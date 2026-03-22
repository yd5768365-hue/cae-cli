"""
弹性材料 Elastic

定义材料的弹性属性，支持各向同性、正交各向异性等。

CalculiX 中 *ELASTIC 用于定义弹性材料参数，支持温度依赖。

参考 pygccx model_keywords/elastic.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from cae.enums import ElasticType
from cae._utils import f2s


# 各弹性类型所需的参数数量
_ELASTIC_PARAM_COUNTS = {
    ElasticType.ISO: 2,                    # E, nu
    ElasticType.ORTHO: 9,                 # E1, E2, E3, nu12, nu13, nu23, G12, G13, G23
    ElasticType.ENGINEERING_CONSTANTS: 9,  # 同 ORTHO
    ElasticType.ANISO: 21,                # 21个独立弹性常数
}


@dataclass
class Elastic:
    """
    弹性材料。

    定义材料的弹性属性，支持温度依赖。

    参数数量取决于类型：
    - ISO: E, nu（2个）
    - ORTHO / ENGINEERING_CONSTANTS: E1, E2, E3, nu12, nu13, nu23, G12, G13, G23（9个）
    - ANISO: 21个独立弹性常数

    Args:
        elastic_params: 弹性参数元组（数量取决于类型）
        type: 弹性类型（ISO / ORTHO / ENGINEERING_CONSTANTS / ANISO）
        temp: 温度（用于温度依赖参数）
        name: 材料名称
        desc: 描述文本

    Example:
        >>> # 各向同性弹性（钢）
        >>> e = Elastic(elastic_params=(210000, 0.3), type=ElasticType.ISO)
        >>>
        >>> # 添加温度依赖
        >>> e.add_elastic_params_for_temp(500, (190000, 0.3))
    """

    elastic_params: tuple[float, ...]
    """第一组弹性参数"""
    type: ElasticType = ElasticType.ISO
    """弹性类型"""
    temp: float = 294.0
    """第一组参数的温度"""
    name: str = ""
    """材料名称（用于识别）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*ELASTIC"
    """关键词名称"""

    _params_for_temps: list[tuple] = field(default_factory=list, init=False)

    def __post_init__(self):
        self.add_elastic_params_for_temp(self.temp, *self.elastic_params)

    def add_elastic_params_for_temp(
        self, temp: float, *elastic_params: float
    ) -> None:
        """
        添加温度依赖的弹性参数。

        Args:
            temp: 温度值
            *elastic_params: 弹性参数（数量取决于类型）

        Raises:
            ValueError: 参数数量不匹配时
        """
        req_len = _ELASTIC_PARAM_COUNTS[self.type]
        if len(elastic_params) != req_len:
            raise ValueError(
                f"{self.type.name} 类型需要 {req_len} 个参数，"
                f"当前 {len(elastic_params)} 个"
            )
        # 存储：(参数..., 温度)
        self._params_for_temps.append(elastic_params + (temp,))

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # 标题行
        line = "*ELASTIC"
        if self.type != ElasticType.ISO:
            line += f",TYPE={self.type.value}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 参数行（每行最多8个值）
        n_per_line = 8
        for params in self._params_for_temps:
            param_list = list(params)
            temp = param_list[-1]
            data = param_list[:-1]

            for i in range(0, len(data), n_per_line):
                chunk = data[i : i + n_per_line]
                line = ",".join(f2s(x) for x in chunk)
                if i + n_per_line < len(data):
                    line += ","
                lines.append(line)

            # 每组数据的最后一行加上温度
            if temp is not None:
                lines[-1] += f",{f2s(temp)}"

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
