"""
Step Keywords 载荷步关键词模块

提供 Step 内使用的载荷、边界条件等关键词类。

类层次：
  Amplitude  # 幅值曲线
  Cload      # 集中载荷
  Dload      # 分布载荷
  Boundary   # 边界条件

参考 pygccx step_keywords/ 设计
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any, Union, Sequence

from cae.enums import LoadOp, DloadType, CouplingType
from cae._utils import f2s


# =============================================================================
# Amplitude 幅值曲线
# =============================================================================

@dataclass
class Amplitude:
    """
    幅值曲线（AMPLITUDE）。

    定义载荷或边界条件相对于时间的幅值变化。

    Args:
        name: 幅值曲线名称
        times: 时间序列（与 amps 长度相同）
        amps: 幅值序列（与 times 长度相同）
        use_total_time: 是否使用总时间
        shift_x: X方向（时间）平移量
        shift_y: Y方向（幅值）平移量
        desc: 描述文本

    Example:
        >>> # 定义一个简单的 ramp 载荷
        >>> amp = Amplitude(name="RAMP1", times=[0, 1, 2], amps=[0, 1, 1])
        >>> # 定义带平移的幅值
        >>> amp = Amplitude(name="SHIFTED", times=[0, 1],
        ...                 amps=[0, 100], shift_x=0.5, shift_y=10)
    """

    name: str
    """幅值曲线名称"""
    times: Sequence[float]
    """时间序列"""
    amps: Sequence[float]
    """幅值序列"""
    use_total_time: bool = False
    """是否使用总时间"""
    shift_x: Optional[float] = None
    """X方向（时间）平移量"""
    shift_y: Optional[float] = None
    """Y方向（幅值）平移量"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*AMPLITUDE"
    """关键词名称"""

    def __post_init__(self):
        if len(self.times) != len(self.amps):
            raise ValueError(
                f"times 和 amps 长度必须相同，"
                f"当前 times={len(self.times)}, amps={len(self.amps)}"
            )
        if len(self.times) < 2:
            raise ValueError("幅值曲线至少需要 2 个数据点")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # AMPLITUDE 行
        line = f"*AMPLITUDE,NAME={self.name}"
        if self.use_total_time:
            line += ",TIME=TOTAL TIME"
        if self.shift_x is not None:
            line += f",SHIFTX={f2s(self.shift_x)}"
        if self.shift_y is not None:
            line += f",SHIFTY={f2s(self.shift_y)}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 数据行
        for t, a in zip(self.times, self.amps):
            lines.append(f"{f2s(t)},{f2s(a)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class Cload:
    """
    集中载荷（CLOAD）。

    在节点上施加集中力或集中位移。

    Args:
        node_ids: 节点 ID 集合或单个节点 ID
        dofs: 自由度字典，key=DOF编号(1-6)，value=幅值
            例如：{3: 1.0} 表示 z 方向 1.0
        op: 操作选项（MOD=修改，NEW=新建）
        amplitude_name: 幅值名称
        time_delay: 时间延迟
        name: 载荷名称
        desc: 描述文本

    Example:
        >>> # 节点 1,2,3 的 z 方向施加 1.0
        >>> c = Cload(node_ids={1, 2, 3}, dofs={3: 1.0})
        >>> # 多个方向
        >>> c = Cload(node_ids=100, dofs={1: 10.0, 2: -5.0, 6: 0.5})
    """

    keyword_name: str = "*CLOAD"
    """关键词名称"""
    node_ids: Union[set[int], int] = field(default_factory=lambda: set())
    """节点 ID 集合或单个节点 ID"""
    dofs: dict[int, float] = field(default_factory=dict)
    """自由度字典，key=DOF编号，value=幅值"""
    op: LoadOp = LoadOp.MOD
    """操作选项"""
    amplitude_name: Optional[str] = None
    """幅值名称"""
    time_delay: Optional[float] = None
    """时间延迟"""
    name: str = ""
    """载荷名称"""
    desc: str = ""

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # CLOAD 行
        line = "*CLOAD"
        if self.op != LoadOp.MOD:
            line += f",OP={self.op.value}"
        if self.amplitude_name:
            line += f",AMPLITUDE={self.amplitude_name}"
        if self.time_delay is not None:
            line += f",TIME DELAY={f2s(self.time_delay)}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 载荷行
        if isinstance(self.node_ids, set):
            nid_list = sorted(self.node_ids)
        elif isinstance(self.node_ids, (list, tuple)):
            nid_list = self.node_ids
        else:
            nid_list = [self.node_ids]

        for nid in nid_list:
            for dof in sorted(self.dofs.keys()):
                mag = self.dofs[dof]
                lines.append(f"{nid},{dof},{f2s(mag)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class Dload:
    """
    分布载荷（DLOAD）。

    在单元或单元集上施加分布载荷。

    Args:
        elset_name: 单元集名称（用于标识施加载荷的区域）
        load_type: 分布载荷类型（GRAV/CENTRIF/NEWTON/P1-P6）
        magnitude: 载荷参数
            - GRAV: (grav_factor, dir_x, dir_y, dir_z)
            - CENTRIF: (omega_sq, point_x, point_y, point_z, dir_x, dir_y, dir_z)
            - NEWTON: 无参数
            - P1-P6: pressure_value
        op: 操作选项
        amplitude_name: 幅值名称
        time_delay: 时间延迟
        name: 载荷名称
        desc: 描述文本

    Example:
        >>> # 重力载荷
        >>> d = Dload(elset_name='EALL', load_type=DloadType.GRAV,
        ...           magnitude=(9.81, 0, 0, -1))
        >>> # 离心力
        >>> d = Dload(elset_name='ROTOR', load_type=DloadType.CENTRIF,
        ...           magnitude=(1000, 0, 0, 0, 0, 0, 1))
        >>> # 面载荷
        >>> d = Dload(elset_name='FACE_SURF', load_type=DloadType.P2,
        ...           magnitude=(-1.0))  # 压力值
    """

    keyword_name: str = "*DLOAD"
    """关键词名称"""
    elset_name: str = ""
    """单元集名称"""
    load_type: DloadType = DloadType.GRAV
    """分布载荷类型"""
    magnitude: tuple[float, ...] = ()
    """载荷参数（取决于 load_type）"""
    op: LoadOp = LoadOp.MOD
    """操作选项"""
    amplitude_name: Optional[str] = None
    """幅值名称"""
    time_delay: Optional[float] = None
    """时间延迟"""
    name: str = ""
    """载荷名称"""
    desc: str = ""

    def __post_init__(self):
        self._validate()

    def _validate(self) -> None:
        if self.time_delay is not None and self.amplitude_name is None:
            raise ValueError("amplitude_name 不能为 None when time_delay is set")

        lt = self.load_type
        mag = self.magnitude

        if lt == DloadType.NEWTON:
            if len(mag) != 0:
                raise ValueError("NEWTON 类型不需要 magnitude 参数")
        elif lt == DloadType.GRAV:
            if len(mag) != 4:
                raise ValueError("GRAV 类型需要 4 个参数 (factor, dx, dy, dz)")
            # 检查方向向量是否归一化
            vector = mag[1:]
            norm_sq = sum(v * v for v in vector)
            if abs(norm_sq - 1.0) > 1e-7:
                raise ValueError(f"GRAV 方向向量必须归一化，当前 norm={norm_sq**0.5}")
        elif lt == DloadType.CENTRIF:
            if len(mag) != 7:
                raise ValueError("CENTRIF 类型需要 7 个参数")
            # 检查旋转轴向量是否归一化
            vector = mag[4:]
            norm_sq = sum(v * v for v in vector)
            if abs(norm_sq - 1.0) > 1e-7:
                raise ValueError(f"CENTRIF 旋转轴向量必须归一化")
        elif lt in (DloadType.P1, DloadType.P2, DloadType.P3,
                    DloadType.P4, DloadType.P5, DloadType.P6):
            if len(mag) != 1:
                raise ValueError(f"Px 类型需要 1 个参数（压力值），当前 {len(mag)} 个")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # DLOAD 行
        line = "*DLOAD"
        if self.op != LoadOp.MOD:
            line += f",OP={self.op.value}"
        if self.amplitude_name:
            line += f",AMPLITUDE={self.amplitude_name}"
        if self.time_delay is not None:
            line += f",TIME DELAY={f2s(self.time_delay)}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 载荷行
        line = f"{self.elset_name},{self.load_type.value}"
        if self.load_type != DloadType.NEWTON:
            line += "," + ",".join(f2s(v) for v in self.magnitude)
        lines.append(line)

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


@dataclass
class Boundary:
    """
    边界条件（BOUNDARY）。

    施加位移约束或速度/加速度边界条件。

    Args:
        node_ids: 节点 ID 集合或单个节点 ID
        dofs: 边界条件字典
            - 固定: key=DOF编号, value=None
            - 给定值: key=DOF编号, value=数值
            DOF: 1-6 = UX, UY, UZ, ROTX, ROTY, ROTZ
        op: 操作选项
        amplitude_name: 幅值名称
        time_delay: 时间延迟
        fixed: 是否冻结前一步变形
        submodel: 是否为子模型
        step: 子模型步选择
        data_set: 子模型数据集选择
        name: 边界条件名称
        desc: 描述文本

    Example:
        >>> # 完全固定
        >>> b = Boundary(node_ids={1, 2, 3}, dofs={1: None, 2: None, 3: None})
        >>> # 固定 + 给定位移
        >>> b = Boundary(node_ids=100, dofs={1: 0, 2: 0, 3: 0.1})  # z 方向 0.1
        >>> # 仅固定某些方向
        >>> b = Boundary(node_ids='NSET_FIXED', dofs={3: None})  # z 方向固定
    """

    node_ids: Union[set[int], int, str]
    """节点 ID 集合、单节点 ID 或节点集名称字符串"""
    dofs: dict[int, Optional[float]]
    """自由度字典，key=DOF编号(1-6)，value=None(固定)或数值"""
    op: LoadOp = LoadOp.MOD
    """操作选项"""
    amplitude_name: Optional[str] = None
    """幅值名称"""
    time_delay: Optional[float] = None
    """时间延迟"""
    fixed: bool = False
    """是否冻结前一步变形"""
    submodel: bool = False
    """是否为子模型"""
    step: Optional[int] = None
    """子模型步选择"""
    data_set: Optional[int] = None
    """子模型数据集选择"""
    name: str = ""
    """边界条件名称"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*BOUNDARY"
    """关键词名称"""

    def __post_init__(self):
        self._validate()

    def _validate(self) -> None:
        if self.time_delay is not None and self.amplitude_name is None:
            raise ValueError("amplitude_name 不能为 None when time_delay is set")
        if self.submodel and self.amplitude_name is not None:
            raise ValueError("submodel 和 amplitude_name 不能同时设置")
        if self.submodel and self.step is None and self.data_set is None:
            raise ValueError("submodel=True 时必须指定 step 或 data_set")
        if not self.submodel and self.step is not None:
            raise ValueError("submodel=False 时 step 必须为 None")
        if not self.submodel and self.data_set is not None:
            raise ValueError("submodel=False 时 data_set 必须为 None")
        if self.step is not None and self.data_set is not None:
            raise ValueError("step 和 data_set 不能同时设置")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # BOUNDARY 行
        line = "*BOUNDARY"
        if self.op != LoadOp.MOD:
            line += f",OP={self.op.value}"
        if self.amplitude_name:
            line += f",AMPLITUDE={self.amplitude_name}"
        if self.time_delay is not None:
            line += f",TIME DELAY={f2s(self.time_delay)}"
        if self.fixed:
            line += ",FIXED"
        if self.submodel:
            line += ",SUBMODEL"
            if self.step is not None:
                line += f",STEP={self.step}"
            if self.data_set is not None:
                line += f",DATA SET={self.data_set}"
        lines.append(line)
        if self.desc:
            lines.append(f"** {self.desc}")

        # 边界条件行
        if isinstance(self.node_ids, str):
            # 节点集名称
            nid_list = [self.node_ids]
        elif isinstance(self.node_ids, set):
            nid_list = sorted(self.node_ids)
        elif isinstance(self.node_ids, (list, tuple)):
            nid_list = self.node_ids
        else:
            nid_list = [self.node_ids]

        for nid in nid_list:
            for dof in sorted(self.dofs.keys()):
                val = self.dofs[dof]
                if val is None:
                    lines.append(f"{nid},{dof}")
                else:
                    lines.append(f"{nid},{dof},{f2s(val)}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())


# =============================================================================
# Coupling 耦合约束
# =============================================================================

@dataclass
class Coupling:
    """
    耦合约束（COUPLING）。

    在参考节点和单元面上定义运动耦合或分布耦合。

    - KINEMATIC: 运动耦合，节点位移与参考节点刚体运动协调
    - DISTRIBUTING: 分布耦合，力/力矩按面积权重分配到参考节点

    Args:
        coupling_type: 耦合类型（DISTRIBUTING 或 KINEMATIC）
        ref_node: 参考节点 ID
        surface_name: 单元面表面名称（通过 *SURFACE 定义）
        name: 耦合约束名称
        first_dof: 第一个自由度（1-6）
        last_dof: 最后一个自由度（可选，默认同 first_dof）
        orientation_name: 局部坐标系名称（可选）
        cyclic_symmetry: 是否循环对称（仅 DISTRIBUTING）
        desc: 描述文本

    Example:
        >>> # 运动耦合
        >>> c = Coupling(
        ...     coupling_type=CouplingType.KINEMATIC,
        ...     ref_node=1000,
        ...     surface_name='FACE_LOAD',
        ...     name='COUP_HEAD',
        ...     first_dof=1,
        ...     last_dof=6
        ... )
        >>> # 分布耦合
        >>> c = Coupling(
        ...     coupling_type=CouplingType.DISTRIBUTING,
        ...     ref_node=1000,
        ...     surface_name='FACE_LOAD',
        ...     name='COUP_DIST',
        ...     first_dof=3,
        ...     cyclic_symmetry=True
        ... )
    """

    coupling_type: CouplingType
    """耦合类型"""
    ref_node: int
    """参考节点 ID"""
    surface_name: str
    """单元面表面名称"""
    name: str
    """耦合约束名称"""
    first_dof: int
    """第一个自由度（1-6）"""
    last_dof: Optional[int] = None
    """最后一个自由度（可选）"""
    orientation_name: Optional[str] = None
    """局部坐标系名称"""
    cyclic_symmetry: bool = False
    """是否循环对称（仅 DISTRIBUTING）"""
    desc: str = ""
    """描述文本"""
    keyword_name: str = "*COUPLING"
    """关键词名称"""

    def __post_init__(self):
        if self.first_dof < 1 or self.first_dof > 6:
            raise ValueError(f"first_dof 必须在 1-6 之间，当前值: {self.first_dof}")
        if self.last_dof is not None:
            if self.last_dof < 1 or self.last_dof > 6:
                raise ValueError(f"last_dof 必须在 1-6 之间，当前值: {self.last_dof}")
            if self.last_dof < self.first_dof:
                raise ValueError(f"last_dof ({self.last_dof}) 必须 >= first_dof ({self.first_dof})")
        if self.coupling_type != CouplingType.DISTRIBUTING and self.cyclic_symmetry:
            raise ValueError("cyclic_symmetry 仅适用于 DISTRIBUTING 类型")

    def to_inp_lines(self) -> list[str]:
        """转换为 INP 文件行。"""
        lines = []

        # COUPLING 行
        line = f"*COUPLING,CONSTRAINT NAME={self.name},REF NODE={self.ref_node},SURFACE={self.surface_name}"
        if self.orientation_name:
            line += f",ORIENTATION={self.orientation_name}"
        lines.append(line)

        # 类型行
        type_line = self.coupling_type.value
        if self.coupling_type == CouplingType.DISTRIBUTING and self.cyclic_symmetry:
            type_line += ",CYCLIC SYMMETRY"
        lines.append(type_line)

        # 自由度行
        dof_line = str(self.first_dof)
        if self.last_dof is not None:
            dof_line += f",{self.last_dof}"
        lines.append(dof_line)

        if self.desc:
            lines.insert(1, f"** {self.desc}")

        return lines

    def __str__(self) -> str:
        return "\n".join(self.to_inp_lines())
