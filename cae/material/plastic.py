"""
塑性材料 Plastic

定义材料的塑性属性，包括硬化规则和温度依赖。

CalculiX 中 *PLASTIC 用于定义塑性材料参数。

参考 pygccx model_keywords/plastic.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from cae.enums import HardeningRule
from cae._utils import f2s


@dataclass
class CyclicHardening:
    """
    循环硬化曲线。

    用于组合硬化（COMBINED）时的各向同性硬化部分。

    Args:
        stress: 屈服应力序列（与 strain 长度相同）
        strain: 等效塑性应变序列（与 stress 长度相同）
        temp: 温度
        name: 名称
        desc: 描述文本

    Example:
        >>> ch = CyclicHardening(
        ...     stress=[200, 300, 400],
        ...     strain=[0, 0.1, 0.3],
        ...     temp=294.0
        ... )
    """

    stress: Sequence[float]
    """屈服应力序列"""
    strain: Sequence[float]
    """等效塑性应变序列"""
    temp: float = 294.0
    """温度"""
    name: str = ""
    """名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*CYCLIC HARDENING"
    """关键词名称"""

    _params_for_temps: list[tuple] = field(default_factory=list, init=False)

    def __post_init__(self):
        self.add_stress_strain_for_temp(self.temp, self.stress, self.strain)

    def add_stress_strain_for_temp(
        self, temp: float, stress: Sequence[float], strain: Sequence[float]
    ) -> None:
        """
        添加温度依赖的应力-应变数据。

        Args:
            temp: 温度
            stress: 屈服应力序列
            strain: 等效塑性应变序列

        Raises:
            ValueError: stress 和 strain 长度不一致时
        """
        if len(stress) != len(strain):
            raise ValueError(
                f"stress 和 strain 长度必须相同，"
                f"当前 stress={len(stress)}, strain={len(strain)}"
            )
        self._params_for_temps.append((temp, tuple(stress), tuple(strain)))

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = ["*CYCLIC HARDENING"]
        if self.desc:
            lines.append(f"** {self.desc}")

        for temp, stress, strain in self._params_for_temps:
            for s, e in zip(stress, strain):
                lines.append(f"{f2s(s)},{f2s(e)},{f2s(temp)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class Plastic(CyclicHardening):
    """
    塑性材料。

    定义材料的塑性属性和硬化规则。

    Args:
        stress: 屈服应力序列（与 strain 长度相同）
        strain: 等效塑性应变序列（与 stress 长度相同）
        temp: 温度
        hardening: 硬化规则（ISOTROPIC / KINEMATIC / COMBINED）
        name: 材料名称
        desc: 描述文本

    Example:
        >>> # 等向硬化
        >>> p = Plastic(
        ...     stress=[200, 250, 300, 350],
        ...     strain=[0, 0.05, 0.15, 0.3],
        ...     hardening=HardeningRule.ISOTROPIC
        ... )
        >>>
        >>> # 组合硬化（需要 CyclicHardening）
        >>> p = Plastic(
        ...     stress=[200, 300, 400],
        ...     strain=[0, 0.1, 0.3],
        ...     hardening=HardeningRule.COMBINED
        ... )
        >>> ch = CyclicHardening(stress=[200, 300], strain=[0, 0.1])
        >>> p.cyclic_hardening = ch
    """

    hardening: HardeningRule = HardeningRule.ISOTROPIC
    """硬化规则"""
    name: str = ""
    """材料名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*PLASTIC"
    """关键词名称"""

    _cyclic_hardening: CyclicHardening | None = field(default=None, init=False, repr=False)

    def set_cyclic_hardening(self, cyclic_hardening: CyclicHardening) -> None:
        """设置循环硬化（用于 COMBINED 硬化）。"""
        self._cyclic_hardening = cyclic_hardening

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # 首先输出 CYCLIC HARDENING（如果存在）
        if self._cyclic_hardening is not None:
            lines.extend(self._cyclic_hardening.to_inp_lines())
            lines.append("")

        # PLASTIC 行
        line = "*PLASTIC"
        if self.hardening != HardeningRule.ISOTROPIC:
            line += f",HARDENING={self.hardening.value}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 应力-应变数据
        for temp, stress, strain in self._params_for_temps:
            for s, e in zip(stress, strain):
                lines.append(f"{f2s(s)},{f2s(e)},{f2s(temp)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
