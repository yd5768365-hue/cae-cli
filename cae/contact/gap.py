"""
间隙单元 Gap

定义节点之间的间隙约束。

CalculiX 中 *GAP 用于定义间隙单元，模拟两个表面之间的接触间隙。

参考 pygccx model_keywords/gap.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from cae._utils import f2s


@dataclass
class Gap:
    """
    间隙单元。

    定义两个节点之间的间隙约束，用于模拟接触问题中的间隙。

    Args:
        node_a: 节点 A
        node_b: 节点 B（与节点 A 形成间隙对）
        clearance: 初始间隙距离（默认为 0，表示理想接触）
        c0: 特征间隙（用于指数模型）
        mu: 摩擦系数
        tens: 张力传递系数（0-1 之间）
        name: 间隙名称
        desc: 描述文本

    Example:
        >>> from cae.contact import Gap
        >>>
        >>> # 基本间隙
        >>> gap = Gap(node_a=1, node_b=2, clearance=0.0)
        >>>
        >>> # 带摩擦的间隙
        >>> gap = Gap(node_a=1, node_b=2, clearance=0.1, mu=0.2, tens=0.5)
    """

    node_a: int
    """节点 A"""
    node_b: int
    """节点 B"""
    clearance: float = 0.0
    """初始间隙距离（0 表示理想接触）"""
    c0: Optional[float] = None
    """特征间隙（用于指数模型）"""
    mu: Optional[float] = None
    """摩擦系数"""
    tens: Optional[float] = None
    """张力传递系数（0-1）"""
    name: str = ""
    """间隙名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*GAP"
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

        if self.node_a < 1:
            raise ValueError(f"node_a 必须 >= 1，当前值 {self.node_a}")
        if self.node_b < 1:
            raise ValueError(f"node_b 必须 >= 1，当前值 {self.node_b}")
        if self.node_a == self.node_b:
            raise ValueError("node_a 和 node_b 不能相同")

        if self.clearance < 0:
            raise ValueError(f"clearance 必须 >= 0，当前值 {self.clearance}")

        if self.c0 is not None and self.c0 <= 0:
            raise ValueError(f"c0 必须 > 0，当前值 {self.c0}")

        if self.mu is not None and self.mu < 0:
            raise ValueError(f"mu 必须 >= 0，当前值 {self.mu}")

        if self.tens is not None and not (0 <= self.tens <= 1):
            raise ValueError(f"tens 必须在 0-1 之间，当前值 {self.tens}")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # GAP 行
        parts = [f"*GAP"]
        if self.name:
            parts.append(f"NAME={self.name}")
        if self.c0 is not None:
            parts.append(f"C0={f2s(self.c0)}")
        if self.mu is not None:
            parts.append(f"MU={f2s(self.mu)}")
        if self.tens is not None:
            parts.append(f"TENS={f2s(self.tens)}")
        if self.desc:
            parts.append(f"DESCRIPTION={self.desc}")

        lines.append(",".join(parts))

        # 节点对和间隙值行
        lines.append(f"{self.node_a},{self.node_b},{f2s(self.clearance)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class GapUnit:
    """
    间隙单元（单元方式）。

    基于单元定义间隙，通过单元 ID 和面索引引用。

    Args:
        elem_no: 单元编号
        face_no: 面编号
        clearance: 初始间隙距离
        c0: 特征间隙
        mu: 摩擦系数
        tens: 张力传递系数
        name: 间隙名称
        desc: 描述文本

    Example:
        >>> from cae.contact import GapUnit
        >>>
        >>> gap = GapUnit(elem_no=1, face_no=3, clearance=0.0)
    """

    elem_no: int
    """单元编号"""
    face_no: int
    """面编号"""
    clearance: float = 0.0
    """初始间隙距离"""
    c0: Optional[float] = None
    """特征间隙"""
    mu: Optional[float] = None
    """摩擦系数"""
    tens: Optional[float] = None
    """张力传递系数"""
    name: str = ""
    """间隙名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*GAP"
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

        if self.elem_no < 1:
            raise ValueError(f"elem_no 必须 >= 1，当前值 {self.elem_no}")
        if self.face_no < 1:
            raise ValueError(f"face_no 必须 >= 1，当前值 {self.face_no}")
        if self.clearance < 0:
            raise ValueError(f"clearance 必须 >= 0，当前值 {self.clearance}")
        if self.c0 is not None and self.c0 <= 0:
            raise ValueError(f"c0 必须 > 0，当前值 {self.c0}")
        if self.mu is not None and self.mu < 0:
            raise ValueError(f"mu 必须 >= 0，当前值 {self.mu}")
        if self.tens is not None and not (0 <= self.tens <= 1):
            raise ValueError(f"tens 必须在 0-1 之间，当前值 {self.tens}")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # GAP 行
        parts = ["*GAP"]
        if self.name:
            parts.append(f"NAME={self.name}")
        if self.c0 is not None:
            parts.append(f"C0={f2s(self.c0)}")
        if self.mu is not None:
            parts.append(f"MU={f2s(self.mu)}")
        if self.tens is not None:
            parts.append(f"TENS={f2s(self.tens)}")
        if self.desc:
            parts.append(f"DESCRIPTION={self.desc}")

        lines.append(",".join(parts))

        # 单元、面和间隙值行
        lines.append(f"{self.elem_no},{self.face_no},{f2s(self.clearance)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
