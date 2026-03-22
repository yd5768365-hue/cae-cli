"""
绑定接触 Tie

定义绑定（tied）接触关系。

CalculiX 中 *TIE 用于绑定两个表面，使它们在分析过程中保持协调。

参考 pygccx model_keywords/tie.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from cae.mesh.surface import ElementSurface, NodeSurface
from cae._utils import f2s


@dataclass
class Tie:
    """
    绑定接触。

    将两个表面绑定在一起，使它们在分析过程中保持协调位移。

    Args:
        name: Tie 名称（最多 80 字符）
        dep_surf: 从表面（Dependent Surface）
        ind_surf: 主表面（Independent Surface）
        adjust: 是否调整绑定节点到主表面（默认 True）
        position_tolerance: 生成耦合的位置公差
        cyclic_symmetry: 是否用于循环对称模型
        multistage: 是否为多阶段耦合
        desc: 描述文本

    Example:
        >>> from cae.contact import Tie
        >>> from cae.mesh.surface import ElementSurface
        >>>
        >>> dep = ElementSurface(name="DEP_SURF", element_faces={(1, 1)})
        >>> ind = ElementSurface(name="IND_SURF", element_faces={(2, 2)})
        >>>
        >>> tie = Tie(
        ...     name="TIED_CONTACT",
        ...     dep_surf=dep,
        ...     ind_surf=ind,
        ...     adjust=True
        ... )
    """

    name: str
    """Tie 名称（最多 80 字符）"""
    dep_surf: Union[ElementSurface, NodeSurface]
    """从表面"""
    ind_surf: Union[ElementSurface, NodeSurface]
    """主表面"""
    adjust: bool = True
    """是否调整绑定节点到主表面"""
    position_tolerance: Optional[float] = None
    """生成耦合的位置公差"""
    cyclic_symmetry: bool = False
    """是否用于循环对称模型"""
    multistage: bool = False
    """是否为多阶段耦合"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*TIE"
    """关键词名称"""

    _is_initialized: bool = field(init=False, default=False)

    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        self._validate()

    def __post_init__(self):
        self._is_initialized = True

    def _validate(self) -> None:
        if not self._is_initialized:
            return

        if len(self.name) > 80:
            raise ValueError(f"name 最多 80 字符，当前 {len(self.name)} 字符")

        if self.position_tolerance is not None and self.position_tolerance < 0:
            raise ValueError(f"position_tolerance 必须 >= 0，当前值 {self.position_tolerance}")

        if self.cyclic_symmetry and self.multistage:
            raise ValueError("cyclic_symmetry 和 multistage 不能同时为 True")

        # 简单绑定接触：主表面必须是单元面
        if not self.cyclic_symmetry and not self.multistage:
            if self.ind_surf.element_faces is None or len(self.ind_surf.element_faces) == 0:
                raise ValueError("简单绑定接触时主表面(ind_surf)必须是单元面表面")

        # 多阶段耦合：两者都必须是节点表面
        if self.multistage:
            if self.ind_surf.node_ids is not None and len(self.ind_surf.node_ids) > 0:
                raise ValueError("多阶段耦合时主表面(ind_surf)必须是节点表面")
            if self.dep_surf.node_ids is not None and len(self.dep_surf.node_ids) > 0:
                raise ValueError("多阶段耦合时从表面(dep_surf)必须是节点表面")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # TIE 行
        line = f"*TIE,NAME={self.name}"
        if not self.adjust:
            line += ",ADJUST=NO"
        if self.position_tolerance is not None:
            line += f",POSITION TOLERANCE={f2s(self.position_tolerance)}"
        if self.cyclic_symmetry:
            line += ",CYCLIC SYMMETRY"
        if self.multistage:
            line += ",MULTISTAGE"
        if self.desc:
            line += f",DESCRIPTION={self.desc}"
        lines.append(line)

        # 表面名称行
        lines.append(f"{self.dep_surf.name},{self.ind_surf.name}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
