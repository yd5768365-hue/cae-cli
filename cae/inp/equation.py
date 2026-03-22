"""
方程约束 Equation

定义线性方程约束关系。

CalculiX 中 *EQUATION 用于定义节点自由度之间的线性方程约束。

参考 pygccx model_keywords/equation.py 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from cae._utils import f2s


@dataclass
class EquationTerm:
    """
    方程约束的单个项。

    定义一个系数乘以节点自由度。

    Args:
        node_id: 节点编号
        dof: 自由度（1-6）
        coefficient: 系数

    Example:
        >>> term = EquationTerm(node_id=1, dof=1, coefficient=1.0)
    """

    node_id: int
    """节点编号"""
    dof: int
    """自由度（1-6）"""
    coefficient: float
    """系数"""

    def __post_init__(self):
        if self.node_id < 1:
            raise ValueError(f"node_id 必须 >= 1，当前值 {self.node_id}")
        if not 1 <= self.dof <= 6:
            raise ValueError(f"dof 必须在 1-6 之间，当前值 {self.dof}")
        if self.coefficient == 0:
            raise ValueError("coefficient 不能为 0")


@dataclass
class Equation:
    """
    方程约束。

    定义节点自由度之间的线性方程约束：
    sum(coef_i * u_j(dof_i)) = 0

    Args:
        terms: 方程项列表，至少需要 2 个项
        name: 方程名称
        desc: 描述文本

    Example:
        >>> from cae.inp.equation import Equation, EquationTerm
        >>>
        >>> # 强制两节点相同位移
        >>> eq = Equation(terms=[
        ...     EquationTerm(node_id=1, dof=1, coefficient=1.0),
        ...     EquationTerm(node_id=2, dof=1, coefficient=-1.0),
        ... ])
        >>>
        >>> # 简化形式（使用列表元组）
        >>> eq = Equation(terms=[
        ...     (1, 1, 1.0),   # 节点1, DOF1, 系数1.0
        ...     (2, 1, -1.0),  # 节点2, DOF1, 系数-1.0
        ... ])
    """

    terms: Sequence[EquationTerm | tuple[int, int, float]]
    """方程项列表"""
    name: str = ""
    """方程名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*EQUATION"
    """关键词名称"""

    _is_initialized: bool = field(init=False, default=False)

    def __post_init__(self):
        # 转换 tuple 为 EquationTerm
        converted_terms: list[EquationTerm] = []
        for i, term in enumerate(self.terms):
            if isinstance(term, tuple):
                if len(term) != 3:
                    raise ValueError(f"第 {i+1} 项元组必须包含 3 个元素 (node_id, dof, coefficient)")
                converted_terms.append(EquationTerm(node_id=term[0], dof=term[1], coefficient=term[2]))
            else:
                converted_terms.append(term)
        object.__setattr__(self, 'terms', converted_terms)

        object.__setattr__(self, '_is_initialized', True)
        self._validate()

    def _validate(self) -> None:
        if not self._is_initialized:
            return

        if len(self.terms) < 2:
            raise ValueError(f"方程至少需要 2 个项，当前只有 {len(self.terms)} 个")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # EQUATION 行
        if self.name:
            lines.append(f"*EQUATION,NAME={self.name}")
        else:
            lines.append("*EQUATION")
        if self.desc:
            lines.append(f"** {self.desc}")

        # 第一行：项数量
        lines.append(str(len(self.terms)))

        # 后续行：节点 ID, DOF, 系数
        for term in self.terms:
            lines.append(f"{term.node_id},{term.dof},{f2s(term.coefficient)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class EquationFactory:
    """
    方程约束工厂方法。

    提供常用方程约束的便捷创建方法。
    """

    @staticmethod
    def equal_dof(
        node_ids: Sequence[int],
        dof: int,
        name: str = "",
        desc: str = "",
    ) -> Equation:
        """
        强制多个节点的同一自由度相等。

        Args:
            node_ids: 节点 ID 列表
            dof: 自由度（1-6）
            name: 方程名称
            desc: 描述文本

        Returns:
            Equation: 方程约束

        Example:
            >>> # 强制节点 1, 2, 3 的 UX 相等
            >>> eq = EquationFactory.equal_dof([1, 2, 3], dof=1)
        """
        if len(node_ids) < 2:
            raise ValueError("至少需要 2 个节点")

        # 第一个节点系数为 1，其余节点系数为 -1
        terms = [EquationTerm(node_id=node_ids[0], dof=dof, coefficient=1.0)]
        for nid in node_ids[1:]:
            terms.append(EquationTerm(node_id=nid, dof=dof, coefficient=-1.0))

        eq = Equation(terms=terms, name=name, desc=desc or f"强制节点 {node_ids} 的 DOF {dof} 相等")
        return eq

    @staticmethod
    def rigid_link(
        node_a: int,
        node_b: int,
        dof: int = 0,
        name: str = "",
        desc: str = "",
    ) -> list[Equation]:
        """
        创建刚体连接（6 个自由度全部耦合）。

        强制两节点保持刚体连接，即所有自由度相等。

        Args:
            node_a: 节点 A
            node_b: 节点 B
            dof: 要耦合的自由度（0 表示全部 6 个自由度）
            name: 方程名称前缀
            desc: 描述文本

        Returns:
            list[Equation]: 6 个方程约束（如果 dof=0）

        Example:
            >>> # 节点 1 和 2 完全刚体连接
            >>> eqs = EquationFactory.rigid_link(1, 2)
        """
        if node_a < 1 or node_b < 1:
            raise ValueError("节点 ID 必须 >= 1")
        if node_a == node_b:
            raise ValueError("两个节点不能相同")

        if dof == 0:
            # 所有 6 个自由度
            dofs = range(1, 7)
        elif 1 <= dof <= 6:
            dofs = [dof]
        else:
            raise ValueError(f"dof 必须在 1-6 之间或 0（全部），当前值 {dof}")

        equations = []
        for i, d in enumerate(dofs):
            eq = Equation(
                terms=[
                    EquationTerm(node_id=node_a, dof=d, coefficient=1.0),
                    EquationTerm(node_id=node_b, dof=d, coefficient=-1.0),
                ],
                name=f"{name}_DOF{d}" if name else "",
                desc=desc or f"刚体连接：节点 {node_a} - 节点 {node_b}, DOF {d}",
            )
            equations.append(eq)

        return equations

    @staticmethod
    def linear_relation(
        terms: Sequence[tuple[int, int, float]],
        name: str = "",
        desc: str = "",
    ) -> Equation:
        """
        创建线性方程约束。

        Args:
            terms: [(node_id, dof, coefficient), ...] 形式的项列表
            name: 方程名称
            desc: 描述文本

        Returns:
            Equation: 方程约束

        Example:
            >>> # u1(1) + 2*u2(1) - 3*u3(1) = 0
            >>> eq = EquationFactory.linear_relation([
            ...     (1, 1, 1.0),
            ...     (2, 1, 2.0),
            ...     (3, 1, -3.0),
            ... ])
        """
        if len(terms) < 2:
            raise ValueError("至少需要 2 个项")

        equation_terms = [
            EquationTerm(node_id=t[0], dof=t[1], coefficient=t[2])
            for t in terms
        ]
        return Equation(terms=equation_terms, name=name, desc=desc)
