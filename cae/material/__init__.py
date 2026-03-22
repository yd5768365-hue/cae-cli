"""
Material 材料模块

提供材料属性定义，包括弹性、塑性、超弹性等。

类层次：
  Elastic       # 弹性材料
  Plastic       # 塑性材料
  CyclicHardening  # 循环硬化
  HyperElastic  # 超弹性材料

参考 pygccx model_keywords/elastic.py, plastic.py, hyperelastic.py 设计
"""
from __future__ import annotations

from cae.material.elastic import Elastic
from cae.material.plastic import Plastic, CyclicHardening
from cae.material.hyperelastic import HyperElastic

__all__ = [
    "Elastic",
    "Plastic",
    "CyclicHardening",
    "HyperElastic",
]
