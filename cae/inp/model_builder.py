"""
INP 模型构建器

使用 Python 类方式构建完整的 INP 模型，替代 Jinja2 模板。

参考 pygccx model.py 设计模式。

Usage:
    from cae.inp.model_builder import ModelBuilder, CantileverBeam, FlatPlate

    # 使用预定义模型
    beam = CantileverBeam(L=500, load_value=1000)
    print(beam.to_inp())

    # 或使用构建器
    model = ModelBuilder(title="My Model")
    model.add_nodes([...])
    model.add_elements([...])
    model.add_keywords([...])
    print(model.to_inp())

    # pickle 序列化
    model.to_pickle("model.pkl")
    model2 = ModelBuilder.from_pickle("model.pkl")
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, Sequence

from cae.protocols import IKeyword, IStep
from cae._utils import f2s


# =============================================================================
# 预定义参数化模型
# =============================================================================


@dataclass
class CantileverBeam:
    """
    悬臂梁参数化模型。

    使用 B32 梁单元，一端固定，另一端施加集中力或弯矩。

    参数：
        title: 模型标题
        material_name: 材料名称
        E: 弹性模量 (MPa)
        nu: 泊松比
        density: 密度 (ton/mm³)
        L: 梁长度 (mm)
        width: 梁宽 (mm)
        height: 梁高 (mm)
        n_nodes: 节点数
        load_type: 载荷类型 ('force' 或 'moment')
        load_value: 载荷值

    Example:
        >>> beam = CantileverBeam(L=500, load_value=1000)
        >>> print(beam.to_inp())
    """

    title: str = "Cantilever Beam"
    material_name: str = "STEEL"
    E: float = 210000.0
    nu: float = 0.3
    density: float = 7.85e-9
    L: float = 100.0
    width: float = 10.0
    height: float = 20.0
    n_nodes: int = 11
    load_type: str = "force"
    load_value: float = 1000.0

    def _generate_nodes(self) -> list[str]:
        """生成节点行"""
        lines = []
        lines.append("*NODE, NSET=NALL")
        dx = self.L / (self.n_nodes - 1)
        for i in range(self.n_nodes):
            x = i * dx
            lines.append(f"{i + 1}, {f2s(x)}, 0.0, 0.0")
        return lines

    def _generate_elements(self) -> list[str]:
        """生成单元行"""
        lines = []
        n_elem = self.n_nodes - 1
        lines.append(f"*ELEMENT, TYPE=B32, ELSET=EBEAM")
        for i in range(n_elem):
            lines.append(f"{i + 1}, {i + 1}, {i + 2}")
        return lines

    def _generate_beam_section(self) -> list[str]:
        """生成梁截面"""
        return [
            "*BEAM SECTION, MATERIAL=STEEL, SECTION=RECT",
            f"{f2s(self.width)}, {f2s(self.height)}",
            "0., 0., -1.",
        ]

    def _generate_boundary(self) -> list[str]:
        """生成边界条件"""
        return [
            "*BOUNDARY",
            "NALL, 1, 3, 0.0",
        ]

    def _generate_load(self) -> list[str]:
        """生成载荷"""
        lines = []
        if self.load_type == "force":
            for i in range(1, self.n_nodes + 1):
                lines.append(f"{i}, 2, {f2s(self.load_value)}")
        else:  # moment
            lines.append(f"{self.n_nodes}, 6, {f2s(self.load_value)}")
        return lines

    def _generate_step(self) -> list[str]:
        """生成载荷步"""
        lines = []
        lines.append("*STEP")
        lines.append("*STATIC")
        lines.extend(self._generate_boundary())
        lines.append("*CLOAD")
        lines.extend(self._generate_load())
        lines.append("*EL FILE")
        lines.append("S, E")
        lines.append("*NODE FILE")
        lines.append("U")
        lines.append("*END STEP")
        return lines

    def _generate_material(self) -> list[str]:
        """生成材料定义"""
        return [
            "*MATERIAL, NAME=STEEL",
            "*ELASTIC",
            f"{f2s(self.E)}, {f2s(self.nu)}",
            "*DENSITY",
            f"{f2s(self.density)},",
        ]

    def to_inp(self) -> str:
        """生成完整 INP 文件内容"""
        lines = []
        lines.append(f"*HEADING")
        lines.append(self.title)
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_material())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_nodes())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_elements())
        lines.extend(self._generate_beam_section())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_boundary())
        lines.append("** ----------------------------------------------------------------")
        lines.append("*CLOAD")
        lines.extend(self._generate_load())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_step())
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_inp()


@dataclass
class FlatPlate:
    """
    平板参数化模型。

    使用 S4 壳单元，四角固支，施加均匀压力或集中力。

    参数：
        title: 模型标题
        material_name: 材料名称
        E: 弹性模量 (MPa)
        nu: 泊松比
        density: 密度 (ton/mm³)
        Lx: 板长 (mm)
        Ly: 板宽 (mm)
        thickness: 板厚 (mm)
        n_x: X方向节点数
        n_y: Y方向节点数
        load_type: 载荷类型 ('pressure' 或 'force')
        pressure: 均匀压力 (MPa)
        load_value: 集中载荷值 (N)

    Example:
        >>> plate = FlatPlate(Lx=100, Ly=50, pressure=1.0)
        >>> print(plate.to_inp())
    """

    title: str = "Flat Plate"
    material_name: str = "STEEL"
    E: float = 210000.0
    nu: float = 0.3
    density: float = 7.85e-9
    Lx: float = 100.0
    Ly: float = 50.0
    thickness: float = 1.0
    n_x: int = 10
    n_y: int = 5
    load_type: str = "pressure"
    pressure: float = 1.0
    load_value: float = 1000.0

    def _generate_nodes(self) -> list[str]:
        """生成节点行"""
        lines = []
        lines.append("*NODE, NSET=NALL")
        dx = self.Lx / (self.n_x - 1)
        dy = self.Ly / (self.n_y - 1)
        for j in range(self.n_y):
            for i in range(self.n_x):
                x = i * dx
                y = j * dy
                lines.append(f"{j * self.n_x + i + 1}, {f2s(x)}, {f2s(y)}, 0.0")
        return lines

    def _generate_elements(self) -> list[str]:
        """生成单元行"""
        lines = []
        lines.append("*ELEMENT, TYPE=S4, ELSET=ESHELL")
        for j in range(self.n_y - 1):
            for i in range(self.n_x - 1):
                n1 = j * self.n_x + i + 1
                n2 = n1 + 1
                n3 = n2 + self.n_x
                n4 = n1 + self.n_x
                lines.append(f"{j * (self.n_x - 1) + i + 1}, {n1}, {n2}, {n3}, {n4}")
        return lines

    def _generate_shell_section(self) -> list[str]:
        """生成壳截面"""
        return [
            "*SHELL SECTION, MATERIAL=STEEL, SECTION=5",
            f"{f2s(self.thickness)}",
        ]

    def _generate_boundary(self) -> list[str]:
        """生成边界条件（四角固定）"""
        corners = [1, self.n_x, (self.n_y - 1) * self.n_x + 1, self.n_y * self.n_x]
        lines = ["*BOUNDARY"]
        for c in corners:
            lines.append(f"{c}, 1, 6, 0.0")
        return lines

    def _generate_load(self, in_step: bool = False) -> list[str]:
        """生成载荷"""
        lines = []
        if self.load_type == "pressure":
            lines.append("*DSLOAD")
            lines.append(f"ESHELL, P, {f2s(self.pressure)}")
        else:
            lines.append("*CLOAD")
            total = self.n_x * self.n_y
            per_node = self.load_value / total
            for i in range(1, total + 1):
                lines.append(f"{i}, 3, {f2s(per_node)}")
        return lines

    def _generate_step(self) -> list[str]:
        """生成载荷步"""
        lines = []
        lines.append("*STEP")
        lines.append("*STATIC")
        lines.extend(self._generate_load(in_step=True))
        lines.append("*EL FILE")
        lines.append("S, E")
        lines.append("*NODE FILE")
        lines.append("U")
        lines.append("*END STEP")
        return lines

    def _generate_material(self) -> list[str]:
        """生成材料定义"""
        return [
            "*MATERIAL, NAME=STEEL",
            "*ELASTIC",
            f"{f2s(self.E)}, {f2s(self.nu)}",
            "*DENSITY",
            f"{f2s(self.density)},",
        ]

    def to_inp(self) -> str:
        """生成完整 INP 文件内容"""
        lines = []
        lines.append("*HEADING")
        lines.append(self.title)
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_material())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_nodes())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_elements())
        lines.extend(self._generate_shell_section())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_boundary())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_load())
        lines.append("** ----------------------------------------------------------------")
        lines.extend(self._generate_step())
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_inp()


# =============================================================================
# 通用模型构建器
# =============================================================================


@dataclass
class ModelBuilder:
    """
    通用 INP 模型构建器。

    支持自由组合节点、单元、关键词构建模型。

    参数：
        title: 模型标题
        jobname: 工作名称

    Example:
        >>> from cae.inp.keywords import create_elastic
        >>> model = ModelBuilder(title="My Model")
        >>> model.add_nodes([(1, 0, 0), (2, 1, 0)])
        >>> model.add_element(1, "C3D8", (1, 2, 3, 4, 5, 6, 7, 8))
        >>> model.add_keywords(create_elastic("ISO", E=210000, nu=0.3))
        >>> print(model.to_inp())
    """

    title: str = "Generated Model"
    jobname: str = "jobname"

    _nodes: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    _elements: dict[int, tuple[str, tuple[int, ...]]] = field(default_factory=dict)
    _keywords: list[IKeyword] = field(default_factory=list)
    _steps: list[IStep] = field(default_factory=list)

    def add_node(
        self,
        coords: tuple[float, float, float],
        node_id: Optional[int] = None,
    ) -> int:
        """添加节点"""
        if node_id is None:
            node_id = len(self._nodes) + 1
        self._nodes[node_id] = coords
        return node_id

    def add_nodes(
        self,
        nodes: Sequence[tuple[float, float, float]],
        start_id: int = 1,
    ) -> list[int]:
        """批量添加节点"""
        ids = []
        for i, coords in enumerate(nodes):
            node_id = start_id + i
            self._nodes[node_id] = coords
            ids.append(node_id)
        return ids

    def add_element(
        self,
        elem_type: str,
        node_ids: tuple[int, ...],
        elem_id: Optional[int] = None,
    ) -> int:
        """添加单元"""
        if elem_id is None:
            elem_id = len(self._elements) + 1
        self._elements[elem_id] = (elem_type, node_ids)
        return elem_id

    def add_keywords(self, *keywords: IKeyword) -> None:
        """添加关键词"""
        self._keywords.extend(keywords)

    def add_step(self, step: IStep) -> None:
        """添加载荷步"""
        self._steps.append(step)

    def to_inp(self) -> str:
        """生成 INP 文件内容"""
        lines = []
        lines.append(f"*HEADING")
        lines.append(self.title)

        # 节点
        if self._nodes:
            lines.append("*NODE")
            for nid in sorted(self._nodes.keys()):
                x, y, z = self._nodes[nid]
                lines.append(f"{nid},{f2s(x)},{f2s(y)},{f2s(z)}")

        # 单元（按类型分组）
        if self._elements:
            by_type: dict[str, list[int]] = {}
            for eid, (etype, _) in self._elements.items():
                by_type.setdefault(etype, []).append(eid)

            for etype, eids in by_type.items():
                lines.append(f"*ELEMENT, TYPE={etype}")
                for eid in sorted(eids):
                    _, nids = self._elements[eid]
                    lines.append(f"{eid}," + ",".join(str(n) for n in nids))

        # 关键词
        for kw in self._keywords:
            lines.append(str(kw))

        # 载荷步
        for step in self._steps:
            lines.append(str(step))

        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_inp()

    def write_file(self, filepath: str) -> None:
        """写入 INP 文件"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_inp())

    def to_pickle(self, filepath: str) -> None:
        """
        序列化模型到 pickle 文件。

        用于保存模型状态，支持后续加载继续编辑。
        求解和后处理可以分离进行。

        Args:
            filepath: 输出 pickle 文件路径
        """
        with open(filepath, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def from_pickle(cls, filepath: str) -> "ModelBuilder":
        """
        从 pickle 文件加载模型。

        Args:
            filepath: pickle 文件路径

        Returns:
            ModelBuilder 实例
        """
        with open(filepath, "rb") as f:
            obj = pickle.load(f)
        if isinstance(obj, cls):
            return obj
        raise TypeError(f"反序列化对象不是 ModelBuilder 类型，而是 {type(obj)}")
