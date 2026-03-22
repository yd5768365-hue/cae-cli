"""
摩擦 Friction

定义接触面的摩擦行为。

CalculiX 中 *FRICTION 用于定义摩擦系数和粘滑斜率。

参考 pygccx model_keywords/friction.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from cae._utils import f2s


@dataclass
class Friction:
    """
    摩擦模型。

    定义接触面的摩擦特性。

    Args:
        mue: 摩擦系数（> 0）
        lam: 粘滑斜率（stick-slope），单位力/体积（> 0）
        desc: 描述文本

    Example:
        >>> friction = Friction(mue=0.2, lam=1e5)
        >>> print(friction)
        *FRICTION
        2.0000000e-01,1.0000000e+05
    """

    mue: float
    """摩擦系数（> 0）"""
    lam: float
    """粘滑斜率（stick-slope），单位力/体积（> 0）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*FRICTION"
    """关键词名称"""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "mue" and value <= 0:
            raise ValueError(f"mue 必须 > 0，当前值 {value}")
        if name == "lam" and value <= 0:
            raise ValueError(f"lam 必须 > 0，当前值 {value}")
        super().__setattr__(name, value)

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = ["*FRICTION"]
        if self.desc:
            lines.append(f"** {self.desc}")
        lines.append(f"{f2s(self.mue)},{f2s(self.lam)}")
        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
