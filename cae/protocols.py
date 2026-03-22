"""
Protocol 接口定义

参考 pygccx/protocols.py 设计，提供运行时检查的接口协议。

Protocol 特点：
- 使用 typing.Protocol 定义接口
- @runtime_checkable 装饰器支持 isinstance() 检查
- 子类只需实现协议方法，无需继承
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable, Iterable


@runtime_checkable
class IKeyword(Protocol):
    """
    关键词协议。

    所有 INP 关键词类（如 Material, Elastic, Cload, Boundary）都应该实现此协议。

    实现要求：
      - keyword_name: str - 关键词名称（含 *，如 "*ELASTIC"）
      - desc: str - 描述文本（可选，用于注释）
      - to_inp_lines() -> list[str] - 转换为 INP 文件行

    Usage:
        def process_keyword(kw: IKeyword) -> None:
            if isinstance(kw, IKeyword):
                print(kw.to_inp_lines())

        # dataclass 自动满足协议
        @dataclass
        class Elastic:
            keyword_name: str = "*ELASTIC"
            params: dict = field(default_factory=dict)
            data: list = field(default_factory=list)

            def to_inp_lines(self) -> list[str]:
                ...

            def __str__(self) -> str:
                return "\\n".join(self.to_inp_lines())
    """

    @property
    def keyword_name(self) -> str:
        """关键词名称（含 *，如 "*ELASTIC", "*BOUNDARY"）。"""
        ...

    @property
    def desc(self) -> str:
        """描述文本，会作为注释写入 INP 文件。"""
        ...

    def to_inp_lines(self) -> list[str]:
        """
        转换为 INP 文件行列表。

        Returns:
            行列表，第一行是关键词行（如 "*ELASTIC,TYPE=ISO"），
            后续行是数据行。
        """
        ...


@runtime_checkable
class IStep(Protocol):
    """
    载荷步协议。

    表示一个分析步骤（如 *STEP ... *END STEP 之间的内容）。

    实现要求：
      - step_keywords: list[IKeyword] - 步内的关键词列表
      - add_step_keywords() - 添加步内关键词

    Usage:
        @dataclass
        class StaticStep:
            nlgeom: bool = False
            step_keywords: list[IKeyword] = field(default_factory=list)

            def add_step_keywords(self, *keywords: IKeyword) -> None:
                self.step_keywords.extend(keywords)
    """

    @property
    def step_keywords(self) -> list[IKeyword]:
        """步内的关键词列表。"""
        ...

    def add_step_keywords(self, *keywords: IKeyword) -> None:
        """
        添加关键词到步内。

        Args:
            *keywords: IKeyword 实例
        """
        ...


@runtime_checkable
class INodeSet(Protocol):
    """
    节点集协议。

    实现要求：
      - name: str - 集合名称
      - ids: set[int] - 节点 ID 集合
    """

    @property
    def name(self) -> str:
        """节点集名称。"""
        ...

    @property
    def ids(self) -> set[int]:
        """节点 ID 集合。"""
        ...


@runtime_checkable
class IElementSet(Protocol):
    """
    单元集协议。

    实现要求：
      - name: str - 集合名称
      - ids: set[int] - 单元 ID 集合
    """

    @property
    def name(self) -> str:
        """单元集名称。"""
        ...

    @property
    def ids(self) -> set[int]:
        """单元 ID 集合。"""
        ...


@runtime_checkable
class ISurface(Protocol):
    """
    表面协议。

    实现要求：
      - name: str - 表面名称
      - write_ccx(buffer: list[str]) - 写入 CCX 输入字符串到 buffer
    """

    @property
    def name(self) -> str:
        """表面名称。"""
        ...

    def write_ccx(self, buffer: list[str]) -> None:
        """
        将 CCX 输入字符串写入 buffer。

        Args:
            buffer: 字符串列表，会被就地修改
        """
        ...


# =============================================================================
# 类型别名
# =============================================================================

Number = int | float
"""数字类型别名。"""

KeywordIterable = Iterable[IKeyword]
"""关键词可迭代对象类型别名。"""
