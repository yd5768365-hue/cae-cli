"""
超弹性材料 HyperElastic

定义材料的超弹性属性（不可压缩或几乎不可压缩橡胶材料）。

CalculiX 中 *HYPERELASTIC 用于定义超弹性材料参数。

支持的模型：
- ARRUDA-BOYCE
- MOONEY-RIVLIN
- NEO HOOKE
- OGDEN (N=1,2,3,4)
- POLYNOMIAL (N=1,2,3)
- REDUCED POLYNOMIAL (N=1,2,3)
- YEOH

参考 pygccx model_keywords/hyperelastic.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from cae.enums import HyperElasticType
from cae._utils import f2s


# 各超弹性类型所需的参数数量
_HYPERELASTIC_PARAM_COUNTS = {
    HyperElasticType.ARRUDA_BOYCE: 3,      # C1, C2, D1
    HyperElasticType.MOONEY_RIVLIN: 3,     # C10, C01, D1
    HyperElasticType.NEO_HOOKE: 2,         # C10, D1
    HyperElasticType.OGDEN_1: 3,           # mu1, alpha1, D1
    HyperElasticType.OGDEN_2: 6,           # mu1, alpha1, mu2, alpha2, D1, D2
    HyperElasticType.OGDEN_3: 9,           # mu1-3, alpha1-3, D1-3
    HyperElasticType.OGDEN_4: 9,           # mu1-4, alpha1-4, D1, D2
    HyperElasticType.POLYNOMIAL_1: 3,      # C10, C01, D1
    HyperElasticType.POLYNOMIAL_2: 7,      # C10, C01, C20, C11, C02, D1, D2
    HyperElasticType.POLYNOMIAL_3: 12,     # C10, C01, C20, C11, C02, C30, C21, C12, C03, D1, D2, D3
    HyperElasticType.REDUCED_POLYNOMIAL_1: 2,  # C10, D1
    HyperElasticType.REDUCED_POLYNOMIAL_2: 4,  # C10, C20, D1, D2
    HyperElasticType.REDUCED_POLYNOMIAL_3: 6,  # C10, C20, C30, D1, D2, D3
    HyperElasticType.YEOH: 6,             # C10, C20, C30, D1, D2, D3
}


@dataclass
class HyperElastic:
    """
    超弹性材料。

    定义材料的超弹性属性（用于橡胶等不可压缩材料）。

    参数数量取决于类型：
    - ARRUDA_BOYCE: C1, C2, D1（3个）
    - MOONEY_RIVLIN: C10, C01, D1（3个）
    - NEO_HOOKE: C10, D1（2个）
    - OGDEN_1: mu1, alpha1, D1（3个）
    - OGDEN_2: mu1, alpha1, mu2, alpha2, D1, D2（6个）
    - OGDEN_3: mu1-3, alpha1-3, D1-3（9个）
    - OGDEN_4: mu1-4, alpha1-4, D1, D2（9个）
    - POLYNOMIAL_1: C10, C01, D1（3个）
    - POLYNOMIAL_2: C10, C01, C20, C11, C02, D1, D2（7个）
    - REDUCED_POLYNOMIAL_1: C10, D1（2个）
    - REDUCED_POLYNOMIAL_2: C10, C20, D1, D2（4个）

    Args:
        hyperelastic_params: 超弹性参数元组（数量取决于类型）
        hyperelastic_type: 超弹性类型
        temp: 温度（用于温度依赖参数）
        name: 材料名称
        desc: 描述文本

    Example:
        >>> # Mooney-Rivlin 模型（橡胶常用）
        >>> h = HyperElastic(
        ...     hyperelastic_params=(0.5, 0.1, 0.01),
        ...     hyperelastic_type=HyperElasticType.MOONEY_RIVLIN
        ... )
        >>>
        >>> # Neo-Hooke 模型
        >>> h = HyperElastic(
        ...     hyperelastic_params=(0.8, 0.001),
        ...     hyperelastic_type=HyperElasticType.NEO_HOOKE
        ... )
        >>>
        >>> # 添加温度依赖
        >>> h.add_hyperelastic_params_for_temp(350, (0.6, 0.12, 0.015))
    """

    hyperelastic_params: tuple[float, ...]
    """第一组超弹性参数"""
    hyperelastic_type: HyperElasticType = HyperElasticType.MOONEY_RIVLIN
    """超弹性类型"""
    temp: float = 294.0
    """第一组参数的温度"""
    name: str = ""
    """材料名称（用于识别）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*HYPERELASTIC"
    """关键词名称"""

    _params_for_temps: list[tuple] = field(default_factory=list, init=False)

    def __post_init__(self):
        self.add_hyperelastic_params_for_temp(self.temp, *self.hyperelastic_params)

    def add_hyperelastic_params_for_temp(
        self, temp: float, *hyperelastic_params: float
    ) -> None:
        """
        添加温度依赖的超弹性参数。

        Args:
            temp: 温度值
            *hyperelastic_params: 超弹性参数（数量取决于类型）

        Raises:
            ValueError: 参数数量不匹配时
        """
        req_len = _HYPERELASTIC_PARAM_COUNTS[self.hyperelastic_type]
        if len(hyperelastic_params) != req_len:
            raise ValueError(
                f"{self.hyperelastic_type.name} 类型需要 {req_len} 个参数，"
                f"当前 {len(hyperelastic_params)} 个"
            )
        # 存储：(参数..., 温度)
        self._params_for_temps.append(hyperelastic_params + (temp,))

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # 标题行
        line = f"*HYPERELASTIC,{self.hyperelastic_type.value}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 参数行（每行最多8个值）
        n_per_line = 8
        for params in self._params_for_temps:
            param_list = list(params)
            temp = param_list[-1]
            data = param_list[:-1]

            # 分块输出，每块最多8个值
            for i in range(0, len(data), n_per_line):
                chunk = data[i : i + n_per_line]
                line_str = ",".join(f2s(x) for x in chunk)
                # 如果不是最后一块或后面还有数据，添加逗号
                if i + n_per_line < len(data):
                    line_str += ","
                lines.append(line_str)

            # 每组数据的最后一行加上温度
            if temp is not None:
                lines[-1] += f",{f2s(temp)}"

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
