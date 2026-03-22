"""
CAE-CLI 枚举定义

定义常用枚举类型，提高代码可读性和类型安全。
"""
from __future__ import annotations

from enum import Enum, IntEnum, auto


# =============================================================================
# 单元类型（CalculiX 官方命名）
# =============================================================================

class ElementType(str, Enum):
    """
    CalculiX 单元类型。

    命名规则：
      - C3D* : 3D 连续体（实体）单元
      - S*   : Shell（壳）单元
      - B*   : Beam（梁）单元
      - CPS*, CPE*, CAX* : 2D 平面应力/应变/轴对称单元
      - T*   : Truss（桁架）单元
      - M3D* : Membrane（膜）单元
      - SPRING*, GAPUNI, DASHPOTA : 特殊单元
    """

    # --- 3D 连续体单元 ---
    C3D4 = "C3D4"       # 4节点四面体（一阶）
    C3D6 = "C3D6"       # 6节点五面体（一阶）
    C3D8 = "C3D8"       # 8节点六面体（一阶）
    C3D8R = "C3D8R"     # 8节点六面体（减缩积分）
    C3D8I = "C3D8I"     # 8节点六面体（非协调模式）
    C3D10 = "C3D10"     # 10节点四面体（二阶）
    C3D10T = "C3D10T"   # 10节点四面体（热耦合）
    C3D15 = "C3D15"     # 15节点五面体（二阶）
    C3D20 = "C3D20"     # 20节点六面体（二阶）
    C3D20R = "C3D20R"   # 20节点六面体（二阶，减缩积分）

    # --- 3D 膜/壳单元 ---
    M3D3 = "M3D3"       # 3节点三角形膜
    M3D4 = "M3D4"       # 4节点四边形膜
    M3D4R = "M3D4R"     # 4节点四边形膜（减缩）
    M3D6 = "M3D6"       # 6节点三角形膜
    M3D8 = "M3D8"       # 8节点四边形膜
    M3D8R = "M3D8R"     # 8节点四边形膜（减缩）

    # --- Shell 单元 ---
    S3 = "S3"           # 3节点三角形壳（一阶）
    S4 = "S4"           # 4节点四边形壳（一阶）
    S4R = "S4R"         # 4节点四边形壳（减缩）
    S6 = "S6"           # 6节点三角形壳（二阶）
    S8 = "S8"           # 8节点四边形壳（二阶）
    S8R = "S8R"         # 8节点四边形壳（二阶，减缩）

    # --- 2D 平面应力/应变/轴对称单元 ---
    CPS3 = "CPS3"       # 3节点三角形平面应力
    CPS4 = "CPS4"       # 4节点四边形平面应力
    CPS4R = "CPS4R"     # 4节点四边形平面应力（减缩）
    CPS6 = "CPS6"       # 6节点三角形平面应力（二阶）
    CPS8 = "CPS8"       # 8节点四边形平面应力（二阶）
    CPS8R = "CPS8R"     # 8节点四边形平面应力（二阶，减缩）

    CPE3 = "CPE3"       # 3节点三角形平面应变
    CPE4 = "CPE4"       # 4节点四边形平面应变
    CPE4R = "CPE4R"     # 4节点四边形平面应变（减缩）
    CPE6 = "CPE6"       # 6节点三角形平面应变（二阶）
    CPE8 = "CPE8"       # 8节点四边形平面应变（二阶）
    CPE8R = "CPE8R"     # 8节点四边形平面应变（二阶，减缩）

    CAX3 = "CAX3"       # 3节点三角形轴对称
    CAX4 = "CAX4"       # 4节点四边形轴对称
    CAX4R = "CAX4R"     # 4节点四边形轴对称（减缩）
    CAX6 = "CAX6"       # 6节点三角形轴对称（二阶）
    CAX8 = "CAX8"       # 8节点四边形轴对称（二阶）
    CAX8R = "CAX8R"     # 8节点四边形轴对称（二阶，减缩）

    # --- 梁单元 ---
    B21 = "B21"         # 2节点梁（一阶，平面）
    B31 = "B31"         # 3节点梁（二阶，空间）
    B31R = "B31R"       # 3节点梁（二阶，减缩）
    B32 = "B32"         # 3节点梁（二阶，空间）
    B32R = "B32R"       # 3节点梁（二阶，减缩）

    # --- 桁架单元 ---
    T2D2 = "T2D2"       # 2节点2D桁架
    T3D2 = "T3D2"       # 2节点3D桁架
    T3D3 = "T3D3"       # 3节点3D桁架

    # --- 特殊单元 ---
    GAPUNI = "GAPUNI"   # 单向接触单元
    DASHPOTA = "DASHPOTA"  # 3D 减震器
    SPRING1 = "SPRING1"  # 1节点弹簧
    SPRING2 = "SPRING2"  # 2节点弹簧
    SPRINGA = "SPRINGA"  # 2节点弹簧（代数）
    DCOUP3D = "DCOUP3D"  # 1节点自由度耦合
    MASS = "MASS"       # 集中质量
    D = "D"             # 分布耦合

    @classmethod
    def from_string(cls, s: str) -> "ElementType":
        """从字符串解析单元类型（不区分大小写）。"""
        s_upper = s.upper()
        for member in cls:
            if member.value.upper() == s_upper:
                return member
        raise ValueError(f"未知单元类型: {s}")

    @property
    def is_solid(self) -> bool:
        """是否为3D实体单元。"""
        return self.value.startswith("C3D") and not self.value.startswith("C3D10T")

    @property
    def is_shell(self) -> bool:
        """是否为壳单元。"""
        return self.value.startswith("S") or self.value.startswith("M3D")

    @property
    def is_beam(self) -> bool:
        """是否为梁单元。"""
        return self.value.startswith("B")

    @property
    def is_2d(self) -> bool:
        """是否为2D单元。"""
        return self.value.startswith(("CPS", "CPE", "CAX"))

    @property
    def is_truss(self) -> bool:
        """是否为桁架单元。"""
        return self.value.startswith("T")

    @property
    def is_special(self) -> bool:
        """是否为特殊单元（弹簧、接触、质量等）。"""
        return self.value in (
            "GAPUNI", "DASHPOTA", "SPRING1", "SPRING2", "SPRINGA",
            "DCOUP3D", "MASS", "D",
        )

    @property
    def node_count(self) -> int:
        """返回单元节点数。"""
        counts = {
            # 3D 实体
            "C3D4": 4, "C3D6": 6, "C3D8": 8, "C3D8R": 8, "C3D8I": 8,
            "C3D10": 10, "C3D10T": 10, "C3D15": 15, "C3D20": 20, "C3D20R": 20,
            # 壳/膜
            "M3D3": 3, "M3D4": 4, "M3D4R": 4, "M3D6": 6, "M3D8": 8, "M3D8R": 8,
            "S3": 3, "S4": 4, "S4R": 4, "S6": 6, "S8": 8, "S8R": 8,
            # 2D
            "CPS3": 3, "CPS4": 4, "CPS4R": 4, "CPS6": 6, "CPS8": 8, "CPS8R": 8,
            "CPE3": 3, "CPE4": 4, "CPE4R": 4, "CPE6": 6, "CPE8": 8, "CPE8R": 8,
            "CAX3": 3, "CAX4": 4, "CAX4R": 4, "CAX6": 6, "CAX8": 8, "CAX8R": 8,
            # 梁
            "B21": 2, "B31": 3, "B31R": 3, "B32": 3, "B32R": 3,
            # 桁架
            "T2D2": 2, "T3D2": 2, "T3D3": 3,
            # 特殊
            "GAPUNI": 2, "DASHPOTA": 2, "SPRING1": 1, "SPRING2": 2,
            "SPRINGA": 2, "DCOUP3D": 1, "MASS": 1, "D": 2,
        }
        return counts.get(self.value, 0)


class ElementDimension(IntEnum):
    """单元空间维度。"""
    DIM_0D = 0  # 点单元（质量、弹簧端点）
    DIM_1D = 1  # 梁、桁架
    DIM_2D = 2  # 壳、膜、2D实体
    DIM_3D = 3  # 3D 实体


# =============================================================================
# 分析类型
# =============================================================================

class AnalysisType(str, Enum):
    """CAE 分析类型。"""
    STATIC = "STATIC"           # 静力学
    DYNAMIC = "DYNAMIC"         # 动力学
    FREQUENCY = "FREQUENCY"     # 模态分析
    BUCKLE = "BUCKLE"           # 屈曲分析
    THERMAL = "THERMAL"         # 热分析
    COUPLED_THERMAL = "COUPLED" # 热力耦合
    VISCO = "VISCO"             # 粘塑性


class StepType(str, Enum):
    """载荷步类型。"""
    STATIC = "*STATIC"
    DYNAMIC = "*DYNAMIC"
    FREQUENCY = "*FREQUENCY"
    BUCKLE = "*BUCKLE"
    VISCO = "*VISCO"
    GREEN = "*GREEN"
    COMPLEX_FREQUENCY = "*COMPLEX FREQUENCY"
    MODAL_DYNAMICS = "*MODAL DYNAMICS"
    SUBSPACE = "*SUBSPACE"
    Steady_STATE_DYNAMICS = "*STEADY STATE DYNAMICS"


# =============================================================================
# 边界条件和载荷类型
# =============================================================================

class BoundaryType(str, Enum):
    """边界条件类型。"""
    DISPLACEMENT = "DISPLACEMENT"   # 位移约束
    VELOCITY = "VELOCITY"           # 速度约束
    ACCELERATION = "ACCELERATION"   # 加速度约束
    TEMPERATURE = "TEMPERATURE"     # 温度约束
    SINGLE_POINT = "SINGLE POINT"   # 单点约束
    FLUID_FLM = "FLUID FLM"         # 流体


class LoadType(str, Enum):
    """载荷类型。"""
    CLOAD = "CLOAD"                 # 集中力
    DLOAD = "DLOAD"                 # 分布力
    BODYFORCE = "BODY FORCE"        # 体积力
    DEADLOAD = "DEAD LOAD"          # 重力
    CENTRIF = "CENTRIF"            # 离心力
    HEATFLUX = "HEAT FLUX"          # 热通量
    FILM = "FILM"                   # 薄膜换热
    GAPHEAT = "GAP HEAT"            # 接触热
    PRESCRIBEDDISP = "PRESCRIBED DISP"  # 强制位移


class LoadOp(str, Enum):
    """载荷操作选项。"""
    MOD = "MOD"   # 修改
    NEW = "NEW"   # 新建


class DloadType(str, Enum):
    """分布载荷类型。"""
    GRAV = "GRAV"           # 重力载荷
    CENTRIF = "CENTRIF"     # 离心力载荷
    NEWTON = "NEWTON"       # Newton 接触载荷
    P1 = "P1"              # 面1均匀压力
    P2 = "P2"              # 面2均匀压力
    P3 = "P3"              # 面3均匀压力
    P4 = "P4"              # 面4均匀压力
    P5 = "P5"              # 面5均匀压力
    P6 = "P6"              # 面6均匀压力


# =============================================================================
# 材料模型
# =============================================================================

class MaterialType(str, Enum):
    """材料模型类型。"""
    ELASTIC = "ELASTIC"
    PLASTIC = "PLASTIC"
    HYPERELASTIC = "HYPERELASTIC"
    VISCOELASTIC = "VISCOELASTIC"
    CREEP = "CREEP"
    DENSITY = "DENSITY"
    EXPANSION = "EXPANSION"
    CONDUCTIVITY = "CONDUCTIVITY"
    SPECIFIC_HEAT = "SPECIFIC HEAT"
    ELASTICITY = "ELASTICITY"


class ElasticType(str, Enum):
    """弹性类型。"""
    ISO = "ISO"                     # 各向同性
    ORTHO = "ORTHO"               # 正交各向异性
    ENGINEERING_CONSTANTS = "ENGINEERING CONSTANTS"  # 工程常数
    ANISO = "ANISO"               # 各向异性


class HardeningRule(str, Enum):
    """塑性硬化规则。"""
    ISOTROPIC = "ISOTROPIC"       # 等向硬化
    KINEMATIC = "KINEMATIC"       # 随动硬化
    COMBINED = "COMBINED"         # 组合硬化


class HyperElasticType(str, Enum):
    """超弹性材料类型。"""
    ARRUDA_BOYCE = "ARRUDA-BOYCE"
    MOONEY_RIVLIN = "MOONEY-RIVLIN"
    NEO_HOOKE = "NEO HOOKE"
    OGDEN_1 = "OGDEN,N=1"
    OGDEN_2 = "OGDEN,N=2"
    OGDEN_3 = "OGDEN,N=3"
    OGDEN_4 = "OGDEN,N=4"
    POLYNOMIAL_1 = "POLYNOMIAL,N=1"
    POLYNOMIAL_2 = "POLYNOMIAL,N=2"
    POLYNOMIAL_3 = "POLYNOMIAL,N=3"
    REDUCED_POLYNOMIAL_1 = "REDUCED POLYNOMIAL,N=1"
    REDUCED_POLYNOMIAL_2 = "REDUCED POLYNOMIAL,N=2"
    REDUCED_POLYNOMIAL_3 = "REDUCED POLYNOMIAL,N=3"
    YEOH = "YEOH"


# =============================================================================
# 输出请求类型
# =============================================================================

class OutputRequestType(str, Enum):
    """结果输出请求类型。"""
    NODE_FILE = "NODE FILE"
    EL_FILE = "EL FILE"
    NODE_PRINT = "NODE PRINT"
    EL_PRINT = "EL PRINT"
    CONTACT_FILE = "CONTACT FILE"
    CONTACT_PRINT = "CONTACT PRINT"
    SECTION_PRINT = "SECTION PRINT"


# =============================================================================
# 结果位置类型
# =============================================================================

class ResultLocation(str, Enum):
    """
    结果数据的位置类型。

    区分结果是在节点上、单元上还是积分点上。
    """
    NODAL = "NODAL"           # 节点结果（每个节点一个值）
    ELEMENT = "ELEMENT"        # 单元结果（每个单元一个值）
    INT_PNT = "INT_PNT"       # 积分点结果（每个单元多个积分点）


# =============================================================================
# 接触类型枚举
# =============================================================================

class ContactType(str, Enum):
    """
    接触类型。

    参考 pygccx EContactTypes。
    """
    NODE_TO_SURFACE = "NODE TO SURFACE"      # 节点-面接触
    SURFACE_TO_SURFACE = "SURFACE TO SURFACE"  # 面-面接触
    MORTAR = "MORTAR"                         # MORTAR 接触
    LINMORTAR = "LINMORTAR"                   # 线性 MORTAR 接触
    PGLINMORTAR = "PGLINMORTAR"              # 丢番图线性 MORTAR


# =============================================================================
# 压力-间隙模型枚举
# =============================================================================

class PressureOverclosure(str, Enum):
    """
    压力-间隙模型类型。

    用于 *SURFACE BEHAVIOR,PRESSURE-OVERCLOSURE=...
    """
    EXPONENTIAL = "EXPONENTIAL"   # 指数模型
    LINEAR = "LINEAR"            # 线性模型
    TABULAR = "TABULAR"          # 表格模型
    TIED = "TIED"               # 绑定模型


# =============================================================================
# 耦合类型枚举
# =============================================================================

class CouplingType(str, Enum):
    """
    耦合类型。

    用于 *COUPLING ... *DISTRIBUTING/*KINEMATIC
    """
    DISTRIBUTING = "*DISTRIBUTING"
    """分布耦合：力/力矩按面积权重分配到参考节点"""
    KINEMATIC = "*KINEMATIC"
    """运动耦合：节点位移与参考节点刚体运动协调"""


class MpcType(str, Enum):
    """
    MPC（多点约束）类型。

    用于 *MPC
    """
    PLANE = "PLANE"
    """强制所有依赖节点保持在平面内"""
    STRAIGHT = "STRAIGHT"
    """强制所有依赖节点保持在直线上"""
    BEAM = "BEAM"
    """刚体梁：强制两节点保持欧几里得距离"""
    MEANROT = "MEANROT"
    """强制参考节点旋转为所有依赖节点旋转的平均值"""
    DIST = "DIST"
    """强制两节点间欧几里得距离不超过给定值"""


# =============================================================================
# FRD 文件结果实体类型（借鉴 pygccx EFrdEntities）
# =============================================================================

class FrdResultEntity(str, Enum):
    """
    .frd 文件中的结果实体类型。

    对应 CalculiX 输出的字段名。
    """
    # --- 位移/速度/加速度 ---
    DISP = "DISP"                   # 实位移
    DISPI = "DISPI"                 # 虚位移（复数分析）
    VELO = "VELO"                   # 速度
    ACCE = "ACCE"                   # 加速度

    # --- 力/反力 ---
    FORC = "FORC"                  # 节点力（实部）
    FORCI = "FORCI"                # 节点力（虚部）
    PFORC = "PFORC"                # 相位力
    RF = "RF"                      # 反力
    PRF = "PRF"                    # 相位反力

    # --- 应力/应变 ---
    STRESS = "STRESS"               # Cauchy 应力（实部）
    STRESSI = "STRESSI"             # Cauchy 应力（虚部）
    MSTRESS = "MSTRESS"            # 最大主应力
    ZZSTR = "ZZSTR"                # Zienkiewicz-Zhu 应力
    ZZSTRI = "ZZSTRI"              # Zienkiewicz-Zhu 应力（虚部）

    # --- 应变 ---
    STRAIN = "STRAIN"              # Lagrange应变
    STRAINI = "STRAINI"            # Lagrange应变（虚部）
    TOSTRAIN = "TOSTRAIN"          # 总应变
    TOSTRAII = "TOSTRAII"         # 总应变（虚部）
    MESTRAIN = "MESTRAIN"          # 机械应变
    MESTRAII = "MESTRAII"         # 机械应变（虚部）
    PEEQ = "PEEQ"                  # 等效塑性应变
    PE = "PE"                      # 塑性应变

    # --- 能量/误差 ---
    ENER = "ENER"                  # 内能密度
    ELKE = "ELKE"                  # 单元动能
    ELSE = "ELSE"                  # 单元内能
    EMAS = "EMAS"                  # 单元质量
    ERROR = "ERROR"                # 误差估计器
    ERRORI = "ERRORI"              # 误差估计器（虚部）
    HERROR = "HERROR"              # 温度误差估计器
    HERRORI = "HERRORI"            # 温度误差估计器（虚部）

    # --- 热/接触 ---
    FLUX = "FLUX"                  # 热通量
    HFL = "HFL"                    # 结构热通量
    NDTEMP = "NDTEMP"              # 节点温度
    PNDTEMP = "PNDTEMP"            # 相位节点温度
    MSTRAIN = "MSTRAIN"            # 最大主应变

    # --- 特殊 ---
    CT3D_MIS = "CT3D-MIS"         # 应力强度因子
    MDISP = "MDISP"                # 最大位移
    SEN = "SEN"                    # 灵敏度
    ZZS = "ZZS"                    # Zienkiewicz-Zhu 应变

    # --- 接触 ---
    CONTACT = "CONTACT"             # 接触位移（实部）
    CONTACTI = "CONTACTI"           # 接触位移（虚部）
    CELS = "CELS"                  # 接触能量
    PCONTAC = "PCONTAC"            # 接触幅值和相位

    # --- 辅助 ---
    COORD = "COORD"                 # 坐标
    EVOL = "EVOL"                  # 单元体积


# =============================================================================
# DAT 文件结果实体类型（借鉴 pygccx EDatEntities）
# =============================================================================

class DatResultEntity(str, Enum):
    """
    .dat 文件中的结果实体类型。

    对应 CalculiX NODE PRINT / EL PRINT 输出的字段名。
    """
    # --- 节点打印 ---
    U = "U"                        # 位移
    RF = "RF"                      # 节点力/反力

    # --- 单元打印 ---
    S = "S"                        # Cauchy 应力
    E = "E"                        # Lagrange 应变
    ME = "ME"                      # 机械应变
    PEEQ = "PEEQ"                  # 等效塑性应变
    EVOL = "EVOL"                  # 单元体积
    COORD = "COORD"                # 全局坐标
    ENER = "ENER"                  # 内能密度
    ELKE = "ELKE"                  # 单元动能
    ELSE = "ELSE"                  # 单元内能
    EMAS = "EMAS"                  # 单元质量

    # --- 接触打印 ---
    CDIS = "CDIS"                  # 相对接触位移
    CSTR = "CSTR"                  # 接触应力
    CELS = "CELS"                  # 接触能量
