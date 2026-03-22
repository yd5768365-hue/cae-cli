"""
表面相互作用 SurfaceInteraction

定义接触面的物理行为开始。

CalculiX 中 *SURFACE INTERACTION 用于定义表面相互作用，
后续跟 *SURFACE BEHAVIOR 和 *FRICTION。

参考 pygccx model_keywords/surface_interaction.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SurfaceInteraction:
    """
    表面相互作用。

    定义接触面相互作用的开始，必须与 SurfaceBehavior 和/或 Friction 配合使用。

    Args:
        name: 表面相互作用名称（最多 80 字符）
        desc: 描述文本（写入 INP 文件）
    """

    name: str
    """表面相互作用名称（最多 80 字符）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*SURFACE INTERACTION"
    """关键词名称"""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "name" and len(value) > 80:
            raise ValueError(f"name 最多 80 字符，当前 {len(value)} 字符")
        super().__setattr__(name, value)

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = [f"*SURFACE INTERACTION,NAME={self.name}"]
        if self.desc:
            lines.append(f"** {self.desc}")
        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
