"""
VTK 导出模块
将 CalculiX 输出 (.frd) 转换为 ParaView 可读的 VTK XML 格式 (.vtu)。

转换策略：
  - 优先使用 meshio 直接读取 .frd（meshio >= 5.3 支持）
  - meshio 失败时回退到自己的 frd_parser + meshio 写出
  - 支持字段：位移(U)、Von Mises 应力(S)、反力(RF)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import meshio as _meshio_module
    _HAS_MESHIO = True
except ImportError:
    _meshio_module = None  # type: ignore
    _HAS_MESHIO = False

log = logging.getLogger(__name__)

# CalculiX 单元类型 → meshio 单元类型名
_ETYPE_TO_MESHIO: dict[int, str] = {
    1:  "hexahedron",        # C3D8
    2:  "wedge",             # C3D6
    3:  "tetra",             # C3D4
    4:  "hexahedron20",      # C3D20
    5:  "wedge15",           # C3D15
    6:  "tetra10",           # C3D10
    7:  "triangle",          # S3
    8:  "triangle6",         # S6
    9:  "quad",              # S4
    10: "quad8",             # S8
}


@dataclass
class VtkExportResult:
    success: bool
    vtu_file: Optional[Path] = None
    error: Optional[str] = None
    node_count: int = 0
    element_count: int = 0
    fields: list[str] = None

    def __post_init__(self):
        if self.fields is None:
            self.fields = []


def frd_to_vtu(
    frd_file: Path,
    output_dir: Optional[Path] = None,
) -> VtkExportResult:
    """
    将 .frd 结果文件转换为 .vtu（VTK XML Unstructured Grid）。

    先尝试 meshio 直读，失败后用内置解析器回退。

    Args:
        frd_file:   CalculiX .frd 结果文件
        output_dir: 输出目录，默认与 frd_file 同目录

    Returns:
        VtkExportResult
    """
    if not frd_file.exists():
        return VtkExportResult(success=False, error=f"文件不存在: {frd_file}")

    out_dir = output_dir or frd_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    vtu_path = out_dir / f"{frd_file.stem}.vtu"

    # ---- 尝试 meshio 直读 ----
    result = _try_meshio_direct(frd_file, vtu_path)
    if result.success:
        log.debug("meshio 直读成功: %s", vtu_path)
        return result

    log.debug("meshio 直读失败（%s），回退到内置解析器", result.error)

    # ---- 回退：内置解析器 + meshio 写出 ----
    return _fallback_frd_parser(frd_file, vtu_path)


def _try_meshio_direct(frd_file: Path, vtu_path: Path) -> VtkExportResult:
    """尝试用 meshio 直接读取 .frd 并写出 .vtu。"""
    if not _HAS_MESHIO:
        return VtkExportResult(success=False, error="meshio 未安装")
    try:
        mesh = _meshio_module.read(str(frd_file))
        _meshio_module.write(str(vtu_path), mesh)

        fields = list(mesh.point_data.keys()) + list(mesh.cell_data.keys())
        n_nodes = len(mesh.points)
        n_cells = sum(len(cb.data) for cb in mesh.cells)

        return VtkExportResult(
            success=True,
            vtu_file=vtu_path,
            node_count=n_nodes,
            element_count=n_cells,
            fields=fields,
        )
    except Exception as exc:  # noqa: BLE001
        return VtkExportResult(success=False, error=str(exc))


def _fallback_frd_parser(frd_file: Path, vtu_path: Path) -> VtkExportResult:
    """使用内置 frd_parser 解析，再用 meshio 写出 .vtu。"""
    if not _HAS_MESHIO:
        return VtkExportResult(success=False, error="meshio 未安装，请运行 pip install meshio")

    try:
        from .frd_parser import parse_frd
    except ImportError as exc:
        return VtkExportResult(success=False, error=f"依赖缺失: {exc}")

    try:
        frd = parse_frd(frd_file)
    except Exception as exc:  # noqa: BLE001
        return VtkExportResult(success=False, error=f"解析 .frd 失败: {exc}")

    if not frd.has_geometry:
        return VtkExportResult(
            success=False,
            error=".frd 文件中未找到节点或单元数据",
        )

    # ---- 构建 meshio Mesh ----
    # 节点坐标：(N, 3) float64
    points = np.array(frd.nodes.coords, dtype=np.float64)

    # 节点编号 → 0-based 索引映射
    node_id_to_idx: dict[int, int] = {
        nid: idx for idx, nid in enumerate(frd.nodes.ids)
    }

    # 按单元类型分组
    cells_by_type: dict[str, list[list[int]]] = {}
    for elem in frd.elements:
        mtype = _ETYPE_TO_MESHIO.get(elem.etype)
        if mtype is None:
            log.warning("未知单元类型 %d，跳过", elem.etype)
            continue
        conn_0based = [node_id_to_idx[nid] for nid in elem.connectivity
                       if nid in node_id_to_idx]
        cells_by_type.setdefault(mtype, []).append(conn_0based)

    if not cells_by_type:
        return VtkExportResult(success=False, error="没有可识别的单元类型")

    cells = [(k, np.array(v, dtype=np.int64)) for k, v in cells_by_type.items()]

    # ---- 附加点数据（节点结果） ----
    point_data: dict[str, np.ndarray] = {}
    exported_fields: list[str] = []

    # 辅助函数：根据分量名判断结果类型
    def _get_result_type(components: list[str]) -> str:
        """根据分量名判断结果类型（位移/应力/其他）"""
        comp_str = " ".join(components).upper()
        if any(c in comp_str for c in ["D1", "D2", "D3", "U1", "U2", "U3", "DISP"]):
            return "Displacement"
        if any(c in comp_str for c in ["SXX", "SYY", "SZZ", "SXY", "SYZ", "SZX", "STRESS"]):
            return "Stress"
        if "STR(" in comp_str or "ERROR" in comp_str:
            return "Error"
        return "Result"

    for res in frd.results:
        if not res.values:
            continue

        # 将结果映射到全节点数组
        n_nodes = len(frd.nodes.ids)
        n_comps = len(res.values[0]) if res.values else 0
        if n_comps == 0:
            continue

        arr = np.zeros((n_nodes, n_comps), dtype=np.float64)
        for nid, vals in zip(res.node_ids, res.values):
            idx = node_id_to_idx.get(nid)
            if idx is not None and len(vals) == n_comps:
                arr[idx] = vals

        # 根据分量类型生成有意义的字段名
        result_type = _get_result_type(res.components)
        field_key = f"{result_type}_step{res.step}"
        point_data[field_key] = arr.squeeze() if n_comps == 1 else arr
        exported_fields.append(field_key)

        # 如果是应力分量，计算 Von Mises 应力
        if result_type == "Stress" and n_comps >= 6:
            vm = von_mises(arr)
            vm_key = f"VonMises_step{res.step}"
            point_data[vm_key] = vm
            exported_fields.append(vm_key)

    mesh = _meshio_module.Mesh(points=points, cells=cells, point_data=point_data)

    try:
        _meshio_module.write(str(vtu_path), mesh)
    except Exception as exc:  # noqa: BLE001
        return VtkExportResult(success=False, error=f"写出 .vtu 失败: {exc}")

    return VtkExportResult(
        success=True,
        vtu_file=vtu_path,
        node_count=len(frd.nodes.ids),
        element_count=frd.element_count,
        fields=exported_fields,
    )


# 导出共享函数供外部使用
from cae.viewer._utils import von_mises  # noqa: E402, F401