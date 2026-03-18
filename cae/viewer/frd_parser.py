"""
CalculiX .frd 文件解析器
.frd 是 CalculiX 输出的二进制/ASCII 混合格式结果文件。
本模块将其解析为 Python 数据结构，供 vtk_export.py 使用。

.frd 结构速查：
  1C  — 节点坐标块
  2C  — 单元拓扑块
  100C — 结果块（位移 U、应力 S、应变 E、反力 RF 等）
  9999 — 文件结束标记
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class FrdNodes:
    ids: list[int]                        # 节点编号（1-based）
    coords: list[tuple[float, float, float]]  # (x, y, z)


@dataclass
class FrdElement:
    eid: int
    etype: int           # CalculiX 单元类型编号
    connectivity: list[int]   # 节点编号列表


@dataclass
class FrdResultStep:
    """单个载荷步 / 时间步的结果。"""
    step: int
    time: float
    name: str            # 字段名，如 "DISP", "STRESS", "FORC"
    components: list[str]  # 分量名称列表
    # values[节点索引] = [分量值, ...]
    values: list[list[float]]
    node_ids: list[int]  # 与 values 一一对应的节点编号


@dataclass
class FrdData:
    nodes: Optional[FrdNodes] = None
    elements: list[FrdElement] = field(default_factory=list)
    results: list[FrdResultStep] = field(default_factory=list)

    @property
    def has_geometry(self) -> bool:
        return self.nodes is not None and len(self.elements) > 0

    @property
    def node_count(self) -> int:
        return len(self.nodes.ids) if self.nodes else 0

    @property
    def element_count(self) -> int:
        return len(self.elements)

    def get_result(self, name: str, step: int = -1) -> Optional[FrdResultStep]:
        """按名称和步骤号查找结果，step=-1 取最后一步。"""
        matches = [r for r in self.results if name.upper() in r.name.upper()]
        if not matches:
            return None
        return matches[step]


# ------------------------------------------------------------------ #
# 单元类型映射：CalculiX 编号 → 节点数
# ------------------------------------------------------------------ #
_ETYPE_NODES: dict[int, int] = {
    1:  8,   # C3D8    8节点六面体
    2:  6,   # C3D6    6节点五面体
    3:  4,   # C3D4    4节点四面体
    4:  20,  # C3D20   20节点六面体（二阶）
    5:  15,  # C3D15   15节点五面体（二阶）
    6:  10,  # C3D10   10节点四面体（二阶）
    7:  3,   # S3      3节点壳
    8:  6,   # S6      6节点壳
    9:  4,   # S4      4节点壳
    10: 8,   # S8      8节点壳
    11: 2,   # B21     2节点梁
    12: 3,   # B22     3节点梁
}


def parse_frd(frd_file: Path) -> FrdData:
    """
    解析 CalculiX ASCII .frd 文件。

    Returns:
        FrdData 数据类，包含节点、单元和结果字段。

    Raises:
        ValueError: 文件格式无法识别时。
        FileNotFoundError: 文件不存在时。
    """
    if not frd_file.exists():
        raise FileNotFoundError(f"找不到 .frd 文件: {frd_file}")

    text = frd_file.read_text(encoding="latin-1", errors="replace")
    lines = text.splitlines()

    data = FrdData()
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # ---- 节点坐标块 ----
        if line.startswith("    1C") or line.startswith("    1PSET"):
            i, data.nodes = _parse_nodes(lines, i)
            continue

        # ---- 单元拓扑块 ----
        if line.startswith("    2C") or line.startswith("    2PSET") or line.startswith("    3C") or line.startswith("    3PSET"):
            i, elems = _parse_elements(lines, i)
            data.elements.extend(elems)
            continue

        # ---- 结果块 ----
        if line.startswith("  100C"):
            i, result = _parse_result(lines, i)
            if result:
                data.results.append(result)
            continue

        # ---- 文件结束 ----
        if line.strip() == "9999":
            break

        i += 1

    return data


# ------------------------------------------------------------------ #
# 内部解析函数
# ------------------------------------------------------------------ #

def _parse_nodes(lines: list[str], start: int) -> tuple[int, FrdNodes]:
    """解析节点坐标块，返回 (下一行索引, FrdNodes)。"""
    ids: list[int] = []
    coords: list[tuple[float, float, float]] = []
    i = start + 1

    while i < len(lines):
        line = lines[i]
        if line.startswith(" -1"):
            # 节点行格式：" -1  <id>  <x>  <y>  <z>"
            parts = line.split()
            if len(parts) >= 5:
                try:
                    ids.append(int(parts[1]))
                    coords.append((float(parts[2]), float(parts[3]), float(parts[4])))
                except (ValueError, IndexError):
                    pass
        elif line.startswith(" -3"):
            i += 1
            break
        i += 1

    return i, FrdNodes(ids=ids, coords=coords)


def _parse_elements(lines: list[str], start: int) -> tuple[int, list[FrdElement]]:
    """解析单元拓扑块。"""
    elements: list[FrdElement] = []
    i = start + 1

    while i < len(lines):
        line = lines[i]
        if line.startswith(" -1"):
            # 单元头行：" -1  <eid>  <etype>  <group>  <mat>"
            parts = line.split()
            if len(parts) >= 3:
                try:
                    eid = int(parts[1])
                    etype = int(parts[2])
                except ValueError:
                    i += 1
                    continue

                # 下一行是节点连接
                i += 1
                if i < len(lines) and lines[i].startswith(" -2"):
                    conn_parts = lines[i].split()[1:]
                    connectivity = [int(x) for x in conn_parts]
                    elements.append(FrdElement(eid=eid, etype=etype, connectivity=connectivity))
        elif line.startswith(" -3"):
            i += 1
            break
        i += 1

    return i, elements


def _parse_result(lines: list[str], start: int) -> tuple[int, Optional[FrdResultStep]]:
    """解析单个结果块（位移、应力等）。"""
    header = lines[start]
    # 解析字段名和时间
    # 格式示例："  100C                             DISP        1  0.00000E+00"
    parts = header.split()
    # 字段名在固定位置
    field_name = "UNKNOWN"
    step = 1
    time = 0.0

    if len(parts) >= 2:
        field_name = parts[1] if len(parts) > 1 else "UNKNOWN"

    # 找 step 和 time
    for j, p in enumerate(parts):
        try:
            v = int(p)
            if 1 <= v <= 9999:
                step = v
                if j + 1 < len(parts):
                    time = float(parts[j + 1])
                break
        except ValueError:
            continue

    i = start + 1
    components: list[str] = []
    node_ids: list[int] = []
    values: list[list[float]] = []

    while i < len(lines):
        line = lines[i]

        # 分量定义行
        if line.startswith(" -4"):
            parts4 = line.split()
            # 格式：" -4  <name>  <ncomp>  <irtype>"
            if len(parts4) >= 2:
                # 下面跟着分量名行
                pass
        elif line.startswith(" -5"):
            # 分量名行：" -5  D1  1  2  1  0"
            parts5 = line.split()
            if len(parts5) >= 2:
                components.append(parts5[1])

        elif line.startswith(" -1"):
            # 结果数值行：" -1  <nid>  <v1>  <v2>  ..."
            parts1 = line.split()
            if len(parts1) >= 2:
                try:
                    nid = int(parts1[1])
                    vals = [float(x) for x in parts1[2:]]
                    node_ids.append(nid)
                    values.append(vals)
                except (ValueError, IndexError):
                    pass

        elif line.startswith(" -3"):
            i += 1
            break

        i += 1

    if not node_ids:
        return i, None

    return i, FrdResultStep(
        step=step,
        time=time,
        name=field_name,
        components=components,
        values=values,
        node_ids=node_ids,
    )