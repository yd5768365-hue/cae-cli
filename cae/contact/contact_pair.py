"""
接触对 ContactPair

定义两个表面之间的接触关系。

CalculiX 中 *CONTACT PAIR 用于定义接触对，必须先定义
SurfaceInteraction（包含 SurfaceBehavior 和/或 Friction）。

参考 pygccx model_keywords/contact_pair.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

from cae.enums import ContactType
from cae.mesh.surface import ElementSurface
from cae.contact.surface_interaction import SurfaceInteraction
from cae._utils import f2s


@dataclass
class ContactPair:
    """
    接触对。

    定义两个表面之间的接触关系。

    Args:
        interaction: SurfaceInteraction 实例
        type: 接触类型（NODE_TO_SURFACE / SURFACE_TO_SURFACE / MORTAR 等）
        dep_surf: 从表面（Dependent Surface），可以是节点表面或单元面表面
        ind_surf: 主表面（Independent Surface），必须是单元面表面
        small_sliding: 是否使用小滑移（仅 NODE_TO_SURFACE 支持）
        adjust: 节点调整（True/False 或节点集名称或数值公差）
        name: 接触对名称
        desc: 描述文本

    Example:
        >>> from cae.contact import SurfaceInteraction, SurfaceBehavior, ContactPair
        >>> from cae.enums import ContactType, PressureOverclosure
        >>> from cae.mesh.surface import ElementSurface
        >>>
        >>> si = SurfaceInteraction(name="INT1")
        >>> sb = SurfaceBehavior(pressure_overclosure=PressureOverclosure.EXPONENTIAL, c0=0.01, p0=1e6)
        >>> surf_dep = ElementSurface(name="DEP_SURF", element_faces={(1, 1), (2, 1)})
        >>> surf_ind = ElementSurface(name="IND_SURF", element_faces={(3, 2), (4, 2)})
        >>>
        >>> cp = ContactPair(
        ...     interaction=si,
        ...     type=ContactType.NODE_TO_SURFACE,
        ...     dep_surf=surf_dep,
        ...     ind_surf=surf_ind,
        ...     small_sliding=True
        ... )
    """

    interaction: SurfaceInteraction
    """SurfaceInteraction 实例"""
    type: ContactType
    """接触类型"""
    dep_surf: ElementSurface
    """从表面（slave surface）"""
    ind_surf: ElementSurface
    """主表面（master surface）"""
    small_sliding: bool = False
    """是否使用小滑移（仅 NODE_TO_SURFACE 支持）"""
    adjust: Optional[Union[bool, str, float]] = None
    """节点调整：True/False、节点集名称字符串、或数值公差"""
    name: str = ""
    """接触对名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*CONTACT PAIR"
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

        # 主表面必须是单元面
        if self.ind_surf.element_faces is None or len(self.ind_surf.element_faces) == 0:
            raise ValueError("主表面(ind_surf)必须是单元面表面")

        # SURFACE_TO_SURFACE 时从表面也必须是单元面
        if self.type == ContactType.SURFACE_TO_SURFACE:
            if self.dep_surf.element_faces is None or len(self.dep_surf.element_faces) == 0:
                raise ValueError("SURFACE_TO_SURFACE 接触时从表面(dep_surf)必须是单元面表面")

        # small_sliding 仅 NODE_TO_SURFACE 支持
        if self.small_sliding and self.type != ContactType.NODE_TO_SURFACE:
            raise ValueError("small_sliding 仅在 NODE_TO_SURFACE 接触类型时有效")

        # adjust 验证
        if self.adjust is not None:
            if isinstance(self.adjust, str) and len(self.adjust) == 0:
                raise ValueError("adjust 节点集名称不能为空")
            if isinstance(self.adjust, (int, float)) and self.adjust < 0:
                raise ValueError(f"adjust 公差必须 >= 0，当前值 {self.adjust}")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # ContactPair 行
        line = f"*CONTACT PAIR,INTERACTION={self.interaction.name},TYPE={self.type.value}"
        if self.small_sliding:
            line += ",SMALL SLIDING"
        if self.adjust is not None:
            if isinstance(self.adjust, bool):
                if not self.adjust:
                    line += ",ADJUST=NO"
            elif isinstance(self.adjust, str):
                line += f",ADJUST={self.adjust}"
            else:  # float/int
                line += f",ADJUST={f2s(self.adjust)}"
        if self.name:
            line += f",NAME={self.name}"
        lines.append(line)

        # 表面名称行
        lines.append(f"{self.dep_surf.name},{self.ind_surf.name}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
