"""
耦合 Coupling

定义运动耦合或分布耦合。

CalculiX 中 *COUPLING 与 *DISTRIBUTING 或 *KINEMATIC 配合使用，
将参考节点的运动/力耦合到单元面上。

参考 pygccx model_keywords/coupling.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from cae.enums import CouplingType
from cae.mesh.surface import ElementSurface


@dataclass
class Coupling:
    """
    耦合（运动或分布耦合）。

    将参考节点的运动或力耦合到单元面。

    Args:
        type: 耦合类型（DISTRIBUTING / KINEMATIC）
        ref_node: 参考节点 ID
        surface: 依赖表面（必须是单元面表面）
        name: 耦合名称
        first_dof: 第一个自由度（1-3 表示位移，4-6 表示旋转）
        last_dof: 可选，最后一个自由度（省略则仅使用 first_dof）
        orientation: 可选，局部坐标系名称
        cyclic_symmetry: 是否循环对称（仅 DISTRIBUTING 支持）
        desc: 描述文本

    Example:
        >>> from cae.coupling import Coupling
        >>> from cae.enums import CouplingType
        >>> from cae.mesh.surface import ElementSurface
        >>>
        >>> surf = ElementSurface(name='CoupSurf', element_faces={(1, 1), (2, 1)})
        >>> coup = Coupling(
        ...     type=CouplingType.KINEMATIC,
        ...     ref_node=100,
        ...     surface=surf,
        ...     name='KIN_COUP',
        ...     first_dof=1,
        ...     last_dof=3
        ... )
    """

    type: CouplingType
    """耦合类型"""
    ref_node: int
    """参考节点 ID"""
    surface: ElementSurface
    """依赖表面（必须是单元面表面）"""
    name: str
    """耦合名称"""
    first_dof: int
    """第一个自由度"""
    last_dof: Optional[int] = None
    """最后一个自由度"""
    orientation: Optional[str] = None
    """局部坐标系名称"""
    cyclic_symmetry: bool = False
    """是否循环对称（仅 DISTRIBUTING）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*COUPLING"
    """关键词名称"""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "surface":
            if value.element_faces is None or len(value.element_faces) == 0:
                raise ValueError("surface 必须是单元面表面")
        if name == "first_dof":
            if value < 1 or value > 6:
                raise ValueError(f"first_dof 必须在 1-6 之间，当前值 {value}")
        if name == "last_dof" and value is not None:
            if value < 1 or value > 6:
                raise ValueError(f"last_dof 必须在 1-6 之间，当前值 {value}")
        super().__setattr__(name, value)

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # COUPLING 行
        line = f"*COUPLING,CONSTRAINT NAME={self.name},REF NODE={self.ref_node},SURFACE={self.surface.name}"
        if self.orientation:
            line += f",ORIENTATION={self.orientation}"
        if self.desc:
            line += f",DESCRIPTION={self.desc}"
        lines.append(line)

        # *DISTRIBUTING 或 *KINEMATIC
        line = self.type.value
        if self.type.value == "*DISTRIBUTING" and self.cyclic_symmetry:
            line += ",CYCLIC SYMMETRY"
        lines.append(line)

        # 自由度行
        dof_line = f"{self.first_dof}"
        if self.last_dof is not None:
            dof_line += f",{self.last_dof}"
        lines.append(dof_line)

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
