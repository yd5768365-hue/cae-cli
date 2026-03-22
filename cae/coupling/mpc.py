"""
MPC 多点约束

定义多点约束（Multiple Point Constraints）。

CalculiX 中 *MPC 用于定义节点之间的约束关系。

参考 pygccx model_keywords/mpc.py 设计
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from cae.enums import MpcType


@dataclass
class Mpc:
    """
    MPC（多点约束）。

    定义节点之间的约束关系。

    Args:
        type: MPC 类型（PLANE / STRAIGHT / BEAM / MEANROT / DIST）
        nids: 参与的节点 ID 序列
        name: MPC 名称
        desc: 描述文本

    静态工厂方法：
        - Mpc.meanrot_from_node_set(node_set, n_pilot, name, desc)
        - Mpc.dist_from_3_nodes(n_a, n_b, n_dist, name, desc)
        - Mpc.beam_from_2_nodes(n_1, n_2, name, desc)
        - Mpc.straight_from_node_set(node_set, name, desc)
        - Mpc.plane_from_node_set(node_set, name, desc)

    Example:
        >>> from cae.coupling import Mpc
        >>> from cae.enums import MpcType
        >>>
        >>> # 刚体梁约束
        >>> mpc = Mpc(MpcType.BEAM, nids=[1, 2], name='rigid_beam')
        >>>
        >>> # 使用工厂方法
        >>> mpc = Mpc.beam_from_2_nodes(100, 101, name='pillar_to_slab')
    """

    type: MpcType
    """MPC 类型"""
    nids: Sequence[int]
    """参与的节点 ID 序列"""
    name: str = ""
    """MPC 名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*MPC"
    """关键词名称"""

    def __post_init__(self):
        # 验证节点 ID
        for nid in self.nids:
            if nid < 1:
                raise ValueError(f"节点 ID 必须 >= 1，当前值 {nid}")

        # 类型特定验证
        if self.type == MpcType.BEAM:
            if len(self.nids) != 2:
                raise ValueError(f"BEAM 类型需要恰好 2 个节点，当前 {len(self.nids)} 个")

        elif self.type == MpcType.PLANE:
            if len(self.nids) < 3:
                raise ValueError(f"PLANE 类型需要至少 3 个节点，当前 {len(self.nids)} 个")

        elif self.type == MpcType.STRAIGHT:
            if len(self.nids) < 2:
                raise ValueError(f"STRAIGHT 类型需要至少 2 个节点，当前 {len(self.nids)} 个")

        elif self.type == MpcType.DIST:
            if len(self.nids) != 7:
                raise ValueError(f"DIST 类型需要恰好 7 个节点，当前 {len(self.nids)} 个")

        elif self.type == MpcType.MEANROT:
            if len(self.nids) < 4:
                raise ValueError(f"MEANROT 类型需要至少 4 个节点，当前 {len(self.nids)} 个")

        # MEANROT 和 DIST 的特殊验证
        if self.type in (MpcType.MEANROT, MpcType.DIST):
            # 直接验证每3个连续节点相同（这是最重要的验证）
            n_dep = len(self.nids) - 1  # 最后一个是pilot节点
            if n_dep % 3 != 0:
                raise ValueError(
                    f"{self.type.name} 类型：依赖节点数量 {n_dep} 不是 3 的倍数"
                )
            for i in range(n_dep // 3):
                start, end = 3 * i, 3 * (i + 1)
                if len(set(self.nids[start:end])) != 1:
                    raise ValueError(
                        f"{self.type.name} 类型：连续的 3 个节点必须是相同的，"
                        f"索引 {start} 到 {end} 不满足"
                    )
            # 最后一个节点（pilot）必须只出现 1 次
            if self.nids.count(self.nids[-1]) != 1:
                raise ValueError(
                    f"{self.type.name} 类型：最后一个节点（pilot）必须只出现 1 次"
                )

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        if self.name:
            lines.append(f"*MPC,NAME={self.name}")
        else:
            lines.append("*MPC")
        if self.desc:
            lines.append(f"** {self.desc}")

        # 节点行：类型值 + 节点 ID
        nids = [self.type.value] + list(self.nids)

        # 每行最多 16 个值
        for i in range(0, len(nids), 16):
            temp = nids[i : i + 16]
            lines.append(",".join(map(str, temp)) + ",")

        # 删除最后一行末尾的逗号
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())

    @staticmethod
    def meanrot_from_node_set(
        node_ids: set[int], n_pilot: int, name: str = "", desc: str = ""
    ) -> "Mpc":
        """
        从节点集创建 MEANROT MPC。

        强制参考节点旋转为所有依赖节点旋转的平均值。

        Args:
            node_ids: 依赖节点 ID 集合
            n_pilot: 导向节点 ID
            name: MPC 名称
            desc: 描述文本

        Returns:
            Mpc: MEANROT MPC
        """
        # 每个节点重复3次，最后加导向节点
        nids = [n for nid in sorted(node_ids) for n in [nid] * 3] + [n_pilot]
        return Mpc(MpcType.MEANROT, nids, name, desc)

    @staticmethod
    def dist_from_3_nodes(
        n_a: int, n_b: int, n_dist: int, name: str = "", desc: str = ""
    ) -> "Mpc":
        """
        从 3 个节点创建 DIST MPC（最大距离约束）。

        强制节点 a 和 b 之间的距离不超过节点 dist 定义的值。

        Args:
            n_a: 定义方向的第一个节点
            n_b: 定义方向的第二个节点
            n_dist: 定义最大距离值的节点
            name: MPC 名称
            desc: 描述文本

        Returns:
            Mpc: DIST MPC
        """
        nids = [n_a] * 3 + [n_b] * 3 + [n_dist]
        return Mpc(MpcType.DIST, nids, name, desc)

    @staticmethod
    def beam_from_2_nodes(
        n_1: int, n_2: int, name: str = "", desc: str = ""
    ) -> "Mpc":
        """
        从 2 个节点创建刚体梁 MPC。

        强制两节点保持固定距离（刚性连接）。

        Args:
            n_1: 第一个节点
            n_2: 第二个节点
            name: MPC 名称
            desc: 描述文本

        Returns:
            Mpc: BEAM MPC
        """
        return Mpc(MpcType.BEAM, [n_1, n_2], name, desc)

    @staticmethod
    def straight_from_node_set(
        node_ids: set[int], name: str = "", desc: str = ""
    ) -> "Mpc":
        """
        从节点集创建 STRAIGHT MPC。

        强制所有依赖节点保持在一条直线上。

        Args:
            node_ids: 依赖节点 ID 集合
            name: MPC 名称
            desc: 描述文本

        Returns:
            Mpc: STRAIGHT MPC
        """
        nids = list(node_ids)
        return Mpc(MpcType.STRAIGHT, nids, name, desc)

    @staticmethod
    def plane_from_node_set(
        node_ids: set[int], name: str = "", desc: str = ""
    ) -> "Mpc":
        """
        从节点集创建 PLANE MPC。

        强制所有依赖节点保持在一个平面内。

        Args:
            node_ids: 依赖节点 ID 集合
            name: MPC 名称
            desc: 描述文本

        Returns:
            Mpc: PLANE MPC
        """
        nids = list(node_ids)
        return Mpc(MpcType.PLANE, nids, name, desc)
