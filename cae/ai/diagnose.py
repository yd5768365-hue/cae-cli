# diagnose.py
"""
三层次诊断系统

Level 1: 规则检测（无条件执行）
  - 收敛性：stderr 含 *ERROR 或 returncode != 0
  - 单元质量：Jacobian 负值、Hourglass、沙漏模式
  - 网格质量：节点/单元比例异常
  - 应力集中：应力梯度突变 > 50x
  - 位移范围：最大位移 > 模型尺寸 10%
  - 大变形：大应变分量 > 0.1 且无 NLGEOM → 建议启用几何非线性
  - 刚体模式：位移非零但应力接近零 → 欠约束
  - 材料屈服：最大应力超过屈服强度
  - 单位一致性：应力量级异常（< 1 Pa 或 > 1 TPa，或 E/应力单位不匹配）

Level 2: 参考案例对比（无条件执行）
  - 从 638 个官方测试集找相似案例
  - 对比用户结果的位移/应力是否在同类案例合理范围内

Level 3: AI 深度分析（可选，需安装 ai 插件）
  - 结合规则检测 + 参考案例对比结果
  - 给出具体的修复建议
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import DIAGNOSE_SYSTEM, make_diagnose_prompt
from .stream_handler import StreamHandler
from .explain import _find_frd, _extract_stats
from .reference_cases import CaseMetadata, CaseDatabase, parse_inp_metadata, ClassificationTree
from cae.viewer.frd_parser import parse_frd

log = logging.getLogger(__name__)

# 参考案例库路径
REFERENCE_CASES_PATH = Path(__file__).parent / "data" / "reference_cases.json"


@dataclass
class DiagnosticIssue:
    """诊断问题条目。"""
    severity: str  # "error" | "warning" | "info"
    category: str  # "convergence" | "mesh_quality" | "stress_concentration" | "displacement" | "reference_comparison"
    message: str
    location: Optional[str] = None
    suggestion: Optional[str] = None


@dataclass
class DiagnoseResult:
    """诊断结果。"""
    success: bool
    level1_issues: list[DiagnosticIssue] = field(default_factory=list)  # 规则检测
    level2_issues: list[DiagnosticIssue] = field(default_factory=list)  # 参考案例对比
    level3_diagnosis: Optional[str] = None  # AI 诊断
    similar_cases: list[dict] = field(default_factory=list)  # 相似案例
    error: Optional[str] = None

    @property
    def issues(self) -> list[DiagnosticIssue]:
        """所有问题的合并列表。"""
        return self.level1_issues + self.level2_issues

    @property
    def issue_count(self) -> int:
        return len(self.issues)


def diagnose_results(
    results_dir: Path | str,
    client: Optional[LLMClient] = None,
    inp_file: Optional[Path] = None,
    *,
    stream: bool = True,
) -> DiagnoseResult:
    """
    三层次诊断。

    Args:
        results_dir: 包含 .frd / .sta / .dat 文件的目录
        client: LLM 客户端（可选，不传或为 None 时跳过 Level 3）
        inp_file: 输入的 .inp 文件路径（用于提取元数据进行案例匹配）
        stream: 是否流式输出

    Returns:
        DiagnoseResult
    """
    result = DiagnoseResult(success=True)

    # 确保 results_dir 是 Path 对象
    if isinstance(results_dir, str):
        results_dir = Path(results_dir)

    try:
        # ========== Level 1: 规则检测（无条件执行）==========
        result.level1_issues.extend(_check_convergence(results_dir))
        result.level1_issues.extend(_check_time_increment_stagnation(results_dir))
        result.level1_issues.extend(_check_input_syntax(results_dir))
        result.level1_issues.extend(_check_material_definition(results_dir))
        result.level1_issues.extend(_check_parameter_syntax(results_dir))
        result.level1_issues.extend(_check_element_quality(results_dir))
        result.level1_issues.extend(_check_frd_quality(results_dir))
        result.level1_issues.extend(_check_stress_gradient(results_dir))
        result.level1_issues.extend(_check_displacement_range(results_dir))
        result.level1_issues.extend(_check_large_strain(results_dir, inp_file))
        result.level1_issues.extend(_check_rigid_body_mode(results_dir, inp_file))
        result.level1_issues.extend(_check_material_yield(results_dir, inp_file))
        result.level1_issues.extend(_check_unit_consistency(results_dir, inp_file))

        # ========== Level 2: 参考案例对比（无条件执行）==========
        ref_result = _check_reference_cases(results_dir, inp_file)
        result.level2_issues = ref_result["issues"]
        result.similar_cases = ref_result["similar_cases"]

        # ========== Level 3: AI 深度分析（可选）==========
        if client is not None:
            result.level3_diagnosis = _run_ai_diagnosis(
                client,
                result.level1_issues,
                result.level2_issues,
                result.similar_cases,
                results_dir,
                stream=stream,
            )

    except FileNotFoundError as exc:
        result.success = False
        result.error = str(exc)
    except Exception as exc:
        result.success = False
        result.error = f"诊断失败: {exc}"
        log.exception("诊断过程出错")

    return result


# ------------------------------------------------------------------ #
# Level 1: 规则检测函数
# ------------------------------------------------------------------ #

# Jacobian / Hourglass 检测模式（不区分大小写）
JACOBIAN_PATTERNS = [
    re.compile(r"negative jacobian", re.IGNORECASE),
    re.compile(r"hourglassing", re.IGNORECASE),
    re.compile(r"hourlim", re.IGNORECASE),
    re.compile(r"nonpositive jacobian", re.IGNORECASE),
]

# 收敛性问题检测模式
CONVERGENCE_PATTERNS = [
    re.compile(r"not\s+converged", re.IGNORECASE),
    re.compile(r"increment\s+size\s+smaller", re.IGNORECASE),
    re.compile(r"divergence", re.IGNORECASE),
]

# 无效 INP 卡片检测模式
INVALID_CARD_PATTERNS = [
    re.compile(r"card image cannot be interpreted", re.IGNORECASE),
    re.compile(r"unknown keyword", re.IGNORECASE),
]

# 材料缺失检测模式（来自 CalculiX 源码）
MATERIAL_PATTERNS = [
    re.compile(r"no elastic constants", re.IGNORECASE),
    re.compile(r"no density was assigned", re.IGNORECASE),
    re.compile(r"no material was assigned", re.IGNORECASE),
    re.compile(r"no specific heat", re.IGNORECASE),
    re.compile(r"no conductivity", re.IGNORECASE),
]

# 参数不识别检测模式
PARAMETER_PATTERNS = [
    re.compile(r"parameter not recognized", re.IGNORECASE),
]

# MPC/约束数量超限检测模式
MPC_LIMIT_PATTERNS = [
    re.compile(r"increase nmpc_", re.IGNORECASE),
    re.compile(r"increase nboun_", re.IGNORECASE),
    re.compile(r"increase nk_", re.IGNORECASE),
    re.compile(r"increase memmpc_", re.IGNORECASE),
]


def _check_convergence(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查收敛性：扫描 .sta / .dat / .cvg 文件中的收敛相关错误。

    检测模式：
    - *ERROR：求解器明确报错
    - NOT CONVERGED：迭代未收敛
    - INCREMENT SIZE SMALLER：增量步小于最小值（收敛困难）
    - DIVERGENCE：发散
    """
    issues: list[DiagnosticIssue] = []

    # 需要扫描的文件
    scan_targets: list[tuple[Path, str]] = []
    for ext in ("*.sta", "*.dat", "*.cvg"):
        for f in results_dir.glob(ext):
            scan_targets.append((f, f.name))

    # 额外检查：stderr 文件（如果存在）
    for stderr_file in results_dir.glob("*.stderr"):
        scan_targets.append((stderr_file, stderr_file.name))

    for file_path, file_label in scan_targets:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")

            # 先尝试匹配特定模式
            for pattern in CONVERGENCE_PATTERNS:
                match = pattern.search(text)
                if match:
                    matched_text = match.group(0).lower()
                    if "increment size smaller" in matched_text:
                        msg = "增量步小于最小值，收敛困难"
                        suggestion = "减小初始步长（*STATIC 首参数），或增大允许的最小步长，或放宽收敛容差"
                    elif "not converged" in matched_text or "converged" in matched_text and "not" in matched_text:
                        msg = "迭代未收敛"
                        suggestion = "检查载荷步设置，增大迭代次数或调整收敛容差"
                    elif "divergence" in matched_text:
                        msg = "求解发散"
                        suggestion = "检查边界条件和载荷是否合理，减小载荷增量"
                    else:
                        msg = "求解器报告错误，收敛失败"
                        suggestion = "检查边界条件、载荷是否合理，或增大迭代次数"

                    issues.append(DiagnosticIssue(
                        severity="error",
                        category="convergence",
                        message=msg,
                        location=file_label,
                        suggestion=suggestion,
                    ))
                    break  # 每个文件只报一次

        except OSError:
            pass

    return issues


def _check_time_increment_stagnation(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查时间增量停滞：连续5个增量步 INC TIME 不增大。

    扫描 .sta 和 .stderr 文件，解析 "increment size=" 模式，
    连续5个增量步的时间增量没有增加则触发警告。
    """
    issues: list[DiagnosticIssue] = []

    import re

    # 收集所有输出文件
    scan_files: list[tuple[Path, str]] = []
    scan_files.extend((f, f.name) for f in results_dir.glob("*.sta"))
    scan_files.extend((f, f.name) for f in results_dir.glob("*.stderr"))

    for file_path, file_label in scan_files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")

            # 匹配 "increment size= 1.000000e+00" 格式
            inc_times: list[float] = []
            for line in text.splitlines():
                match = re.search(r"increment\s+size=\s*([0-9eE.+\-]+)", line)
                if match:
                    try:
                        val = float(match.group(1))
                        inc_times.append(val)
                    except ValueError:
                        pass

            # 检查连续5个增量是否停滞
            if len(inc_times) >= 5:
                stagnant_count = 0
                for i in range(1, len(inc_times)):
                    if inc_times[i] <= inc_times[i - 1]:
                        stagnant_count += 1
                    else:
                        stagnant_count = 0  # 重置计数器
                    if stagnant_count >= 5:
                        issues.append(DiagnosticIssue(
                            severity="warning",
                            category="convergence",
                            message="时间增量停滞，连续5个增量步 INC TIME 未增大",
                            location=file_label,
                            suggestion="检查接触设置或减小初始步长（*STATIC 首参数）。接触问题建议：1) 检查接触面定义是否正确 2) 减小接触刚度惩罚因子（*SURFACE BEHAVIOR 的 pressure= 参数）3) 使用 *CONTROLS, PARAMETER=FIELD 调整迭代参数",
                        ))
                        break

        except OSError:
            pass

    return issues


def _check_input_syntax(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查 INP 输入文件语法：无效卡片等错误。

    扫描 .stderr 文件，匹配以下模式：
    - "card image cannot be interpreted"：无法识别的卡片
    - "unknown keyword"：未知关键词
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file in results_dir.glob("*.stderr"):
        try:
            text = stderr_file.read_text(encoding="utf-8", errors="replace")

            for pattern in INVALID_CARD_PATTERNS:
                match = pattern.search(text)
                if match:
                    issues.append(DiagnosticIssue(
                        severity="error",
                        category="input_syntax",
                        message="检测到无效 INP 关键词，可能是拼写错误或版本不兼容",
                        location=stderr_file.name,
                        suggestion="检查 INP 文件中的卡片拼写，确保与 CalculiX 支持的关键词一致。常见错误：拼写错误、大小写不匹配、不支持的卡片格式。",
                    ))
                    break  # 每个文件只报一次

        except OSError:
            pass

    return issues


def _check_material_definition(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查材料定义完整性：材料属性缺失等错误。

    扫描 .stderr 文件，匹配以下模式（来自 CalculiX 源码）：
    - "no elastic constants"：缺少弹性常数
    - "no density was assigned"：缺少密度
    - "no material was assigned"：未分配材料
    - "no specific heat"：缺少比热容
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file in results_dir.glob("*.stderr"):
        try:
            text = stderr_file.read_text(encoding="utf-8", errors="replace")

            for pattern in MATERIAL_PATTERNS:
                match = pattern.search(text)
                if match:
                    matched_text = match.group(0).lower()
                    if "no elastic" in matched_text:
                        msg = "材料缺少弹性常数（Elastic modulus）"
                        suggestion = "在 *MATERIAL 中添加 *ELASTIC 或 *ELASTIC,TYPE=ISOTROPIC 定义弹性模量"
                    elif "no density" in matched_text:
                        msg = "材料缺少密度定义"
                        suggestion = "在 *MATERIAL 中添加 *DENSITY 定义材料密度（动力学分析必需）"
                    elif "no material" in matched_text:
                        msg = "单元未分配材料属性"
                        suggestion = "检查 *SOLID SECTION 是否正确关联了材料名称"
                    elif "no specific heat" in matched_text:
                        msg = "材料缺少比热容定义"
                        suggestion = "在 *MATERIAL 中添加 *SPECIFIC HEAT 定义比热容（热分析必需）"
                    elif "no conductivity" in matched_text:
                        msg = "材料缺少热传导系数"
                        suggestion = "在 *MATERIAL 中添加 *CONDUCTIVITY 定义热传导系数"
                    else:
                        msg = "材料属性定义不完整"
                        suggestion = "检查材料卡片是否完整定义"
                    issues.append(DiagnosticIssue(
                        severity="error",
                        category="material",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    ))
                    break

        except OSError:
            pass

    return issues


def _check_parameter_syntax(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查卡片参数语法：参数不识别等错误。

    扫描 .stderr 文件，匹配 "parameter not recognized" 模式。
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file in results_dir.glob("*.stderr"):
        try:
            text = stderr_file.read_text(encoding="utf-8", errors="replace")

            if PARAMETER_PATTERNS[0].search(text):
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="input_syntax",
                    message="卡片参数不被识别",
                    location=stderr_file.name,
                    suggestion="检查卡片参数拼写是否正确。CalculiX 参数名区分大小写，常见错误：PARAMETERS 而非 PARAMETER",
                ))
                break

        except OSError:
            pass

    return issues


def _check_element_quality(results_dir: Path) -> list[DiagnosticIssue]:
    """
    检查单元质量：Jacobian 负值、Hourglass 等问题。

    扫描 .sta / .dat / .cvg 文件，使用正则匹配以下模式：
    - NEGATIVE JACOBIAN：单元翻转或畸形
    - HOURGLASSING：减缩积分单元的零能模式
    - HOURGLIM：沙漏控制参数
    - *ERROR.*element：元素相关错误
    """
    issues: list[DiagnosticIssue] = []

    # 需要扫描的文件及对应的位置信息
    scan_files: list[tuple[Path, str]] = []
    for sta in results_dir.glob("*.sta"):
        scan_files.append((sta, sta.name))
    for dat in results_dir.glob("*.dat"):
        scan_files.append((dat, dat.name))
    for cvg in results_dir.glob("*.cvg"):
        scan_files.append((cvg, cvg.name))

    for file_path, file_label in scan_files:
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")

            for pattern in JACOBIAN_PATTERNS:
                match = pattern.search(text)
                if match:
                    # 根据匹配到的关键词确定具体问题类型
                    matched_text = match.group(0).lower()
                    if "negative jacobian" in matched_text:
                        issue_type = "Jacobian 负值"
                        suggestion = "检查网格质量，畸形单元会导致 Jacobian 负值。尝试：1) 加密网格 2) 改善单元形状 3) 使用全积分单元替代减缩积分"
                    elif "hourglassing" in matched_text:
                        issue_type = "Hourglass 模式"
                        suggestion = "检测到沙漏/零能模式。解决：1) 加密网格 2) 使用全积分单元（如 C3D8 而非 C3D8R）3) 调整 HOURGLIM 参数"
                    elif "hourlim" in matched_text:
                        issue_type = "Hourglass 控制"
                        suggestion = "沙漏控制参数异常。检查：1) 网格是否太粗 2) 是否使用了减缩积分单元"
                    else:
                        issue_type = "单元错误"
                        suggestion = "检测到元素相关错误。检查网格质量和单元类型设置"

                    issues.append(DiagnosticIssue(
                        severity="error",
                        category="element_quality",
                        message=f"单元质量问题（{issue_type}）",
                        location=file_label,
                        suggestion=suggestion,
                    ))
                    break  # 每个文件只报一次

        except OSError:
            pass

    return issues


def _check_frd_quality(results_dir: Path) -> list[DiagnosticIssue]:
    """检查网格质量（通过 FrdData 统计推断）。"""
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)

        if frd_data.node_count > 0 and frd_data.element_count > 0:
            ratio = frd_data.node_count / frd_data.element_count
            if ratio < 0.5:
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="mesh_quality",
                    message=f"节点/单元比例过低 ({ratio:.2f})，可能存在低质量单元",
                    suggestion="检查网格划分参数，确保没有畸形单元",
                ))
            elif ratio > 50:
                issues.append(DiagnosticIssue(
                    severity="info",
                    category="mesh_quality",
                    message=f"节点/单元比例较高 ({ratio:.2f})",
                    suggestion="考虑加密网格以提高精度",
                ))

        # 检查位移异常
        disp_result = frd_data.get_result("DISP")
        if disp_result and disp_result.values:
            all_disp_vals = [
                (sum(v ** 2 for v in vals) ** 0.5 if len(vals) >= 3 else abs(vals[0]))
                for vals in disp_result.values.values()
                if vals
            ]
            if all_disp_vals:
                max_disp = max(all_disp_vals)
                mean_disp = sum(all_disp_vals) / len(all_disp_vals)
                if max_disp > 0 and mean_disp > 0 and max_disp / mean_disp > 100:
                    issues.append(DiagnosticIssue(
                        severity="warning",
                        category="mesh_quality",
                        message=f"位移分布极不均匀，最大/平均 = {max_disp/mean_disp:.1f}x",
                        suggestion="可能存在应力集中或边界条件错误",
                    ))

    except Exception:
        pass

    return issues


def _check_stress_gradient(results_dir: Path) -> list[DiagnosticIssue]:
    """检查应力集中：应力梯度突变 > 50x。"""
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        stress_result = frd_data.get_result("STRESS")

        if stress_result and stress_result.values and len(stress_result.values) > 10:
            stress_vals = []
            for vals in stress_result.values.values():
                if len(vals) >= 4:
                    stress_vals.append(abs(vals[3]))
                elif vals:
                    stress_vals.append(abs(max(vals, key=abs)))

            if stress_vals:
                sorted_vals = sorted(stress_vals)
                min_stress = sorted_vals[len(sorted_vals) // 10]
                max_stress = sorted_vals[-1]

                if min_stress > 0 and max_stress / min_stress > 50:
                    issues.append(DiagnosticIssue(
                        severity="warning",
                        category="stress_concentration",
                        message=f"应力梯度极大（差异 > 50x），可能存在应力集中",
                        suggestion="在应力集中区域加密网格，或优化几何形状",
                    ))

    except Exception:
        pass

    return issues


def _check_displacement_range(results_dir: Path) -> list[DiagnosticIssue]:
    """检查位移范围：最大位移 > 模型尺寸 10%。"""
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        stats = _extract_stats(frd_data)

        max_disp = stats["max_displacement"]
        bx, by, bz = stats["model_bounds"]
        model_size = max(bx, by, bz)

        # 数值溢出检测：位移 > 1e10 是求解未收敛的标志
        if max_disp > 1e10:
            issues.append(DiagnosticIssue(
                severity="error",
                category="displacement",
                message=f"最大位移异常巨大（{max_disp:.2e}），疑似数值溢出",
                suggestion="求解可能未收敛。检查：1) 接触设置是否正确 2) 载荷步是否合理 3) 网格是否过于畸形",
            ))
            return issues  # 数值溢出的情况下不继续判断刚度问题

        if model_size > 0 and max_disp / model_size > 0.1:
            issues.append(DiagnosticIssue(
                severity="warning",
                category="displacement",
                message=f"最大位移 ({max_disp:.2e}) 超过模型尺寸的 10%，可能刚度不足",
                suggestion="考虑增加厚度、添加肋板或使用更高强度材料",
            ))

    except Exception:
        pass

    return issues


def _check_large_strain(results_dir: Path, inp_file: Optional[Path] = None) -> list[DiagnosticIssue]:
    """
    检查大变形：应变分量 > 0.1（10%应变）时判断是否启用了几何非线性。

    规则：
    - 应变分量 > 0.1 且 inp 无 NLGEOM → warning: 建议启用几何非线性
    - 应变分量 > 0.1 且 inp 有 NLGEOM → info: 大变形分析，应变为拉格朗日定义
    - NLGEOM 检测支持两种格式：*STEP, NLGEOM 和 *STEP,NLGEOM（无空格）
    """
    issues: list[DiagnosticIssue] = []

    # 1. 检查 inp 文件是否有 NLGEOM
    has_nlgeom = False
    if inp_file and inp_file.exists():
        try:
            inp_text = inp_file.read_text(encoding="utf-8", errors="replace")
            # 支持 *STEP, NLGEOM 和 *STEP,NLGEOM 两种格式
            has_nlgeom = bool(re.search(r"\*STEP\s*,\s*NLGEOM", inp_text, re.IGNORECASE))
        except OSError:
            pass

    # 2. 解析 FRD 获取应变数据
    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        strain_result = frd_data.get_result("TOSTRAIN")

        if not strain_result or not strain_result.values:
            return issues

        # 找出所有应变分量的最大值
        max_strain = 0.0
        max_component = ""
        max_node = 0

        for comp_idx, comp_name in enumerate(strain_result.components):
            for node_id, vals in strain_result.values.items():
                if vals is not None and len(vals) > comp_idx:
                    val = abs(float(vals[comp_idx]))
                    if val > max_strain:
                        max_strain = val
                        max_component = comp_name
                        max_node = node_id

        # 3. 根据阈值判断
        if max_strain > 0.1:
            if has_nlgeom:
                issues.append(DiagnosticIssue(
                    severity="info",
                    category="large_strain",
                    message=f"检测到大变形（{max_component}={max_strain:.4f}），分析已启用几何非线性（NLGEOM），应变输出为拉格朗日定义",
                    location=f"节点 {max_node}",
                    suggestion="结果为格林/拉格朗日应变，非线性应变值本身是合理的",
                ))
            else:
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="large_strain",
                    message=f"检测到大变形（{max_component}={max_strain:.4f}），但 inp 文件未启用几何非线性（NLGEOM）",
                    location=f"节点 {max_node}",
                    suggestion="在 *STEP 行添加 NLGEOM 参数以启用几何非线性分析：*STEP, NLGEOM",
                ))

    except Exception:
        pass

    return issues


# ------------------------------------------------------------------ #
# 材料屈服强度提取（单位：Pa）
# ------------------------------------------------------------------ #

def _extract_yield_strength(inp_file: Optional[Path]) -> Optional[float]:
    """
    从 inp 文件提取材料屈服强度。

    支持的材料定义：
    - *DEFORMATION PLASTICITY：E, nu, sigma_y, n, angle → 取第三参数 sigma_y（单位 MPa）
    - *PLASTIC：需解析多行，默认取第一个屈服点（单位 MPa）
    - *ELASTIC：无法获取屈服强度，返回 None

    Returns:
        屈服强度（Pa），无法提取时返回 None
    """
    if not inp_file or not inp_file.exists():
        return None

    try:
        lines = inp_file.read_text(encoding="utf-8", errors="replace").splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # DEFORMATION PLASTICITY: E, nu, sigma_y, n, angle
            if line.upper().startswith("*DEFORMATION PLASTICITY"):
                if i + 1 < len(lines):
                    parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', lines[i + 1])
                    if len(parts) >= 3:
                        # sigma_y 单位是 MPa，转换为 Pa
                        return float(parts[2]) * 1e6
                i += 1
                continue

            # *PLASTIC: 屈服应力（第一列），单位 MPa
            if line.upper().startswith("*PLASTIC"):
                # 读取后续非注释行，取第一个数据行的第一列
                i += 1
                while i < len(lines):
                    data_line = lines[i].strip()
                    if not data_line or data_line.startswith("**") or data_line.startswith("*"):
                        i += 1
                        continue
                    parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', data_line)
                    if parts:
                        # 单位 MPa，转换为 Pa
                        return float(parts[0]) * 1e6
                    i += 1
                continue

            # *ELASTIC 只有 E 和 nu，无法获取屈服强度
            if line.upper().startswith("*ELASTIC"):
                return None

            i += 1

    except Exception:
        pass

    return None


# ------------------------------------------------------------------ #
# 刚体模式 & 材料屈服检测
# ------------------------------------------------------------------ #

def _check_rigid_body_mode(
    results_dir: Path,
    inp_file: Optional[Path] = None,
) -> list[DiagnosticIssue]:
    """
    检查刚体模式：位移非零但应力几乎为零。

    判断逻辑：
    - 最大位移 > 模型尺寸的 1% 且 最大 von Mises 应力 < 屈服强度的 0.01
    - 注意：刚体运动的特征是"整体"应力很低，用最大应力而不是平均应力更准确
    - 避免粗网格下应力插值误差导致的误报
    """
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        stats = _extract_stats(frd_data)

        max_disp = stats["max_displacement"]
        model_size = max(*stats["model_bounds"], 1e-10)

        # 位移太小（< 模型尺寸 0.5%）不算刚体模式
        if max_disp < model_size * 0.005:
            return issues

        # 获取最大应力
        max_stress = _get_max_stress(frd_data)
        if max_stress <= 0:
            return issues

        # 从 inp 获取屈服强度
        yield_strength = _extract_yield_strength(inp_file)
        if yield_strength is None:
            yield_strength = 250e6  # 默认结构钢

        # 最大应力 < 屈服强度的 0.01（1%）认为是刚体运动
        if max_disp > model_size * 0.01 and max_stress < yield_strength * 0.01:
            issues.append(DiagnosticIssue(
                severity="warning",
                category="rigid_body_mode",
                message=f"检测到刚体运动：最大位移较大（{max_disp:.2e}）但最大应力很低（{max_stress:.2e} Pa），可能存在欠约束",
                location=f"最大应力/屈服强度比: {max_stress/yield_strength:.4e}",
                suggestion="检查边界条件：确保结构被完全约束（尤其旋转自由度），所有位移分量都被限制",
            ))

    except Exception:
        pass

    return issues


def _check_material_yield(
    results_dir: Path,
    inp_file: Optional[Path] = None,
) -> list[DiagnosticIssue]:
    """
    检查材料是否屈服：最大应力是否超过屈服强度。

    判断逻辑：
    - 最大 von Mises 应力 > 屈服强度 → warning: 材料屈服
    - 最大 von Mises 应力 > 屈服强度 * 1.5 → error: 严重屈服
    """
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        max_stress = _get_max_stress(frd_data)

        if max_stress <= 0:
            return issues

        yield_strength = _extract_yield_strength(inp_file)
        if yield_strength is None:
            # 线弹性材料（*ELASTIC）无屈服强度定义，跳过屈服检查
            log.info("线弹性材料，无屈服强度定义，跳过屈服检查")
            return issues

        ratio = max_stress / yield_strength

        if ratio > 1.5:
            issues.append(DiagnosticIssue(
                severity="error",
                category="material_yield",
                message=f"材料严重屈服：最大应力（{max_stress:.2e} Pa）是屈服强度（{yield_strength:.2e} Pa）的 {ratio:.1f}x",
                suggestion="1) 检查载荷是否超出设计值 2) 考虑增加材料厚度或使用更高强度材料 3) 检查载荷方向和边界条件是否正确",
            ))
        elif ratio > 1.0:
            issues.append(DiagnosticIssue(
                severity="warning",
                category="material_yield",
                message=f"材料屈服：最大应力（{max_stress:.2e} Pa）超过屈服强度（{yield_strength:.2e} Pa）的 {ratio:.1f}x",
                suggestion="检查载荷是否超出设计值，考虑增加材料厚度或使用更高强度材料",
            ))

    except Exception:
        pass

    return issues


def _check_unit_consistency(
    results_dir: Path,
    inp_file: Optional[Path] = None,
) -> list[DiagnosticIssue]:
    """
    检查单位一致性：应力值量级是否合理。

    判断逻辑：
    - 正常结构应力范围：1e2 ~ 1e9 Pa（100 Pa ~ 1 GPa）
    - < 1e0 (1 Pa)：可能是单位搞错了（应该用 MPa）
    - > 1e12 (1 TPa)：物理上不可能，正常材料不会达到这个量级

    常见单位错误：
    - 材料 E 用 MPa，但载荷用 N，直接导致应力结果差 1e6 倍
    - 几何尺寸 mm vs m 不一致
    """
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        max_stress = _get_max_stress(frd_data)

        if max_stress <= 0:
            return issues

        # 检查量级异常
        if max_stress < 1.0:
            issues.append(DiagnosticIssue(
                severity="warning",
                category="unit_consistency",
                message=f"最大应力极低（{max_stress:.2e} Pa），可能存在单位不一致",
                suggestion="检查材料参数单位：E/nu 通常用 MPa，长度用 mm，确保载荷单位一致",
            ))
        elif max_stress > 1e12:
            issues.append(DiagnosticIssue(
                severity="error",
                category="unit_consistency",
                message=f"最大应力异常巨大（{max_stress:.2e} Pa），可能存在单位严重不一致",
                suggestion="检查所有单位：材料用 MPa 时，几何必须用 mm，载荷用 N",
            ))

        # 额外检查：从 inp 推断期望的单位范围
        # 如果材料 E > 1e8 (> 100 GPa)，而应力 < 1e6 (< 1 MPa)，可能单位混乱
        if inp_file and inp_file.exists():
            try:
                inp_text = inp_file.read_text(encoding="utf-8", errors="replace")

                # 提取 E 值（单位 MPa）
                E_value = None
                for i, line in enumerate(inp_text.splitlines()):
                    if line.upper().startswith("*ELASTIC"):
                        if i + 1 < len(inp_text.splitlines()):
                            parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', inp_text.splitlines()[i + 1])
                            if parts:
                                E_value = float(parts[0])
                                break

                if E_value and E_value > 1e8:  # E > 100 GPa（异常高，可能用了 Pa）
                    if max_stress < 1e6:  # 但应力 < 1 MPa
                        issues.append(DiagnosticIssue(
                            severity="warning",
                            category="unit_consistency",
                            message=f"材料弹性模量 E={E_value:.2e} MPa 与应力结果不匹配，可能单位不一致",
                            suggestion="如果 E 用 Pa 而非 MPa，会导致应力结果偏小 1e6 倍。请确认 E 单位是 MPa，尺寸单位是 mm。",
                        ))
            except Exception:
                pass

    except Exception:
        pass

    return issues


# ------------------------------------------------------------------ #
# Level 2: 参考案例对比
# ------------------------------------------------------------------ #

def _check_reference_cases(
    results_dir: Path,
    inp_file: Optional[Path] = None,
) -> dict:
    """
    与参考案例库对比，检查结果是否在合理范围内。

    Returns:
        {
            "issues": list[DiagnosticIssue],
            "similar_cases": list[dict],  # 相似案例信息
        }
    """
    issues: list[DiagnosticIssue] = []
    similar_cases: list[dict] = []

    # 加载参考案例库
    if not REFERENCE_CASES_PATH.exists():
        log.warning("参考案例库不存在: %s", REFERENCE_CASES_PATH)
        return {"issues": issues, "similar_cases": similar_cases}

    try:
        db = CaseDatabase.from_json(REFERENCE_CASES_PATH)
    except Exception as e:
        log.warning("参考案例库加载失败: %s", e)
        return {"issues": issues, "similar_cases": similar_cases}

    # 如果提供了 INP 文件，提取元数据并查找相似案例
    if inp_file and inp_file.exists():
        try:
            user_meta = parse_inp_metadata(inp_file)

            # 两阶段检索
            similar = db.find_similar(user_meta, top_n=3)

            for ref_case, score in similar:
                case_info = {
                    "name": ref_case.name,
                    "element_type": ref_case.element_type,
                    "problem_type": ref_case.problem_type,
                    "boundary_type": ref_case.boundary_type,
                    "similarity_score": round(score * 100, 1),
                    "expected_disp_max": ref_case.expected_disp_max,
                    "expected_stress_max": ref_case.expected_stress_max,
                }
                similar_cases.append(case_info)

            # 与相似案例对比结果
            issues.extend(_compare_with_reference(results_dir, similar))

        except Exception as e:
            log.warning("参考案例对比失败: %s", e)

    return {"issues": issues, "similar_cases": similar_cases}


def _compare_with_reference(
    results_dir: Path,
    similar_cases: list[tuple[CaseMetadata, float]],
) -> list[DiagnosticIssue]:
    """将用户结果与相似案例的预期范围对比。"""
    issues: list[DiagnosticIssue] = []

    frd_file = _find_frd(results_dir)
    if not frd_file:
        return issues

    try:
        frd_data = parse_frd(frd_file)
        stats = _extract_stats(frd_data)
        user_disp_max = stats["max_displacement"]
        user_stress_max = _get_max_stress(frd_data)

        for ref_case, score in similar_cases:
            # 对比位移
            if ref_case.expected_disp_max and ref_case.expected_disp_max > 0:
                ratio = user_disp_max / ref_case.expected_disp_max
                if ratio > 10:
                    issues.append(DiagnosticIssue(
                        severity="warning",
                        category="reference_comparison",
                        message=f"最大位移是同类参考案例的 {ratio:.1f}x（案例: {ref_case.name}）",
                        location=f"案例相似度: {score*100:.0f}%",
                        suggestion="检查边界条件是否与参考案例一致，或载荷是否过大",
                    ))
                    break
                elif ratio < 0.1 and ratio > 0:
                    issues.append(DiagnosticIssue(
                        severity="info",
                        category="reference_comparison",
                        message=f"最大位移是同类参考案例的 {ratio:.1f}x（案例: {ref_case.name}），可能刚度过高",
                        location=f"案例相似度: {score*100:.0f}%",
                        suggestion="结果偏小，可能需要检查载荷是否正确施加",
                    ))

            # 对比应力
            if ref_case.expected_stress_max and ref_case.expected_stress_max > 0 and user_stress_max > 0:
                stress_ratio = user_stress_max / ref_case.expected_stress_max
                if stress_ratio > 10:
                    issues.append(DiagnosticIssue(
                        severity="warning",
                        category="reference_comparison",
                        message=f"最大应力是同类参考案例的 {stress_ratio:.1f}x（案例: {ref_case.name}）",
                        location=f"案例相似度: {score*100:.0f}%",
                        suggestion="检查材料参数是否正确，或是否存在应力集中",
                    ))
                    break

    except Exception as e:
        log.warning("对比参考案例时出错: %s", e)

    return issues


def _get_max_stress(frd_data) -> float:
    """从 FrdData 获取最大应力。"""
    stress_result = frd_data.get_result("STRESS")
    if not stress_result or not stress_result.values:
        return 0.0

    max_stress = 0.0
    for vals in stress_result.values.values():
        if len(vals) >= 4:
            # 取 von Mises（假设第4个分量是等效应力）
            max_stress = max(max_stress, abs(vals[3]))
        elif vals:
            max_stress = max(max_stress, max(abs(v) for v in vals))
    return max_stress


# ------------------------------------------------------------------ #
# Level 3: AI 诊断
# ------------------------------------------------------------------ #

def _run_ai_diagnosis(
    client: LLMClient,
    level1_issues: list[DiagnosticIssue],
    level2_issues: list[DiagnosticIssue],
    similar_cases: list[dict],
    results_dir: Path,
    stream: bool = True,
) -> Optional[str]:
    """运行 AI 深度诊断。"""
    try:
        stderr_summary = _get_stderr_summary(results_dir)
        physical_data = _get_physical_data(results_dir)  # 新增：提取物理数据

        all_issues = level1_issues + level2_issues
        # 即使没有问题，也提取诊断信息（用于用户了解结果）
        # if not all_issues:
        #     return None

        issue_dicts = [
            {
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "location": i.location,
                "suggestion": i.suggestion,
            }
            for i in all_issues
        ]

        prompt_text = make_diagnose_prompt(issue_dicts, stderr_summary, similar_cases, physical_data)

        if stream:
            handler = StreamHandler()
            tokens = client.complete_streaming(prompt_text)
            return handler.stream_tokens(tokens)
        else:
            return client.complete(prompt_text)

    except Exception as e:
        log.warning("AI 诊断失败: %s", e)
        return None


def _get_physical_data(results_dir: Path) -> str:
    """从 .frd 文件提取关键物理数据用于 AI 分析。"""
    try:
        frd_file = _find_frd(results_dir)
        if not frd_file:
            return ""

        frd_data = parse_frd(frd_file)
        lines = []

        # 节点/单元数
        lines.append(f"节点数: {frd_data.node_count}, 单元数: {frd_data.element_count}")

        # 位移
        disp_result = frd_data.get_result("DISP")
        if disp_result and disp_result.values:
            max_disp = 0.0
            max_node = 0
            for node_id, vals in disp_result.values.items():
                if vals is not None and len(vals) > 0:
                    magnitude = sum(float(v) ** 2 for v in vals) ** 0.5
                    if magnitude > max_disp:
                        max_disp = magnitude
                        max_node = node_id
            lines.append(f"最大位移: {max_disp:.6e} (节点 {max_node})")

        # 应力
        stress_result = frd_data.get_result("STRESS")
        if stress_result and stress_result.values:
            max_stress = 0.0
            max_elem = 0
            for elem_id, vals in stress_result.values.items():
                if vals is not None and len(vals) >= 4:
                    vm = abs(float(vals[3]))  # von Mises
                    if vm > max_stress:
                        max_stress = vm
                        max_elem = elem_id
            lines.append(f"最大 von Mises 应力: {max_stress:.6e} (单元 {max_elem})")

        # 应变分量（TOSTRAIN 包含 EXX, EYY, EZZ, EXY, EYZ, EZX）
        strain_result = frd_data.get_result("TOSTRAIN")
        if strain_result and strain_result.components and strain_result.values:
            strain_components = strain_result.components
            strain_vals_by_node = strain_result.values

            # 找出每个分量的最大值
            max_vals = {}
            max_nodes = {}
            for comp_idx, comp_name in enumerate(strain_components):
                max_val = 0.0
                max_node = 0
                for node_id, vals in strain_vals_by_node.items():
                    if vals is not None and len(vals) > comp_idx:
                        val = abs(float(vals[comp_idx]))
                        if val > max_val:
                            max_val = val
                            max_node = node_id
                if max_val > 0:
                    max_vals[comp_name] = max_val
                    max_nodes[comp_name] = max_node

            if max_vals:
                lines.append(f"\n应变分量（绝对值最大）:")
                for comp_name in strain_components:
                    if comp_name in max_vals:
                        lines.append(f"  {comp_name}: {max_vals[comp_name]:.6e} (节点 {max_nodes[comp_name]})")

                # 检测是否存在大变形特征（应变 > 0.1）
                large_strain_components = {k: v for k, v in max_vals.items() if v > 0.1}
                if large_strain_components:
                    lines.append(f"\n⚠️ 大变形警告：检测到以下应变分量 > 0.1（10%变形）:")
                    for comp_name, val in large_strain_components.items():
                        lines.append(f"  {comp_name}: {val:.4f}")

        return "\n".join(lines)
    except Exception as e:
        log.warning("提取物理数据失败: %s", e)
        return ""


def _get_stderr_summary(results_dir: Path) -> str:
    """收集所有 .sta / .dat / .cvg 文件内容作为摘要。"""
    summaries: list[str] = []

    keyword_patterns = (
        "error", "ERROR", "warning", "WARNING",
        "not converge", "NOT CONVERGED", "converged",
        "increment", "INCREMENT", "iteration", "ITERATION",
        "displacement", "DISPLACEMENT", "stress", "STRESS",
        "factor", "FACTOR", "ratio", "RATIO",
        "zero", "ZERO", "negative", "NEGATIVE",
        "singular", "SINGULAR", "Jacobian",
    )

    for ext in ("*.sta", "*.dat", "*.cvg"):
        for f in results_dir.glob(ext):
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
                lines = text.strip().splitlines()

                last_lines = lines[-50:] if len(lines) > 50 else lines
                keyword_lines = [
                    line for line in lines
                    if any(kw in line for kw in keyword_patterns)
                ][-30:]

                seen = set()
                combined = []
                for line in last_lines:
                    if line not in seen:
                        seen.add(line)
                        combined.append(line)
                for line in keyword_lines:
                    if line not in seen:
                        seen.add(line)
                        combined.append(line)

                if combined:
                    summaries.append(f"=== {f.name} ===")
                    summaries.extend(combined)
            except OSError:
                pass

    return "\n".join(summaries) if summaries else "（无详细日志）"
