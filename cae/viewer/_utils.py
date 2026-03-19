# _utils.py
"""
Viewer 模块共享工具函数
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np


# 预编译正则表达式（避免循环中重复编译）
_NUMBER_PATTERN = re.compile(r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?")


def von_mises(stress: np.ndarray) -> np.ndarray:
    """
    从 6 分量 Cauchy/Voigt 应力张量计算 Von Mises 等效应力。

    应力顺序：S11, S22, S33, S12, S13, S23

    Args:
        stress: (N, 6) 的应力数组

    Returns:
        (N,) 的 Von Mises 应力数组
    """
    s11, s22, s33 = stress[:, 0], stress[:, 1], stress[:, 2]
    s12, s13, s23 = stress[:, 3], stress[:, 4], stress[:, 5]
    return np.sqrt(0.5 * (
        (s11 - s22) ** 2 +
        (s22 - s33) ** 2 +
        (s33 - s11) ** 2 +
        6.0 * (s12 ** 2 + s13 ** 2 + s23 ** 2)
    ))


def parse_numbers(line: str) -> list[float]:
    """
    从文本行中解析所有数字（处理科学计数法和连在一起的情况）。

    Args:
        line: 文本行

    Returns:
        解析出的数字列表
    """
    matches = _NUMBER_PATTERN.findall(line)
    numbers = []
    for m in matches:
        try:
            numbers.append(float(m))
        except ValueError:
            pass
    return numbers


def find_frd(results_dir: Path) -> Optional[Path]:
    """
    在目录中查找第一个 .frd 文件。

    Args:
        results_dir: 结果目录

    Returns:
        .frd 文件路径，或 None
    """
    frd_files = sorted(results_dir.glob("*.frd"))
    return frd_files[0] if frd_files else None
