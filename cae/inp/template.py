"""
INP 模板生成模块 — 使用 Jinja2 渲染参数化 .inp 文件
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import jinja2


@dataclass
class TemplateParams:
    """模板参数"""
    # 通用参数
    title: str = "Generated Model"
    material_name: str = "STEEL"
    E: float = 210000.0  # 弹性模量 (MPa)
    density: float = 7.85e-9  # 密度 (ton/mm³)
    thickness: float = 1.0  # 板厚 (mm)

    # 梁参数
    L: float = 100.0  # 梁长度 (mm)
    width: float = 10.0  # 梁宽 (mm)
    height: float = 20.0  # 梁高 (mm)
    n_nodes: int = 11  # 节点数
    n_elements: int = 10  # 单元数
    load_type: str = "force"  # force / moment
    load_value: float = 1000.0  # 载荷值

    # 板参数
    Lx: float = 100.0  # 板长 (mm)
    Ly: float = 50.0  # 板宽 (mm)
    n_x: int = 10  # X方向节点数
    n_y: int = 5  # Y方向节点数
    pressure: float = 1.0  # 均匀压力 (MPa)


@dataclass
class TemplateInfo:
    """模板信息"""
    name: str
    description: str
    params: list[tuple[str, str, str]]  # (name, type, description)
    file: Path


_TEMPLATES_DIR = Path(__file__).parent / "templates"

# 内置模板列表
_BUILTIN_TEMPLATES: list[TemplateInfo] = [
    TemplateInfo(
        name="cantilever_beam",
        description="悬臂梁 (B32 梁单元)",
        params=[
            ("title", "str", "模型标题"),
            ("material_name", "str", "材料名称"),
            ("E", "float", "弹性模量 (MPa)"),
            ("density", "float", "密度 (ton/mm³)"),
            ("L", "float", "梁长度 (mm)"),
            ("width", "float", "梁宽 (mm)"),
            ("height", "float", "梁高 (mm)"),
            ("n_nodes", "int", "节点数"),
            ("load_type", "str", "载荷类型 (force/moment)"),
            ("load_value", "float", "载荷值"),
        ],
        file=_TEMPLATES_DIR / "cantilever_beam.inp.j2",
    ),
    TemplateInfo(
        name="flat_plate",
        description="平板 (S4 壳单元，四角固支)",
        params=[
            ("title", "str", "模型标题"),
            ("material_name", "str", "材料名称"),
            ("E", "float", "弹性模量 (MPa)"),
            ("density", "float", "密度 (ton/mm³)"),
            ("Lx", "float", "板长 (mm)"),
            ("Ly", "float", "板宽 (mm)"),
            ("thickness", "float", "板厚 (mm)"),
            ("n_x", "int", "X方向节点数"),
            ("n_y", "int", "Y方向节点数"),
            ("load_type", "str", "载荷类型 (pressure/force)"),
            ("pressure", "float", "均匀压力 (MPa)"),
            ("load_value", "float", "集中载荷值 (N)"),
        ],
        file=_TEMPLATES_DIR / "flat_plate.inp.j2",
    ),
]


def list_templates() -> list[TemplateInfo]:
    """返回所有可用模板"""
    return _BUILTIN_TEMPLATES


def get_template(name: str) -> Optional[TemplateInfo]:
    """按名称查找模板"""
    for t in _BUILTIN_TEMPLATES:
        if t.name == name:
            return t
    return None


def render_template(
    name: str,
    params: Optional[dict] = None,
    **kwargs,
) -> str:
    """
    渲染指定模板

    Args:
        name: 模板名称
        params: 参数字典
        **kwargs: 其他参数（优先级高于 params）

    Returns:
        渲染后的 INP 文件内容
    """
    template_info = get_template(name)
    if template_info is None:
        raise ValueError(f"未知模板: {name}")

    # 合并参数
    merged = {}
    if params:
        merged.update(params)
    merged.update(kwargs)

    # 渲染
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_info.file.parent),
        keep_trailing_newline=True,
    )
    tmpl = env.get_template(template_info.file.name)
    return tmpl.render(**merged)


def render_to_file(
    name: str,
    output: Path,
    params: Optional[dict] = None,
    **kwargs,
) -> Path:
    """
    渲染模板并写入文件

    Args:
        name: 模板名称
        output: 输出文件路径
        params: 参数字典
        **kwargs: 其他参数

    Returns:
        输出文件路径
    """
    content = render_template(name, params, **kwargs)
    with open(output, "w", encoding="utf-8") as f:
        f.write(content)
    return output
