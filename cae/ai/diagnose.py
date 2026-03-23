# diagnose.py
"""
三层次诊断系统

Level 1: 规则检测（无条件执行）
  - 收敛性：stderr 含 *ERROR 或 returncode != 0
  - 网格质量：节点/单元比例异常
  - 应力集中：应力梯度突变 > 50x
  - 位移范围：最大位移 > 模型尺寸 10%

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
    results_dir: Path,
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

    try:
        # ========== Level 1: 规则检测（无条件执行）==========
        result.level1_issues.extend(_check_convergence(results_dir))
        result.level1_issues.extend(_check_frd_quality(results_dir))
        result.level1_issues.extend(_check_stress_gradient(results_dir))
        result.level1_issues.extend(_check_displacement_range(results_dir))

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

def _check_convergence(results_dir: Path) -> list[DiagnosticIssue]:
    """检查收敛性：stderr / sta 文件中是否有 *ERROR。"""
    issues: list[DiagnosticIssue] = []

    # 检查 .sta 文件
    for sta in results_dir.glob("*.sta"):
        try:
            text = sta.read_text(encoding="utf-8", errors="replace")
            if "*ERROR" in text or "error" in text.lower():
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="convergence",
                    message="求解器报告 *ERROR，收敛失败",
                    location=str(sta.name),
                    suggestion="检查边界条件、载荷是否合理，或增大迭代次数",
                ))
        except OSError:
            pass

    # 检查 .cvg 文件
    for cvg in results_dir.glob("*.cvg"):
        try:
            text = cvg.read_text(encoding="utf-8", errors="replace")
            if "NOT" in text and "CONVERGED" in text:
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="convergence",
                    message="迭代未收敛",
                    location=str(cvg.name),
                    suggestion="检查载荷步设置，增大迭代次数或调整收敛容差",
                ))
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

        all_issues = level1_issues + level2_issues
        if not all_issues:
            return None

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

        prompt_text = make_diagnose_prompt(issue_dicts, stderr_summary, similar_cases)

        if stream:
            handler = StreamHandler()
            tokens = client.complete_streaming(prompt_text)
            return handler.stream_tokens(tokens)
        else:
            return client.complete(prompt_text)

    except Exception as e:
        log.warning("AI 诊断失败: %s", e)
        return None


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
