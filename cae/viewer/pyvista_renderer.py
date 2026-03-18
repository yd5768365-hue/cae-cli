"""
PyVista 渲染引擎
负责将 .vtu / .frd 结果文件渲染为：
  - 静态截图 PNG（变形云图、Von Mises 应力云图）
  - 动画 GIF / MP4（多时间步）
  - 截面切片图

所有渲染均使用 off-screen 模式，无需显示器。
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 强制离屏渲染 —— 必须在 import pyvista 之前设置
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import numpy as np
import pyvista as pv

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 常量
# ------------------------------------------------------------------ #

# 云图配色
CMAP_STRESS     = "jet"        # Von Mises 应力
CMAP_DISP       = "cool"       # 位移幅值
CMAP_DEFAULT    = "viridis"

# 默认渲染尺寸
DEFAULT_W, DEFAULT_H = 1280, 720

# 背景 / 前景颜色（工业风暗色）
BG_COLOR   = "#1a1a24"
EDGE_COLOR = "#444466"
TEXT_COLOR = "white"


# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

@dataclass
class RenderResult:
    success: bool
    files: list[Path] = field(default_factory=list)
    error: Optional[str] = None

    def first(self) -> Optional[Path]:
        return self.files[0] if self.files else None


@dataclass
class MeshInfo:
    """从 .vtu 提取的网格摘要信息。"""
    n_points: int = 0
    n_cells: int = 0
    bounds: tuple = ()          # (xmin, xmax, ymin, ymax, zmin, zmax)
    scalar_fields: list[str] = field(default_factory=list)
    has_displacement: bool = False
    has_stress: bool = False


# ------------------------------------------------------------------ #
# 公共接口
# ------------------------------------------------------------------ #

def load_result(vtu_file: Path):
    """
    加载 .vtu 结果文件，返回 PyVista UnstructuredGrid。
    Raises: FileNotFoundError, RuntimeError
    """
    if not vtu_file.exists():
        raise FileNotFoundError(f"结果文件不存在: {vtu_file}")
    mesh = pv.read(str(vtu_file))
    return mesh


def get_mesh_info(mesh) -> MeshInfo:
    """提取网格摘要信息。"""
    fields = list(mesh.point_data.keys()) + list(mesh.cell_data.keys())
    has_disp = any("DISP" in f.upper() or f.upper().startswith("U") for f in fields)
    has_stress = any("STRESS" in f.upper() or "VONMISES" in f.upper() or "S_" in f.upper() for f in fields)
    return MeshInfo(
        n_points=mesh.n_points,
        n_cells=mesh.n_cells,
        bounds=mesh.bounds,
        scalar_fields=fields,
        has_displacement=has_disp,
        has_stress=has_stress,
    )


def render_displacement(
    vtu_file: Path,
    output_path: Path,
    scale_factor: float = 1.0,
    window_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
    component: str = "magnitude",   # "magnitude" | "x" | "y" | "z"
) -> RenderResult:
    """
    渲染位移云图（变形后的模型着色）。

    Args:
        vtu_file:     结果文件
        output_path:  输出 PNG 路径
        scale_factor: 变形放大倍数（1.0 = 真实比例）
        component:    显示分量（幅值 / x / y / z）
    """
    try:
        mesh = load_result(vtu_file)
    except Exception as exc:
        return RenderResult(success=False, error=str(exc))

    # ---- 查找位移字段（严格模式：无匹配直接报错）----
    disp_key = _find_field(mesh, ["DISP", "U", "displacement"], strict=True)
    if disp_key is None:
        return RenderResult(success=False, error="未找到位移字段（DISP / U）")

    disp = mesh.point_data[disp_key]

    # ---- 计算标量 ----
    if disp.ndim == 2 and disp.shape[1] >= 3:
        scalars = {
            "magnitude": np.linalg.norm(disp[:, :3], axis=1),
            "x":  disp[:, 0],
            "y":  disp[:, 1],
            "z":  disp[:, 2],
        }.get(component, np.linalg.norm(disp[:, :3], axis=1))
        vectors = disp[:, :3]
    else:
        scalars = np.abs(disp.flatten())
        vectors = None

    mesh.point_data["_disp_scalar"] = scalars

    # ---- 变形 ----
    deformed = mesh
    if vectors is not None and scale_factor != 0:
        deformed = mesh.copy()
        deformed.points = mesh.points + vectors * scale_factor

    # ---- 渲染 ----
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pl = pv.Plotter(off_screen=True, window_size=list(window_size))
        pl.set_background(BG_COLOR)
        pl.add_mesh(
            deformed,
            scalars="_disp_scalar",
            cmap=CMAP_DISP,
            show_edges=True,
            edge_color=EDGE_COLOR,
            scalar_bar_args={
                "title": f"位移 {component.upper()} (mm)",
                "color": TEXT_COLOR,
                "title_font_size": 14,
                "label_font_size": 12,
            },
        )
        pl.add_text(
            f"变形云图  scale={scale_factor}×",
            position="upper_left",
            color=TEXT_COLOR,
            font_size=11,
        )
        pl.camera_position = "iso"
        pl.reset_camera()
        pl.screenshot(str(output_path), transparent_background=False)
        pl.close()
    except Exception as exc:
        return RenderResult(success=False, error=f"渲染失败: {exc}")

    return RenderResult(success=True, files=[output_path])


def render_von_mises(
    vtu_file: Path,
    output_path: Path,
    window_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
) -> RenderResult:
    """渲染 Von Mises 应力云图。"""
    try:
        mesh = load_result(vtu_file)
    except Exception as exc:
        return RenderResult(success=False, error=str(exc))

    # ---- 查找应力字段 ----
    vm_key = _find_field(mesh, ["VonMises", "VONMISES", "von_mises", "STRESS_VM"])
    if vm_key is None:
        # 尝试从 6-分量应力场计算
        stress_key = _find_field(mesh, ["STRESS", "S"])
        if stress_key and mesh.point_data[stress_key].ndim == 2:
            s = mesh.point_data[stress_key]
            if s.shape[1] >= 6:
                vm = _von_mises_from_tensor(s)
                mesh.point_data["_von_mises"] = vm
                vm_key = "_von_mises"

    if vm_key is None:
        return RenderResult(success=False, error="未找到 Von Mises / STRESS 字段")

    scalars = mesh.point_data[vm_key]
    if scalars.ndim > 1:
        scalars = scalars.flatten()
    mesh.point_data["_vm"] = scalars
    vmax = float(np.percentile(scalars, 99))   # 去掉极值奇点

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pl = pv.Plotter(off_screen=True, window_size=list(window_size))
        pl.set_background(BG_COLOR)
        pl.add_mesh(
            mesh,
            scalars="_vm",
            cmap=CMAP_STRESS,
            clim=[0, vmax],
            show_edges=True,
            edge_color=EDGE_COLOR,
            scalar_bar_args={
                "title": "Von Mises 应力 (MPa)",
                "color": TEXT_COLOR,
                "title_font_size": 14,
                "label_font_size": 12,
            },
        )
        pl.add_text("Von Mises 应力云图", position="upper_left", color=TEXT_COLOR, font_size=11)
        pl.camera_position = "iso"
        pl.reset_camera()
        pl.screenshot(str(output_path), transparent_background=False)
        pl.close()
    except Exception as exc:
        return RenderResult(success=False, error=f"渲染失败: {exc}")

    return RenderResult(success=True, files=[output_path])


def render_slice(
    vtu_file: Path,
    output_path: Path,
    normal: str = "z",           # "x" | "y" | "z"
    origin_fraction: float = 0.5,  # 切片位置（沿法向轴 0~1）
    scalar_field: Optional[str] = None,
    window_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
) -> RenderResult:
    """
    截面切片渲染。

    Args:
        normal:           切片法向轴
        origin_fraction:  沿法向轴方向的相对位置（0=最小端, 1=最大端）
    """
    try:
        mesh = load_result(vtu_file)
    except Exception as exc:
        return RenderResult(success=False, error=str(exc))

    # 计算切片原点
    bounds = mesh.bounds  # (xmin,xmax, ymin,ymax, zmin,zmax)
    axis_idx = {"x": (0, 1), "y": (2, 3), "z": (4, 5)}.get(normal.lower(), (4, 5))
    lo, hi = bounds[axis_idx[0]], bounds[axis_idx[1]]
    origin_val = lo + (hi - lo) * origin_fraction
    origin_pt = {"x": [origin_val, 0, 0], "y": [0, origin_val, 0], "z": [0, 0, origin_val]}[normal.lower()]
    normal_vec = {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}[normal.lower()]

    try:
        sliced = mesh.slice(normal=normal_vec, origin=origin_pt)
    except Exception as exc:
        return RenderResult(success=False, error=f"切片失败: {exc}")

    if sliced.n_points == 0:
        return RenderResult(success=False, error="切片结果为空，请调整切片位置")

    # 选择标量字段
    if scalar_field is None:
        scalar_field = _find_field(mesh, ["VonMises", "STRESS", "DISP", "U"])
        if scalar_field and scalar_field not in sliced.point_data:
            scalar_field = sliced.point_data.keys()[0] if sliced.point_data.keys() else None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        pl = pv.Plotter(off_screen=True, window_size=list(window_size))
        pl.set_background(BG_COLOR)
        # 原始网格（半透明）
        pl.add_mesh(mesh, opacity=0.15, color="#3355aa", show_edges=False)
        # 切片（不透明着色）
        pl.add_mesh(
            sliced,
            scalars=scalar_field,
            cmap=CMAP_STRESS,
            show_edges=True,
            edge_color=EDGE_COLOR,
            scalar_bar_args={"color": TEXT_COLOR, "title_font_size": 14},
        )
        pl.add_text(
            f"截面切片  法向={normal.upper()}  位置={origin_fraction*100:.0f}%",
            position="upper_left", color=TEXT_COLOR, font_size=11,
        )
        pl.camera_position = "iso"
        pl.reset_camera()
        pl.screenshot(str(output_path), transparent_background=False)
        pl.close()
    except Exception as exc:
        return RenderResult(success=False, error=f"渲染失败: {exc}")

    return RenderResult(success=True, files=[output_path])


def render_animation(
    vtu_files: list[Path],
    output_path: Path,
    scalar_field: Optional[str] = None,
    fps: int = 10,
    window_size: tuple[int, int] = (DEFAULT_W, DEFAULT_H),
) -> RenderResult:
    """
    多时间步动画（GIF 或 MP4）。

    Args:
        vtu_files:    按时间步排序的 .vtu 文件列表
        output_path:  输出路径（.gif 或 .mp4）
        scalar_field: 标量字段名，None 则自动选择
        fps:          帧率
    """
    if not vtu_files:
        return RenderResult(success=False, error="没有输入文件")

    try:
        # 用第一帧确定色标范围
        first = pv.read(str(vtu_files[0]))
        if scalar_field is None:
            scalar_field = _find_field(first, ["VonMises", "STRESS", "DISP", "U"])
        if scalar_field is None or scalar_field not in first.point_data:
            return RenderResult(success=False, error=f"字段 '{scalar_field}' 不存在")

        all_vals = []
        meshes = []
        for f in vtu_files:
            m = pv.read(str(f))
            meshes.append(m)
            if scalar_field in m.point_data:
                v = m.point_data[scalar_field]
                all_vals.append(v.flatten())

        clim = [0, float(np.percentile(np.concatenate(all_vals), 99))]
        output_path.parent.mkdir(parents=True, exist_ok=True)

        pl = pv.Plotter(off_screen=True, window_size=list(window_size))
        pl.set_background(BG_COLOR)
        pl.open_gif(str(output_path), fps=fps)

        for i, m in enumerate(meshes):
            pl.clear()
            pl.add_mesh(
                m,
                scalars=scalar_field,
                cmap=CMAP_STRESS,
                clim=clim,
                show_edges=True,
                edge_color=EDGE_COLOR,
                scalar_bar_args={
                    "title": scalar_field,
                    "color": TEXT_COLOR,
                    "title_font_size": 14,
                },
            )
            pl.add_text(
                f"步骤 {i+1}/{len(meshes)}",
                position="upper_left", color=TEXT_COLOR, font_size=12,
            )
            pl.camera_position = "iso"
            pl.reset_camera()
            pl.write_frame()

        pl.close()
    except Exception as exc:
        return RenderResult(success=False, error=f"动画生成失败: {exc}")

    return RenderResult(success=True, files=[output_path])


def render_all(
    vtu_file: Path,
    output_dir: Path,
    scale_factor: float = 10.0,
) -> dict[str, RenderResult]:
    """
    一键渲染全套图像（位移 + 应力 + 3个方向切片）。
    返回 {图像名称: RenderResult} 字典。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    results: dict[str, RenderResult] = {}

    results["displacement"] = render_displacement(
        vtu_file, output_dir / "displacement.png", scale_factor=scale_factor
    )
    results["von_mises"] = render_von_mises(
        vtu_file, output_dir / "von_mises.png"
    )
    for axis in ("x", "y", "z"):
        results[f"slice_{axis}"] = render_slice(
            vtu_file, output_dir / f"slice_{axis}.png", normal=axis
        )
    return results


# ------------------------------------------------------------------ #
# 内部工具
# ------------------------------------------------------------------ #

def _find_field(mesh, candidates: list[str], strict: bool = False) -> Optional[str]:
    """在 point_data 中模糊匹配字段名，优先返回第一个命中。
    strict=True 时无匹配返回 None，不兜底。
    """
    keys = list(mesh.point_data.keys())
    for cand in candidates:
        for k in keys:
            if cand.upper() in k.upper():
                return k
    if strict:
        return None
    return keys[0] if keys else None


def _von_mises_from_tensor(stress: np.ndarray) -> np.ndarray:
    """从 6 分量 Voigt 应力张量计算 Von Mises 等效应力。"""
    s11, s22, s33 = stress[:, 0], stress[:, 1], stress[:, 2]
    s12, s13, s23 = stress[:, 3], stress[:, 4], stress[:, 5]
    return np.sqrt(0.5 * (
        (s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2 +
        6.0 * (s12 ** 2 + s13 ** 2 + s23 ** 2)
    ))