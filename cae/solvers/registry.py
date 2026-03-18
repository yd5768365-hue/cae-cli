# 求解器注册表
"""
求解器注册表
管理所有可用求解器，提供实例化和查询接口。
"""
from __future__ import annotations

from typing import Optional

from .base import BaseSolver
from .calculix import CalculixSolver

# 求解器注册表
SOLVERS: dict[str, type[BaseSolver]] = {
    "calculix": CalculixSolver,
}


def get_solver(name: str) -> BaseSolver:
    """
    根据名称获取求解器实例。

    Args:
        name: 求解器名称（如 "calculix"）

    Returns:
        求解器实例

    Raises:
        ValueError: 如果求解器名称不存在
    """
    key = name.lower()
    if key not in SOLVERS:
        available = ", ".join(SOLVERS.keys())
        raise ValueError(f"未知求解器 '{name}'，可用求解器: {available}")
    return SOLVERS[key]()


def list_solvers() -> list[dict]:
    """
    列出所有已注册求解器信息。

    Returns:
        求解器信息列表，每项包含 name, installed, version, formats, description
    """
    result = []
    for name, cls in SOLVERS.items():
        solver = cls()
        result.append({
            "name": name,
            "installed": solver.check_installation(),
            "version": solver.get_version(),
            "formats": solver.supported_formats(),
            "description": solver.description,
        })
    return result
