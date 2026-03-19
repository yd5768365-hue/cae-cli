"""
Mesh 检查模块
在求解前预览 .inp 文件的网格、边界条件和载荷，
类似 CGX 的实时可视化效果。

功能：
  - 解析 .inp 提取节点/单元/NSET/ELSET
  - PyVista 渲染网格（按 NSET 着色边界条件）
  - 载荷箭头可视化（*CLOAD/*DLOAD）
  - 输出 HTML 预览报告
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# 强制离屏渲染
os.environ.setdefault("PYVISTA_OFF_SCREEN", "true")

import numpy as np

from cae.inp import InpParser

log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# 数据结构
# ------------------------------------------------------------------ #

# CalculiX 单元类型 → PyVista cell type
_ETYPE_TO_PV: dict[int, str] = {
    1: "hexahedron",      # C3D8
    2: "wedge",           # C3D6
    3: "tetra",           # C3D4
    4: "hexahedron20",    # C3D20
    5: "wedge15",         # C3D15
    6: "tetra10",         # C3D10
    7: "triangle",        # S3
    8: "triangle6",       # S6
    9: "quad",            # S4
    10: "quad8",          # S8
}

# NSET 颜色表（工业风）
_NSET_COLORS = [
    "#ff6b6b",  # 红色 — 固定约束
    "#ffd93d",  # 黄色 — 对称约束
    "#6bcb77",  # 绿色 — 位移约束
    "#4d96ff",  # 蓝色 — 通用节点集
    "#ff922b",  # 橙色 — 载荷作用点
    "#cc5de8",  # 紫色 — 耦合点
    "#20c997",  # 青色 — 其他
]


@dataclass
class MeshSummary:
    """网格摘要。"""
    n_nodes: int = 0
    n_elements: int = 0
    n_nsets: int = 0
    n_elsets: int = 0
    element_types: dict[str, int] = field(default_factory=dict)
    nsets: dict[str, list[int]] = field(default_factory=dict)
    elsets: dict[str, list[int]] = field(default_factory=dict)
    boundaries: list[dict] = field(default_factory=list)  # [{name, nset, dof, value}]
    cloads: list[dict] = field(default_factory=list)     # [{name, node, dof, value}]
    dloads: list[dict] = field(default_factory=list)     # [{name, elset, surface, value}]


@dataclass
class MeshCheckResult:
    success: bool
    summary: Optional[MeshSummary] = None
    html_file: Optional[Path] = None
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None


# ------------------------------------------------------------------ #
# 网格摘要提取
# ------------------------------------------------------------------ #

def extract_mesh_summary(inp_file: Path) -> MeshSummary:
    """
    从 .inp 文件提取网格摘要。

    解析内容：
      - 节点坐标（*NODE）
      - 单元拓扑（*ELEMENT）
      - 节点集（*NSET，含 GENERATE 范围）
      - 单元集（*ELSET，含 GENERATE 范围）
      - 边界条件（*BOUNDARY）
      - 集中载荷（*CLOAD）
      - 分布载荷（*DLOAD）
    """
    parser = InpParser()
    blocks = parser.parse(inp_file)

    summary = MeshSummary()
    node_ids_to_coords: dict[int, list[float]] = {}

    for block in blocks:
        kw = block.keyword_name.upper()

        # ---- 节点 ----
        if kw == "*NODE":
            summary.n_nodes += _parse_nodes(block, node_ids_to_coords)

        # ---- 单元 ----
        elif kw == "*ELEMENT":
            n_els, etypes = _parse_elements(block, summary)
            summary.n_elements += n_els
            for et, cnt in etypes.items():
                summary.element_types[et] = summary.element_types.get(et, 0) + cnt

        # ---- NSET ----
        elif kw == "*NSET":
            nset_name = block.get_param("NAME") or block.get_param("NSET")
            if nset_name:
                nset_ids = _parse_node_set(block, node_ids_to_coords)
                summary.nsets[nset_name.upper()] = nset_ids
                summary.n_nsets += 1

        # ---- ELSET ----
        elif kw == "*ELSET":
            elset_name = block.get_param("NAME") or block.get_param("ELSET")
            if elset_name:
                summary.elsets[elset_name.upper()] = []  # 简化：暂不展开 element id
                summary.n_elsets += 1

        # ---- BOUNDARY ----
        elif kw == "*BOUNDARY":
            bc = _parse_boundary(block)
            if bc:
                summary.boundaries.append(bc)

        # ---- CLOAD ----
        elif kw == "*CLOAD":
            cloads = _parse_cload(block)
            summary.cloads.extend(cloads)

        # ---- DLOAD ----
        elif kw == "*DLOAD":
            dloads = _parse_dload(block)
            summary.dloads.extend(dloads)

    return summary


def _parse_nodes(block, node_dict: dict) -> int:
    """解析 *NODE 块，返回节点数量。"""
    count = 0
    for line in block.data_lines:
        if not line.strip() or line.startswith("**"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 4:
            nid = int(parts[0])
            coords = [float(parts[1]), float(parts[2]), float(parts[3])]
            node_dict[nid] = coords
            count += 1
    return count


def _parse_elements(block, summary) -> tuple[int, dict]:
    """解析 *ELEMENT 块，返回 (数量, {类型: 数量})。"""
    count = 0
    etype_map: dict[str, int] = {}
    etype_param = block.get_param("TYPE") or ""
    elset_name = block.get_param("ELSET") or "DEFAULT"

    for line in block.data_lines:
        if not line.strip() or line.startswith("**"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            count += 1

    # 从 TYPE 参数推断单元类型名
    etype = etype_param.upper() if etype_param else "UNKNOWN"
    etype_map[etype] = etype_map.get(etype, 0) + count

    return count, etype_map


def _parse_node_set(block, node_dict: dict) -> list[int]:
    """
    解析 *NSET 块，返回节点编号列表。
    支持 GENERATE 关键字（范围生成）。
    """
    node_ids: list[int] = []
    generate_mode = "GENERATE" in block.lead_line.upper()

    if generate_mode:
        # GENERATE 模式：第一行是 start, stop, step
        for line in block.data_lines:
            if not line.strip():
                continue
            parts = line.replace(",", " ").split()
            if len(parts) >= 2:
                try:
                    start = int(parts[0])
                    stop = int(parts[1])
                    step = int(parts[2]) if len(parts) > 2 else 1
                    node_ids.extend(range(start, stop + 1, step))
                except ValueError:
                    pass
    else:
        for line in block.data_lines:
            if not line.strip() or line.startswith("**"):
                continue
            parts = line.replace(",", " ").split()
            for p in parts:
                try:
                    nid = int(p)
                    if nid in node_dict:
                        node_ids.append(nid)
                except ValueError:
                    pass

    return node_ids


def _parse_boundary(block) -> Optional[dict]:
    """解析 *BOUNDARY，返回边界条件信息。"""
    name = block.get_param("NAME")
    nset = block.get_param("NSET") or block.get_param("NSET")
    dof_start = block.get_param("DOF") or "1"
    dof_end = block.get_param("DOF2") or dof_start
    value = block.get_param("VALUE") or "0.0"

    # 从 data_lines 提取实际节点
    nodes = []
    for line in block.data_lines:
        if not line.strip() or line.startswith("**"):
            continue
        parts = line.replace(",", " ").split()
        for p in parts:
            try:
                nodes.append(int(p))
            except ValueError:
                pass

    if not nodes and not nset:
        return None

    return {
        "name": name or f"BC-{nset or 'unnamed'}",
        "nset": nset,
        "nodes": nodes,
        "dof_start": int(dof_start),
        "dof_end": int(dof_end),
        "value": float(value),
    }


def _parse_cload(block) -> list[dict]:
    """解析 *CLOAD，返回集中载荷列表。"""
    cloads = []
    name = block.get_param("NAME") or "CLOAD"
    nset = block.get_param("NSET") or ""

    for line in block.data_lines:
        if not line.strip() or line.startswith("**"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 3:
            try:
                node = int(parts[0])
                dof = int(parts[1])
                value = float(parts[2])
                cloads.append({
                    "name": name,
                    "nset": nset,
                    "node": node,
                    "dof": dof,
                    "value": value,
                })
            except ValueError:
                pass
    return cloads


def _parse_dload(block) -> list[dict]:
    """解析 *DLOAD，返回分布载荷列表。"""
    dloads = []
    name = block.get_param("NAME") or "DLOAD"
    elset = block.get_param("ELSET") or ""

    for line in block.data_lines:
        if not line.strip() or line.startswith("**"):
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 3:
            try:
                elem = int(parts[0])
                dof = int(parts[1])
                value = float(parts[2])
                dloads.append({
                    "name": name,
                    "elset": elset,
                    "element": elem,
                    "dof": dof,
                    "value": value,
                })
            except ValueError:
                pass
    return dloads


# ------------------------------------------------------------------ #
# PyVista 可视化
# ------------------------------------------------------------------ #

def render_mesh_check(
    inp_file: Path,
    output_html: Path,
    window_size: tuple[int, int] = (1280, 720),
) -> MeshCheckResult:
    """
    渲染网格检查图，输出 HTML 报告。

    可视化内容：
      - 网格（按单元类型着色）
      - 边界条件（节点按 NSET 着色）
      - 载荷（箭头表示）
    """
    try:
        import pyvista as pv
    except ImportError:
        return MeshCheckResult(
            success=False,
            error="PyVista 未安装，请运行: pip install pyvista",
        )

    try:
        summary = extract_mesh_summary(inp_file)
    except Exception as exc:
        return MeshCheckResult(success=False, error=f"解析失败: {exc}")

    warnings: list[str] = []

    # ---- 构建 PyVista Grid ----
    parser = InpParser()
    blocks = parser.parse(inp_file)

    node_id_to_idx: dict[int, int] = {}
    points = []
    node_coords: dict[int, list[float]] = {}

    for block in blocks:
        if block.keyword_name.upper() == "*NODE":
            for line in block.data_lines:
                if not line.strip():
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) >= 4:
                    nid = int(parts[0])
                    coords = [float(parts[1]), float(parts[2]), float(parts[3])]
                    idx = len(points)
                    points.append(coords)
                    node_id_to_idx[nid] = idx
                    node_coords[nid] = coords

    if not points:
        return MeshCheckResult(success=False, error="未找到节点数据")

    # ---- 构建单元 ----
    cells: list[tuple[str, list[int]]] = []
    cell_types: list[int] = []

    etype_name_to_num = {
        "C3D8": 1, "C3D8R": 1,
        "C3D6": 2,
        "C3D4": 3, "C3D10": 3,
        "C3D20": 4, "C3D20R": 4,
        "C3D15": 5,
        "S3": 7, "STRI3": 7,
        "S6": 8,
        "S4": 9, "S4R": 9,
        "S8": 10, "S8R": 10,
    }

    for block in blocks:
        if block.keyword_name.upper() == "*ELEMENT":
            etype_str = (block.get_param("TYPE") or "").upper()
            etype_num = etype_name_to_num.get(etype_str, 0)
            if etype_num == 0:
                continue
            cell_name = _ETYPE_TO_PV.get(etype_num, "mixed")

            for line in block.data_lines:
                if not line.strip():
                    continue
                parts = line.replace(",", " ").split()
                if len(parts) >= 2:
                    connectivity = [node_id_to_idx[int(p)] for p in parts[1:] if int(p) in node_id_to_idx]
                    if len(connectivity) >= 3:
                        cells.append((cell_name, connectivity))
                        cell_types.append(etype_num)

    if not cells:
        warnings.append("未找到单元数据，仅显示节点")

    # ---- 构建 PyVista 结构 ----
    try:
        grid = pv.UnstructuredGrid()
        for cell_name, conn in cells:
            etype_num = etype_name_to_num.get(cell_name.upper(), 0)
            if etype_num == 1:
                grid.insert_next_cell(pv.CellType.HEXAHEDRON, conn)
            elif etype_num == 2:
                grid.insert_next_cell(pv.CellType.WEDGE, conn)
            elif etype_num == 3:
                grid.insert_next_cell(pv.CellType.TETRA, conn)
            elif etype_num == 7:
                grid.insert_next_cell(pv.CellType.TRIANGLE, conn)
            elif etype_num == 9:
                grid.insert_next_cell(pv.CellType.QUAD, conn)
            else:
                grid.insert_next_cell(pv.CellType.QUAD, conn)

        grid.points = np.array(points)
    except Exception as exc:
        warnings.append(f"网格构建警告: {exc}")

    # ---- 渲染 ----
    try:
        pl = pv.Plotter(off_screen=True, window_size=list(window_size))
        pl.set_background("#1a1a24")

        # 网格
        if grid.n_cells > 0:
            pl.add_mesh(
                grid,
                show_edges=True,
                edge_color="#444466",
                scalars=cell_types[:grid.n_cells] if len(cell_types) == grid.n_cells else None,
                cmap="tab10",
                opacity=0.85,
                label="Elements",
            )

        # 节点球（标注）
        node_points = np.array([node_coords[nid] for nid in sorted(node_coords.keys())][:5000])
        if len(node_points) > 0:
            pl.add_points(
                node_points,
                color="#88aaff",
                point_size=2,
                render_points_as_spheres=True,
                label=f"Nodes ({len(node_points)})",
            )

        # 边界条件节点着色
        bc_nodes_list = []
        for i, (nset_name, node_ids) in enumerate(summary.nsets.items()):
            bc_nodes = np.array([node_coords[nid] for nid in node_ids if nid in node_coords][:3000])
            if len(bc_nodes) > 0:
                color = _NSET_COLORS[i % len(_NSET_COLORS)]
                pl.add_points(
                    bc_nodes,
                    color=color,
                    point_size=8,
                    render_points_as_spheres=True,
                    label=f"NSET: {nset_name} ({len(node_ids)})",
                )
                bc_nodes_list.append((nset_name, bc_nodes, color))

        # 载荷箭头（CLOAD）
        for cload in summary.cloads[:50]:  # 最多50个
            nid = cload["node"]
            if nid not in node_coords:
                continue
            origin = np.array(node_coords[nid])
            dof = cload["dof"]
            value = cload["value"]

            # DOF 1=X, 2=Y, 3=Z
            direction = np.array([1.0, 0.0, 0.0])
            if dof == 2:
                direction = np.array([0.0, 1.0, 0.0])
            elif dof == 3:
                direction = np.array([0.0, 0.0, 1.0])

            scale = abs(value) / max(abs(v["value"]) for v in summary.cloads) if summary.cloads else 1.0
            arrow_len = 0.05 + 0.5 * scale
            arrow = pv.Arrow(
                start=origin,
                direction=direction,
                scale=arrow_len,
            )
            pl.add_mesh(
                arrow,
                color="#ff4444",
                label=f"CLOAD: {cload['name']} = {value:.2e}",
            )

        pl.add_legend(
            loc="upper_left",
            bcolor="#1a1a24",
            border=True,
            size=(0.25, 0.4),
        )
        pl.camera_position = "iso"
        pl.reset_camera()

        # 截图
        output_html.parent.mkdir(parents=True, exist_ok=True)
        pl.screenshot(str(output_html), transparent_background=False)
        pl.close()

    except Exception as exc:
        return MeshCheckResult(success=False, error=f"渲染失败: {exc}")

    return MeshCheckResult(
        success=True,
        summary=summary,
        html_file=output_html,
        warnings=warnings,
    )


# ------------------------------------------------------------------ #
# HTML 报告生成（Glance 风格）
# ------------------------------------------------------------------ #

def generate_mesh_check_html(
    summary: MeshSummary,
    screenshot_path: Path,
    output_path: Path,
    inp_name: str = "",
) -> None:
    """生成网格检查 HTML 报告。"""

    # 节点集表格
    nsets_rows = ""
    for name, node_ids in list(summary.nsets.items())[:20]:
        nsets_rows += f"<tr><td>{name}</td><td>{len(node_ids)}</td><td style='max-width:300px;overflow:hidden;text-overflow:ellipsis'>{str(node_ids[:20])[1:-1]}{'...' if len(node_ids)>20 else ''}</td></tr>"

    # 边界条件表格
    bc_rows = ""
    for bc in summary.boundaries[:20]:
        bc_rows += f"<tr><td>{bc['name']}</td><td>{bc.get('nset','-')}</td><td>{bc.get('dof_start','-')}-{bc.get('dof_end','-')}</td><td>{bc.get('value','0')}</td><td>{len(bc.get('nodes',[]))}</td></tr>"

    # 载荷表格
    load_rows = ""
    for cl in summary.cloads[:20]:
        load_rows += f"<tr><td>{cl['name']}</td><td>{cl['node']}</td><td>DOF{cl['dof']}</td><td>{cl['value']:.4e}</td></tr>"

    # 单元类型统计
    etype_rows = ""
    for et, cnt in summary.element_types.items():
        etype_rows += f"<tr><td>{et}</td><td>{cnt}</td></tr>"

    html = f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>Mesh Check — {inp_name}</title>
<style>
  :root {{
    --bg: #0e0e16; --surface: #16161f; --surface2: #1e1e2e;
    --border: #2a2a3e; --accent: #4488ff; --accent2: #44ccaa;
    --text: #d8d8f0; --muted: #7070a0; --danger: #ff6666;
    --success: #44dd88; --warning: #ffd93d; --font: system-ui, sans-serif;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: var(--font);
         line-height: 1.6; padding: 24px; }}
  h1 {{ color: var(--accent); margin-bottom: 8px; font-size: 1.5rem; }}
  h2 {{ color: var(--accent2); margin: 20px 0 10px; font-size: 1.1rem;
        border-bottom: 1px solid var(--border); padding-bottom: 4px; }}
  .summary-bar {{ display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0 20px; }}
  .stat {{ background: var(--surface); border: 1px solid var(--border);
           border-radius: 8px; padding: 10px 16px; }}
  .stat .val {{ font-size: 1.6rem; font-weight: 700; color: var(--accent); }}
  .stat .lbl {{ font-size: 0.75rem; color: var(--muted); text-transform: uppercase; }}
  .screenshot {{ background: var(--surface); border: 1px solid var(--border);
                 border-radius: 8px; overflow: hidden; margin: 12px 0; }}
  .screenshot img {{ width: 100%; height: auto; display: block; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th {{ background: var(--surface2); color: var(--muted); padding: 6px 10px;
        text-align: left; font-weight: 600; text-transform: uppercase;
        font-size: 0.7rem; letter-spacing: 0.05em; }}
  td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); }}
  tr:hover td {{ background: var(--surface); }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px;
            font-size: 0.75rem; font-weight: 600; }}
  .badge-warning {{ background: #ffd93d22; color: var(--warning); }}
  .badge-danger {{ background: #ff666622; color: var(--danger); }}
  .badge-success {{ background: #44dd8822; color: var(--success); }}
  .badge-info {{ background: #4488ff22; color: var(--accent); }}
  .warn {{ background: #ffd93d11; border: 1px solid var(--warning); padding: 8px 12px;
           border-radius: 6px; color: var(--warning); margin: 8px 0; font-size: 0.875rem; }}
  .footer {{ margin-top: 32px; color: var(--muted); font-size: 0.75rem;
             text-align: center; }}
</style>
</head>
<body>

<h1>🔍 Mesh Check Report</h1>
<p style="color:var(--muted);font-size:0.875rem">{inp_name}</p>

<div class="summary-bar">
  <div class="stat"><div class="val">{summary.n_nodes:,}</div><div class="lbl">Nodes</div></div>
  <div class="stat"><div class="val">{summary.n_elements:,}</div><div class="lbl">Elements</div></div>
  <div class="stat"><div class="val">{summary.n_nsets}</div><div class="lbl">Node Sets</div></div>
  <div class="stat"><div class="val">{summary.n_elsets}</div><div class="lbl">Elem Sets</div></div>
  <div class="stat"><div class="val">{len(summary.boundaries)}</div><div class="lbl">BCs</div></div>
  <div class="stat"><div class="val">{len(summary.cloads)}</div><div class="lbl">CLOADs</div></div>
</div>

<div class="screenshot">
  <img src="{screenshot_path.name}" alt="Mesh Preview" loading="lazy"/>
</div>

<h2>单元类型统计</h2>
<table>
  <tr><th>类型</th><th>数量</th></tr>
  {etype_rows or '<tr><td colspan="2" style="color:var(--muted)">无数据</td></tr>'}
</table>

<h2>节点集 (NSET)</h2>
<table>
  <tr><th>名称</th><th>节点数</th><th>节点列表（最多20个）</th></tr>
  {nsets_rows or '<tr><td colspan="3" style="color:var(--muted)">未定义节点集</td></tr>'}
</table>

<h2>边界条件 (BOUNDARY)</h2>
<table>
  <tr><th>名称</th><th>节点集</th><th>DOF范围</th><th>值</th><th>节点数</th></tr>
  {bc_rows or '<tr><td colspan="5" style="color:var(--muted)">未定义边界条件</td></tr>'}
</table>

<h2>集中载荷 (CLOAD)</h2>
<table>
  <tr><th>名称</th><th>节点</th><th>DOF</th><th>值</th></tr>
  {load_rows or '<tr><td colspan="4" style="color:var(--muted)">无集中载荷</td></tr>'}
</table>

<div class="footer">
  Generated by cae-cli mesh check · {inp_name}
</div>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
