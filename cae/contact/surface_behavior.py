"""
表面行为 SurfaceBehavior

定义接触面的压力-间隙模型。

CalculiX 中 *SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=... 用于定义
法向接触行为，包括指数模型、线性模型、表格模型和绑定模型。

参考 pygccx model_keywords/surface_behavior.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional, Any
from collections.abc import Sequence

from cae.enums import PressureOverclosure
from cae._utils import f2s


@dataclass
class SurfaceBehavior:
    """
    表面行为（压力-间隙模型）。

    定义接触面的法向行为。

    Args:
        pressure_overclosure: 压力-间隙模型类型
        c0: 特征间隙距离
            - EXPONENTIAL: 压力衰减到 1% p0 时的间隙距离
            - LINEAR: 弹簧接触生成的间隙因子（默认 1e-3）
        p0: 零间隙时的接触压力（仅 EXPONENTIAL）
        k: 压力-间隙曲线斜率（LINEAR 和 TIED 必须）
        sig_inf: 大间隙时的张力值（LINEAR node-to-face 必须）
        table: 压力-间隙表格数据（TABULAR 必须），[[overclosure, pressure], ...]
        desc: 描述文本

    Example:
        >>> # 指数模型
        >>> sb = SurfaceBehavior(
        ...     pressure_overclosure=PressureOverclosure.EXPONENTIAL,
        ...     c0=0.01, p0=1e6
        ... )
        >>> # 线性模型
        >>> sb = SurfaceBehavior(
        ...     pressure_overclosure=PressureOverclosure.LINEAR,
        ...     k=1e8, sig_inf=1e3
        ... )
    """

    pressure_overclosure: PressureOverclosure
    """压力-间隙模型类型"""
    c0: Optional[float] = field(default=None)
    """特征间隙距离"""
    p0: Optional[float] = field(default=None)
    """零间隙时的接触压力（仅 EXPONENTIAL）"""
    k: Optional[float] = field(default=None)
    """压力-间隙曲线斜率（LINEAR 和 TIED 必须）"""
    sig_inf: Optional[float] = field(default=None)
    """大间隙时的张力值（LINEAR node-to-face 必须）"""
    table: Optional[Sequence[Sequence[float]]] = field(default=None)
    """压力-间隙表格数据（TABULAR 必须）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*SURFACE BEHAVIOR"
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

        po = self.pressure_overclosure

        if po == PressureOverclosure.EXPONENTIAL:
            if self.c0 is None:
                raise ValueError("EXPONENTIAL 模型必须指定 c0")
            if self.c0 <= 0:
                raise ValueError(f"c0 必须 > 0，当前值 {self.c0}")
            if self.p0 is None:
                raise ValueError("EXPONENTIAL 模型必须指定 p0")
            if self.p0 <= 0:
                raise ValueError(f"p0 必须 > 0，当前值 {self.p0}")

        if po == PressureOverclosure.LINEAR:
            if self.k is None:
                raise ValueError("LINEAR 模型必须指定 k")
            if self.k <= 0:
                raise ValueError(f"k 必须 > 0，当前值 {self.k}")
            if self.sig_inf is not None and self.sig_inf <= 0:
                raise ValueError(f"sig_inf 必须 > 0，当前值 {self.sig_inf}")
            if self.c0 is not None and self.c0 <= 0:
                raise ValueError(f"c0 必须 > 0，当前值 {self.c0}")

        if po == PressureOverclosure.TABULAR:
            if self.table is None:
                raise ValueError("TABULAR 模型必须指定 table")

        if po == PressureOverclosure.TIED:
            if self.k is None:
                raise ValueError("TIED 模型必须指定 k")
            if self.k <= 0:
                raise ValueError(f"k 必须 > 0，当前值 {self.k}")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = [f"*SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE={self.pressure_overclosure.value}"]
        if self.desc:
            lines.append(f"** {self.desc}")

        po = self.pressure_overclosure

        if po == PressureOverclosure.EXPONENTIAL:
            lines.append(f"{f2s(self.c0)},{f2s(self.p0)}")

        elif po == PressureOverclosure.LINEAR:
            parts = [f2s(self.k)]
            if self.sig_inf is not None:
                parts.append(f2s(self.sig_inf))
            if self.c0 is not None:
                parts.append(f2s(self.c0))
            lines.append(",".join(parts))

        elif po == PressureOverclosure.TABULAR:
            for row in self.table:  # type: ignore
                lines.append(",".join(f2s(x) for x in row))

        elif po == PressureOverclosure.TIED:
            lines.append(f2s(self.k))

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
