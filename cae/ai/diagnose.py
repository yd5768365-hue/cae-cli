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
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import make_diagnose_prompt_v2
from .stream_handler import StreamHandler
from .explain import _find_frd, _extract_stats
from .reference_cases import CaseMetadata, CaseDatabase, parse_inp_metadata, ClassificationTree
from cae.viewer.frd_parser import FrdData, parse_frd

log = logging.getLogger(__name__)

DIAGNOSE_RESULT_NAMES = {"DISP", "STRESS", "TOSTRAIN"}
_FRD_PREFIX_WIDTH = 13
_FRD_VALUE_WIDTH = 12

# 参考案例库路径
REFERENCE_CASES_PATH = Path(__file__).parent / "data" / "reference_cases.json"
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
CATEGORY_TITLES = {
    "boundary_condition": "Boundary Condition Issue",
    "convergence": "Convergence Issue",
    "contact": "Contact Definition Issue",
    "displacement": "Displacement Range Issue",
    "dynamics": "Dynamics Analysis Issue",
    "element_quality": "Element Quality Issue",
    "file_io": "File I/O Issue",
    "input_syntax": "Input Syntax Issue",
    "large_strain": "Large Strain Issue",
    "limit_exceeded": "Solver Limit Exceeded",
    "load_transfer": "Load Transfer Issue",
    "material": "Material Definition Issue",
    "material_yield": "Material Yield Issue",
    "mesh_quality": "Mesh Quality Issue",
    "reference_comparison": "Reference Comparison Issue",
    "rigid_body_mode": "Rigid Body Mode Risk",
    "stress_concentration": "Stress Concentration Issue",
    "unit_consistency": "Unit Consistency Issue",
    "user_element": "User Element Issue",
}
PRIORITY_BY_CATEGORY = {
    "file_io": 1,
    "input_syntax": 1,
    "material": 1,
    "boundary_condition": 1,
    "load_transfer": 1,
    "convergence": 2,
    "contact": 2,
    "rigid_body_mode": 2,
    "element_quality": 2,
    "limit_exceeded": 2,
    "unit_consistency": 3,
    "large_strain": 3,
    "material_yield": 3,
    "mesh_quality": 3,
    "stress_concentration": 3,
    "displacement": 3,
    "dynamics": 3,
    "reference_comparison": 4,
    "user_element": 4,
}
INVALID_SYNTAX_PATTERNS = [
    r"\*C\s+LOAD",
    r"E\s*=\s*[\d.e+\-]+",
    r"DLOAD\s+\d+\s+\d+",
    r"at\s+node\s+\d+",
]
AI_OUTPUT_SYNTAX_WARNING = (
    "注意：AI 生成的代码片段已被移除，请参考 CalculiX 文档确认正确语法。"
)


@dataclass
class DiagnosticIssue:
    """诊断问题条目。"""
    severity: str  # "error" | "warning" | "info"
    category: str  # "convergence" | "mesh_quality" | "stress_concentration" | "displacement" | "reference_comparison"
    message: str
    location: Optional[str] = None
    suggestion: Optional[str] = None
    priority: Optional[int] = None
    auto_fixable: Optional[bool] = None

    @property
    def title(self) -> str:
        return CATEGORY_TITLES.get(self.category, self.category.replace("_", " ").title())

    @property
    def cause(self) -> str:
        return self.message.strip()

    @property
    def action(self) -> str:
        return (self.suggestion or "").strip()


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
        return normalize_issues(self.level1_issues + self.level2_issues)

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass
class FrdDiagnosticSummary:
    """Minimal FRD summary used by AI diagnosis."""

    node_count: int = 0
    element_count: int = 0
    model_bounds: tuple[float, float, float] = (1.0, 1.0, 1.0)
    disp_count: int = 0
    disp_sum: float = 0.0
    max_displacement: float = 0.0
    max_displacement_node: int = 0
    stress_values: list[float] = field(default_factory=list, repr=False)
    max_stress: float = 0.0
    max_stress_id: int = 0
    max_strain: float = 0.0
    max_strain_component: str = ""
    max_strain_node: int = 0


@dataclass
class DiagnosisContext:
    """Single-run cache for expensive diagnosis inputs."""

    results_dir: Path
    inp_file: Optional[Path] = None
    text_cache: dict[Path, str] = field(default_factory=dict, repr=False)
    line_cache: dict[Path, list[str]] = field(default_factory=dict, repr=False)
    glob_cache: dict[str, list[Path]] = field(default_factory=dict, repr=False)
    frd_file: Optional[Path] = field(default=None, repr=False)
    frd_file_loaded: bool = field(default=False, repr=False)
    frd_data: Optional[FrdData] = field(default=None, repr=False)
    frd_data_loaded: bool = field(default=False, repr=False)
    frd_summary: Optional[FrdDiagnosticSummary] = field(default=None, repr=False)
    frd_summary_loaded: bool = field(default=False, repr=False)
    frd_stats: Optional[dict] = field(default=None, repr=False)
    frd_stats_loaded: bool = field(default=False, repr=False)
    yield_strength_cache: dict[Path, Optional[float]] = field(default_factory=dict, repr=False)


def _build_context(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> DiagnosisContext:
    if ctx is not None:
        if inp_file is not None and ctx.inp_file is None:
            ctx.inp_file = inp_file
        return ctx
    return DiagnosisContext(results_dir=results_dir, inp_file=inp_file)


def _normalize_text_key(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"\s+", " ", lowered)
    lowered = re.sub(r"[^\w\s]+", "", lowered)
    return lowered


def _issue_dedup_key(issue: DiagnosticIssue) -> tuple[str, str]:
    return issue.category, _normalize_text_key(issue.message)


def _infer_priority(issue: DiagnosticIssue) -> int:
    if issue.priority is not None:
        return issue.priority
    base = PRIORITY_BY_CATEGORY.get(issue.category, 4)
    severity_rank = SEVERITY_ORDER.get(issue.severity, 2)
    return min(5, base + severity_rank)


def _infer_auto_fixable(issue: DiagnosticIssue) -> bool:
    if issue.auto_fixable is not None:
        return issue.auto_fixable

    message_key = _normalize_text_key(issue.message)
    suggestion_key = _normalize_text_key(issue.suggestion or "")

    if issue.category == "material" and "elastic" in message_key:
        return True
    if issue.category == "input_syntax" and "step" in message_key:
        return True
    if issue.category == "convergence" and (
        "increment" in message_key or "increment" in suggestion_key or "static" in suggestion_key
    ):
        return True
    return False


def _should_replace_issue(current: DiagnosticIssue, candidate: DiagnosticIssue) -> bool:
    current_rank = SEVERITY_ORDER.get(current.severity, 2)
    candidate_rank = SEVERITY_ORDER.get(candidate.severity, 2)
    if candidate_rank != current_rank:
        return candidate_rank < current_rank

    current_has_suggestion = bool((current.suggestion or "").strip())
    candidate_has_suggestion = bool((candidate.suggestion or "").strip())
    if candidate_has_suggestion != current_has_suggestion:
        return candidate_has_suggestion

    current_priority = _infer_priority(current)
    candidate_priority = _infer_priority(candidate)
    if candidate_priority != current_priority:
        return candidate_priority < current_priority

    current_has_location = bool((current.location or "").strip())
    candidate_has_location = bool((candidate.location or "").strip())
    return candidate_has_location and not current_has_location


def normalize_issues(issues: list[DiagnosticIssue]) -> list[DiagnosticIssue]:
    deduped: dict[tuple[str, str], DiagnosticIssue] = {}
    for issue in issues:
        normalized = DiagnosticIssue(
            severity=issue.severity,
            category=issue.category,
            message=issue.message.strip(),
            location=issue.location.strip() if issue.location else None,
            suggestion=issue.suggestion.strip() if issue.suggestion else None,
            priority=_infer_priority(issue),
            auto_fixable=_infer_auto_fixable(issue),
        )
        key = _issue_dedup_key(normalized)
        existing = deduped.get(key)
        if existing is None or _should_replace_issue(existing, normalized):
            deduped[key] = normalized

    return sorted(
        deduped.values(),
        key=lambda issue: (
            SEVERITY_ORDER.get(issue.severity, 2),
            issue.priority if issue.priority is not None else 99,
            issue.category,
            _normalize_text_key(issue.message),
        ),
    )


def build_diagnosis_summary(issues: list[DiagnosticIssue]) -> dict:
    normalized = normalize_issues(issues)
    errors = [issue for issue in normalized if issue.severity == "error"]
    warnings = [issue for issue in normalized if issue.severity == "warning"]
    auto_fixable = [issue for issue in normalized if issue.auto_fixable]
    top_issue = normalized[0] if normalized else None
    return {
        "total": len(normalized),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "auto_fixable_count": len(auto_fixable),
        "top_issue": top_issue,
        "first_action": top_issue.action if top_issue else "",
    }


def _glob_cached(
    results_dir: Path,
    pattern: str,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[Path]:
    if ctx is None:
        return list(results_dir.glob(pattern))
    if pattern not in ctx.glob_cache:
        ctx.glob_cache[pattern] = list(results_dir.glob(pattern))
    return ctx.glob_cache[pattern]


def _read_text_cached(path: Path, *, ctx: Optional[DiagnosisContext] = None) -> str:
    if ctx is None:
        return path.read_text(encoding="utf-8", errors="replace")
    if path not in ctx.text_cache:
        ctx.text_cache[path] = path.read_text(encoding="utf-8", errors="replace")
    return ctx.text_cache[path]


def _read_lines_cached(path: Path, *, ctx: Optional[DiagnosisContext] = None) -> list[str]:
    if ctx is None:
        return _read_text_cached(path).splitlines()
    if path not in ctx.line_cache:
        ctx.line_cache[path] = _read_text_cached(path, ctx=ctx).splitlines()
    return ctx.line_cache[path]


def _iter_result_texts(
    results_dir: Path,
    patterns: tuple[str, ...],
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in _glob_cached(results_dir, pattern, ctx=ctx):
            if path in seen:
                continue
            seen.add(path)
            try:
                items.append((path, _read_text_cached(path, ctx=ctx)))
            except OSError:
                continue
    return items


def _get_inp_text(
    inp_file: Optional[Path],
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[str]:
    target = inp_file or (ctx.inp_file if ctx else None)
    if not target or not target.exists():
        return None
    try:
        return _read_text_cached(target, ctx=ctx)
    except OSError:
        return None


def _get_inp_lines(
    inp_file: Optional[Path],
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[str]:
    target = inp_file or (ctx.inp_file if ctx else None)
    if not target or not target.exists():
        return []
    try:
        return _read_lines_cached(target, ctx=ctx)
    except OSError:
        return []


def _get_frd_data(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[FrdData]:
    if ctx is None:
        frd_file = _find_frd(results_dir)
        return (
            parse_frd(
                frd_file,
                result_names=DIAGNOSE_RESULT_NAMES,
                include_element_connectivity=False,
            )
            if frd_file
            else None
        )

    if not ctx.frd_file_loaded:
        ctx.frd_file = _find_frd(results_dir)
        ctx.frd_file_loaded = True

    if not ctx.frd_file:
        return None

    if not ctx.frd_data_loaded:
        ctx.frd_data = parse_frd(
            ctx.frd_file,
            result_names=DIAGNOSE_RESULT_NAMES,
            include_element_connectivity=False,
        )
        ctx.frd_data_loaded = True

    return ctx.frd_data


def _parse_frd_row(line: str, value_count: int) -> Optional[tuple[int, tuple[float, ...]]]:
    """Fast path for standard fixed-width FRD rows."""
    if value_count <= 0:
        return None

    expected_len = _FRD_PREFIX_WIDTH + value_count * _FRD_VALUE_WIDTH
    if len(line) != expected_len:
        return None

    try:
        row_id = int(line[3:_FRD_PREFIX_WIDTH])
        if value_count == 3:
            values = (
                float(line[13:25]),
                float(line[25:37]),
                float(line[37:49]),
            )
        elif value_count == 6:
            values = (
                float(line[13:25]),
                float(line[25:37]),
                float(line[37:49]),
                float(line[49:61]),
                float(line[61:73]),
                float(line[73:85]),
            )
        else:
            values = tuple(
                float(line[offset: offset + _FRD_VALUE_WIDTH])
                for offset in range(_FRD_PREFIX_WIDTH, expected_len, _FRD_VALUE_WIDTH)
            )
    except ValueError:
        return None

    return row_id, values


def _parse_frd_row_fallback(line: str) -> Optional[tuple[int, tuple[float, ...]]]:
    matches = re.findall(r"[+-]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?", line)
    if len(matches) < 3:
        return None
    try:
        return int(matches[1]), tuple(map(float, matches[2:]))
    except (ValueError, IndexError):
        return None


def _parse_frd_summary(frd_file: Path) -> FrdDiagnosticSummary:
    """Parse only the FRD data required by AI diagnosis."""
    summary = FrdDiagnosticSummary()

    min_x = min_y = min_z = float("inf")
    max_x = max_y = max_z = float("-inf")

    with frd_file.open(encoding="latin-1", errors="replace") as handle:
        while True:
            raw_line = handle.readline()
            if not raw_line:
                break

            line = raw_line.rstrip("\r\n")

            if line.startswith("    1C") or line.startswith("    1PSET"):
                while True:
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    line = raw_line.rstrip("\r\n")
                    if line.startswith(" -3"):
                        break
                    if not line.startswith(" -1"):
                        continue

                    parsed = _parse_frd_row(line, 3) or _parse_frd_row_fallback(line)
                    if parsed is None:
                        continue

                    nid, (x, y, z) = parsed
                    if nid <= 0:
                        continue
                    summary.node_count += 1
                    min_x = min(min_x, x)
                    min_y = min(min_y, y)
                    min_z = min(min_z, z)
                    max_x = max(max_x, x)
                    max_y = max(max_y, y)
                    max_z = max(max_z, z)
                continue

            if line.startswith("    2C") or line.startswith("    2PSET") or line.startswith("    3C") or line.startswith("    3PSET"):
                while True:
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    line = raw_line.rstrip("\r\n")
                    if line.startswith(" -3"):
                        break
                    if line.startswith(" -1"):
                        summary.element_count += 1
                continue

            if line.startswith("  100C"):
                parts = line.split()
                field_name = parts[1].upper() if len(parts) >= 2 else ""
                components: list[str] = []
                local_disp_count = 0
                local_disp_sum = 0.0
                local_max_disp = 0.0
                local_max_disp_node = 0
                local_stress_values: list[float] = []
                local_max_stress = 0.0
                local_max_stress_id = 0
                local_max_strain = 0.0
                local_max_strain_component = ""
                local_max_strain_node = 0
                capture_block = field_name in DIAGNOSE_RESULT_NAMES

                while True:
                    raw_line = handle.readline()
                    if not raw_line:
                        break
                    line = raw_line.rstrip("\r\n")

                    if line.startswith(" -4"):
                        parts4 = line.split()
                        if len(parts4) >= 2 and not parts4[1].isdigit():
                            field_name = parts4[1].upper()
                            capture_block = field_name in DIAGNOSE_RESULT_NAMES
                        continue

                    if line.startswith(" -5"):
                        if capture_block and field_name == "TOSTRAIN":
                            parts5 = line.split()
                            if len(parts5) >= 2:
                                components.append(parts5[1])
                        continue

                    if line.startswith(" -1"):
                        if not capture_block:
                            continue

                        value_count = len(components) if field_name == "TOSTRAIN" else 0
                        parsed = None
                        if field_name == "DISP":
                            parsed = _parse_frd_row(line, 3)
                        elif field_name == "STRESS":
                            parsed = _parse_frd_row(line, 6)
                        elif field_name == "TOSTRAIN" and value_count > 0:
                            parsed = _parse_frd_row(line, value_count)

                        parsed = parsed or _parse_frd_row_fallback(line)
                        if parsed is None:
                            continue

                        row_id, values = parsed
                        if not values:
                            continue

                        if field_name == "DISP":
                            if len(values) >= 3:
                                magnitude = (values[0] ** 2 + values[1] ** 2 + values[2] ** 2) ** 0.5
                            else:
                                magnitude = abs(values[0])
                            local_disp_count += 1
                            local_disp_sum += magnitude
                            if magnitude > local_max_disp:
                                local_max_disp = magnitude
                                local_max_disp_node = row_id
                        elif field_name == "STRESS":
                            stress_value = abs(values[3]) if len(values) >= 4 else max(abs(v) for v in values)
                            local_stress_values.append(stress_value)
                            if stress_value > local_max_stress:
                                local_max_stress = stress_value
                                local_max_stress_id = row_id
                        elif field_name == "TOSTRAIN":
                            for comp_idx, comp_name in enumerate(components):
                                if len(values) <= comp_idx:
                                    break
                                strain_value = abs(values[comp_idx])
                                if strain_value > local_max_strain:
                                    local_max_strain = strain_value
                                    local_max_strain_component = comp_name
                                    local_max_strain_node = row_id
                        continue

                    if line.startswith(" -3"):
                        break

                if field_name == "DISP":
                    summary.disp_count = local_disp_count
                    summary.disp_sum = local_disp_sum
                    summary.max_displacement = local_max_disp
                    summary.max_displacement_node = local_max_disp_node
                elif field_name == "STRESS":
                    summary.stress_values = local_stress_values
                    summary.max_stress = local_max_stress
                    summary.max_stress_id = local_max_stress_id
                elif field_name == "TOSTRAIN":
                    summary.max_strain = local_max_strain
                    summary.max_strain_component = local_max_strain_component
                    summary.max_strain_node = local_max_strain_node
                continue

            if line.strip() == "9999":
                break

    if summary.node_count > 0:
        summary.model_bounds = (
            max_x - min_x,
            max_y - min_y,
            max_z - min_z,
        )

    return summary


def _get_frd_summary(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[FrdDiagnosticSummary]:
    if ctx is None:
        frd_file = _find_frd(results_dir)
        return _parse_frd_summary(frd_file) if frd_file else None

    if not ctx.frd_file_loaded:
        ctx.frd_file = _find_frd(results_dir)
        ctx.frd_file_loaded = True

    if not ctx.frd_file:
        return None

    if not ctx.frd_summary_loaded:
        ctx.frd_summary = _parse_frd_summary(ctx.frd_file)
        ctx.frd_summary_loaded = True

    return ctx.frd_summary


def _get_frd_stats(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[dict]:
    summary = _get_frd_summary(results_dir, ctx=ctx)
    if summary is None:
        return None

    if ctx is None:
        return {
            "node_count": summary.node_count,
            "element_count": summary.element_count,
            "max_displacement": summary.max_displacement,
            "max_displacement_node": summary.max_displacement_node,
            "max_stress": summary.max_stress,
            "max_stress_element": summary.max_stress_id,
            "stress_component": "von Mises",
            "material_yield": 250e6,
            "model_bounds": summary.model_bounds,
        }

    if not ctx.frd_stats_loaded:
        ctx.frd_stats = {
            "node_count": summary.node_count,
            "element_count": summary.element_count,
            "max_displacement": summary.max_displacement,
            "max_displacement_node": summary.max_displacement_node,
            "max_stress": summary.max_stress,
            "max_stress_element": summary.max_stress_id,
            "stress_component": "von Mises",
            "material_yield": 250e6,
            "model_bounds": summary.model_bounds,
        }
        ctx.frd_stats_loaded = True

    return ctx.frd_stats


@lru_cache(maxsize=1)
def _load_reference_case_db() -> Optional[CaseDatabase]:
    if not REFERENCE_CASES_PATH.exists():
        return None
    try:
        return CaseDatabase.from_json(REFERENCE_CASES_PATH)
    except Exception as exc:
        log.warning("参考案例库加载失败: %s", exc)
        return None


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

    ctx = _build_context(results_dir, inp_file)

    try:
        # ========== Level 1: 规则检测（无条件执行）==========
        result.level1_issues.extend(_check_convergence(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_time_increment_stagnation(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_input_syntax(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_material_definition(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_parameter_syntax(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_element_quality(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_frd_quality(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_stress_gradient(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_displacement_range(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_large_strain(results_dir, inp_file, ctx=ctx))
        result.level1_issues.extend(_check_rigid_body_mode(results_dir, inp_file, ctx=ctx))
        result.level1_issues.extend(_check_material_yield(results_dir, inp_file, ctx=ctx))
        result.level1_issues.extend(_check_unit_consistency(results_dir, inp_file, ctx=ctx))
        result.level1_issues.extend(_check_load_transfer(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_boundary_issues(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_contact_issues(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_file_io_errors(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_user_element_errors(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_mpc_limits(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_dynamics_errors(results_dir, ctx=ctx))
        result.level1_issues.extend(_check_inp_file_quality(inp_file, ctx=ctx))
        result.level1_issues = normalize_issues(result.level1_issues)

        # ========== Level 2: 参考案例对比（无条件执行）==========
        ref_result = _check_reference_cases(results_dir, inp_file, ctx=ctx)
        result.level2_issues = normalize_issues(ref_result["issues"])
        result.similar_cases = ref_result["similar_cases"]

        # ========== Level 3: AI 深度分析（仅当规则层发现真实问题时才调用）==========
        # 只有 level1 的 error/warning 才是真实问题，level2 的 info 参考信息不触发 LLM
        real_issues = [
            i for i in result.level1_issues
            if i.severity in ("error", "warning")
        ]
        if not real_issues:
            result.level3_diagnosis = None
        elif client is not None:
            result.level3_diagnosis = _run_ai_diagnosis(
                client,
                result.level1_issues,
                result.level2_issues,
                result.similar_cases,
                results_dir,
                inp_file=inp_file,
                stream=stream,
                ctx=ctx,
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

# 收敛性问题检测模式（增强自 calculix_patterns.txt）
CONVERGENCE_PATTERNS = [
    re.compile(r"not\s+converged", re.IGNORECASE),
    re.compile(r"increment\s+size\s+smaller", re.IGNORECASE),
    re.compile(r"divergence", re.IGNORECASE),
    re.compile(r"no\s+convergence", re.IGNORECASE),
    re.compile(r"convergence\s+failed", re.IGNORECASE),
    re.compile(r"fatal error", re.IGNORECASE),
    re.compile(r"ddebdf\s+did\s+not\s+converge", re.IGNORECASE),
]

# 无效 INP 卡片检测模式
INVALID_CARD_PATTERNS = [
    re.compile(r"card image cannot be interpreted", re.IGNORECASE),
    re.compile(r"unknown keyword", re.IGNORECASE),
]

# 材料缺失检测模式（来自 CalculiX 源码 528 模式）
MATERIAL_PATTERNS = [
    re.compile(r"no elastic constants", re.IGNORECASE),
    re.compile(r"no density was assigned", re.IGNORECASE),
    re.compile(r"no material was assigned", re.IGNORECASE),
    re.compile(r"no specific heat", re.IGNORECASE),
    re.compile(r"no conductivity", re.IGNORECASE),
    re.compile(r"no magnetic constants", re.IGNORECASE),
    re.compile(r"no anisotropic material", re.IGNORECASE),
    re.compile(r"no orthotropic material", re.IGNORECASE),
    re.compile(r"no second order", re.IGNORECASE),
    re.compile(r"no thermal", re.IGNORECASE),
    re.compile(r"no body forces", re.IGNORECASE),
    re.compile(r"no buckling", re.IGNORECASE),
    re.compile(r"no coriolis", re.IGNORECASE),
    re.compile(r"no offset", re.IGNORECASE),
    re.compile(r"no orientation", re.IGNORECASE),
]

# 参数不识别检测模式
PARAMETER_PATTERNS = [
    re.compile(r"parameter not recognized", re.IGNORECASE),
]

# MPC/约束数量超限检测模式（来自 CalculiX 源码）
MPC_LIMIT_PATTERNS = [
    re.compile(r"increase nmpc_", re.IGNORECASE),
    re.compile(r"increase nboun_", re.IGNORECASE),
    re.compile(r"increase nk_", re.IGNORECASE),
    re.compile(r"increase memmpc_", re.IGNORECASE),
    re.compile(r"increase nbody_", re.IGNORECASE),
    re.compile(r"increase nforc_", re.IGNORECASE),
    re.compile(r"increase nload_", re.IGNORECASE),
    re.compile(r"increase norien_", re.IGNORECASE),
    re.compile(r"increase namtot_", re.IGNORECASE),
    re.compile(r"increase nprint_", re.IGNORECASE),
    re.compile(r"increase the dimension", re.IGNORECASE),
]

# 载荷传递问题检测模式
LOAD_TRANSFER_PATTERNS = [
    re.compile(r"RHS only consists of 0\.0", re.IGNORECASE),
    re.compile(r"concentrated loads:\s*0\s*$", re.IGNORECASE | re.MULTILINE),
]

# 边界条件问题检测模式
BOUNDARY_PATTERNS = [
    re.compile(r"zero pivot", re.IGNORECASE),
    re.compile(r"singular matrix", re.IGNORECASE),
    re.compile(r"欠约束|underconstrained", re.IGNORECASE),
    re.compile(r"过约束|overconstrained", re.IGNORECASE),
]

# 网格质量问题检测模式
MESH_QUALITY_PATTERNS = [
    re.compile(r"negative.*jacobian", re.IGNORECASE),
    re.compile(r"distorted.*element", re.IGNORECASE),
    re.compile(r"element.*invert", re.IGNORECASE),
    re.compile(r"skewness", re.IGNORECASE),
    re.compile(r"aspect ratio", re.IGNORECASE),
]

# 接触问题检测模式（增强自 calculix_patterns.txt）
CONTACT_PATTERNS = [
    re.compile(r"contact.*not.*found", re.IGNORECASE),
    re.compile(r"overclosure", re.IGNORECASE),
    re.compile(r"contact.*stress.*negative", re.IGNORECASE),
    re.compile(r"master.*slave", re.IGNORECASE),
    re.compile(r"contact.*open", re.IGNORECASE),
    re.compile(r"slave surface", re.IGNORECASE),
    re.compile(r"master surface", re.IGNORECASE),
    re.compile(r"slave node", re.IGNORECASE),
    re.compile(r"contact slave set", re.IGNORECASE),
    re.compile(r"no tied MPC", re.IGNORECASE),
    re.compile(r"tied MPC", re.IGNORECASE),
    re.compile(r"contact.*adjust", re.IGNORECASE),
]

# 文件 I/O 错误检测模式（来自 CalculiX 源码）
FILE_IO_PATTERNS = [
    re.compile(r"could not open file", re.IGNORECASE),
    re.compile(r"file name is lacking", re.IGNORECASE),
    re.compile(r"file name too long", re.IGNORECASE),
    re.compile(r"input file name is too long", re.IGNORECASE),
    re.compile(r"could not open", re.IGNORECASE),
    re.compile(r"could not delete file", re.IGNORECASE),
    re.compile(r"syntax error", re.IGNORECASE),
]

# 用户单元/材料错误检测模式（来自 CalculiX 源码）
USER_ELEMENT_PATTERNS = [
    re.compile(r"user element", re.IGNORECASE),
    re.compile(r"umat", re.IGNORECASE),
    re.compile(r"no user material subroutine", re.IGNORECASE),
    re.compile(r"user subroutine", re.IGNORECASE),
]

# 动力学/模态分析错误模式（来自 CalculiX 源码）
DYNAMICS_PATTERNS = [
    re.compile(r"eigenvalue", re.IGNORECASE),
    re.compile(r"frequencies:.*less than 1 eigenvalue", re.IGNORECASE),
    re.compile(r"modal dynamic", re.IGNORECASE),
    re.compile(r"cyclic symmetric", re.IGNORECASE),
    re.compile(r"alpha is greater", re.IGNORECASE),
    re.compile(r"alpha is smaller", re.IGNORECASE),
]


def _check_convergence(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查收敛性：扫描 .sta / .dat / .cvg 文件中的收敛相关错误。

    检测模式：
    - *ERROR：求解器明确报错
    - NOT CONVERGED：迭代未收敛
    - INCREMENT SIZE SMALLER：增量步小于最小值（收敛困难）
    - DIVERGENCE：发散
    """
    issues: list[DiagnosticIssue] = []

    for file_path, text in _iter_result_texts(
        results_dir,
        ("*.sta", "*.dat", "*.cvg", "*.stderr"),
        ctx=ctx,
    ):
        file_label = file_path.name

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

    return issues


def _check_time_increment_stagnation(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查时间增量停滞：连续5个增量步 INC TIME 不增大。

    扫描 .sta 和 .stderr 文件，解析 "increment size=" 模式，
    连续5个增量步的时间增量没有增加则触发警告。
    """
    issues: list[DiagnosticIssue] = []

    import re

    for file_path, text in _iter_result_texts(results_dir, ("*.sta", "*.stderr"), ctx=ctx):
        file_label = file_path.name

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

    return issues


def _check_input_syntax(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查 INP 输入文件语法：无效卡片等错误。

    扫描 .stderr 文件，匹配以下模式：
    - "card image cannot be interpreted"：无法识别的卡片
    - "unknown keyword"：未知关键词
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
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

    return issues


def _check_material_definition(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查材料定义完整性：材料属性缺失等错误。

    扫描 .stderr 文件，匹配以下模式（来自 CalculiX 源码）：
    - "no elastic constants"：缺少弹性常数
    - "no density was assigned"：缺少密度
    - "no material was assigned"：未分配材料
    - "no specific heat"：缺少比热容
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
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

    return issues


def _check_parameter_syntax(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查卡片参数语法：参数不识别等错误。

    扫描 .stderr 文件，匹配 "parameter not recognized" 模式。
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        if PARAMETER_PATTERNS[0].search(text):
            issues.append(DiagnosticIssue(
                severity="error",
                category="input_syntax",
                message="卡片参数不被识别",
                location=stderr_file.name,
                suggestion="检查卡片参数拼写是否正确。CalculiX 参数名区分大小写，常见错误：PARAMETERS 而非 PARAMETER",
            ))
            break

    return issues


def _check_load_transfer(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查载荷传递问题：载荷未正确传递到结构。

    扫描 .stderr 文件，匹配以下模式：
    - "RHS only consists of 0.0"：载荷向量为零，通常是耦合约束配置错误
    - "concentrated loads: 0"：集中载荷数量为零
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in LOAD_TRANSFER_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "rhs only consists of 0.0" in matched_text:
                    msg = "载荷向量为零（RHS only consists of 0.0），载荷未正确传递到结构"
                    suggestion = (
                        "检查以下可能原因：\n"
                        "1) *COUPLING 与 *DISTRIBUTING 联用时，载荷必须使用 *DLOAD 而非 *CLOAD\n"
                        "2) 检查 *COUPLING 的 REF NODE 是否正确设置\n"
                        "3) 检查耦合约束的 DOF 是否与载荷方向一致\n"
                        "4) 如果使用 DISTRIBUTING 耦合，改用 *DLOAD 在表面施加分布载荷"
                    )
                else:
                    msg = "集中载荷数量为零，载荷未正确定义"
                    suggestion = "检查 *CLOAD 或 *DLOAD 是否正确施加"
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="load_transfer",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_boundary_issues(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查边界条件问题：欠约束/过约束导致的刚体运动或奇异性。

    扫描 .stderr 文件，匹配以下模式：
    - "zero pivot"：零主元，通常是边界条件不完整
    - "singular matrix"：矩阵奇异，欠约束或过约束
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in BOUNDARY_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "zero pivot" in matched_text:
                    msg = "检测到零主元（zero pivot），可能是边界条件不完整"
                    suggestion = (
                        "检查以下可能原因：\n"
                        "1) 结构是否被完全约束（尤其旋转自由度）\n"
                        "2) 壳单元是否有足够的边界约束\n"
                        "3) 接触面是否正确定义\n"
                        "4) 节点编号是否连续"
                    )
                elif "singular matrix" in matched_text:
                    msg = "矩阵奇异，结构存在欠约束或过约束"
                    suggestion = (
                        "检查边界条件：\n"
                        "1) 确保所有位移分量都被约束\n"
                        "2) 检查是否存在冲突的边界条件\n"
                        "3) 壳/梁结构需要面外约束"
                    )
                else:
                    msg = "边界条件可能存在问题"
                    suggestion = "检查边界条件是否完整且无冲突"
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="boundary_condition",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_contact_issues(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查接触问题：接触定义错误、接触未找到等。

    扫描 .stderr 文件，匹配以下模式（增强自 calculix_patterns.txt）：
    - "contact not found"：接触面未找到
    - "overclosure"：过盈量过大
    - "contact stress negative"：接触应力为负
    - "slave/master surface"：主从面问题
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in CONTACT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "contact" in matched_text and "not" in matched_text and "found" in matched_text:
                    msg = "接触面未找到，接触定义可能错误"
                    suggestion = (
                        "检查以下可能原因：\n"
                        "1) 主从面是否正确设置\n"
                        "2) 接触面之间是否有初始间隙\n"
                        "3) 接触面节点是否在同一位置\n"
                        "4) 接触面法向方向是否正确"
                    )
                elif "overclosure" in matched_text:
                    msg = "接触过盈量过大"
                    suggestion = "检查初始几何位置，确保接触面之间没有过大的过盈量"
                elif "contact stress" in matched_text and "negative" in matched_text:
                    msg = "接触应力为负，可能存在穿透问题"
                    suggestion = "检查接触刚度设置和初始间隙"
                elif "slave surface" in matched_text or "master surface" in matched_text:
                    msg = "接触主从面定义存在问题"
                    suggestion = "检查 *CONTACT PAIR 中 SLAVE 和 MASTER 面的设置是否正确"
                elif "slave node" in matched_text:
                    msg = "接触从节点定义存在问题"
                    suggestion = "检查接触从节点的选取是否正确"
                elif "no tied" in matched_text or "tied mpc" in matched_text:
                    msg = "接触绑定/粘接问题"
                    suggestion = "检查 *TIE 命令的绑定面设置"
                else:
                    msg = "接触定义可能存在问题"
                    suggestion = "检查 *CONTACT PAIR 的主从面设置和 *SURFACE INTERACTION 参数"
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="contact",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_file_io_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查文件 I/O 错误（来自 CalculiX 源码 528 模式）。

    扫描 .stderr 文件，匹配以下模式：
    - "could not open file"：文件打开失败
    - "file name is lacking"：文件名缺失
    - "file name too long"：文件名过长
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in FILE_IO_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "could not open file" in matched_text:
                    msg = "文件打开失败"
                    suggestion = "检查 INP 文件路径是否正确，确保文件存在且有读取权限"
                elif "could not open" in matched_text:
                    msg = "文件打开失败"
                    suggestion = "检查文件名和路径是否正确"
                elif "file name is lacking" in matched_text:
                    msg = "文件名缺失"
                    suggestion = "检查 INP 文件中是否缺少输入文件名称"
                elif "file name too long" in matched_text or "input file name is too long" in matched_text:
                    msg = "文件名过长"
                    suggestion = "缩短输入文件的路径或文件名，CalculiX 对文件名长度有限制"
                elif "could not delete" in matched_text:
                    msg = "文件删除失败"
                    suggestion = "检查文件是否被其他程序占用，或是否有写入权限"
                elif "syntax error" in matched_text:
                    msg = "输入文件语法错误"
                    suggestion = "检查 INP 文件格式是否正确，确保卡片语法符合 CalculiX 规范"
                else:
                    msg = "文件 I/O 错误"
                    suggestion = "检查输入输出文件路径和权限"
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="file_io",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_user_element_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查用户单元/材料错误（来自 CalculiX 源码）。

    扫描 .stderr 文件，匹配以下模式：
    - "user element"：用户单元问题
    - "umat"：用户材料子程序问题
    - "user subroutine"：用户子程序问题
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in USER_ELEMENT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "no user material" in matched_text or "umat" in matched_text and "no" in matched_text:
                    msg = "用户材料子程序（UMAT）未找到"
                    suggestion = "确保 *USER MATERIAL 子程序已正确编译并链接，或使用标准材料模型"
                elif "user element" in matched_text:
                    msg = "用户单元（UELS）存在问题"
                    suggestion = "检查用户单元子程序是否正确实现和链接"
                elif "umat" in matched_text:
                    msg = "用户材料子程序（UMAT）存在问题"
                    suggestion = "检查 UMAT 子程序的输入参数和材料参数是否正确"
                else:
                    msg = "用户子程序存在问题"
                    suggestion = "检查用户自定义子程序是否正确编译和链接"
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="user_element",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_mpc_limits(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查 MPC/约束数量超限错误（来自 CalculiX 源码）。

    扫描 .stderr 文件，匹配以下模式：
    - "increase nmpc_"：MPC 数量超限
    - "increase nboun_"：边界条件数量超限
    - "increase nk_"：节点数量超限
    - "increase memmpc_"：MPC 内存超限
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in MPC_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "nmpc" in matched_text:
                    msg = "MPC（多点约束）数量超限"
                    suggestion = "减少模型中的 MPC 数量，或在 *MPCACABLE 参数中增加限制值"
                elif "nboun" in matched_text:
                    msg = "边界条件数量超限"
                    suggestion = "简化边界条件定义，减少边界条件数量"
                elif "nk" in matched_text:
                    msg = "节点数量超限"
                    suggestion = "检查网格节点编号是否合理，确保节点数量在允许范围内"
                elif "memmpc" in matched_text:
                    msg = "MPC 内存分配超限"
                    suggestion = "减少复杂 MPC 约束，或增加 *MPCABLE 的 MEMMPCC 参数"
                elif "nbody" in matched_text:
                    msg = "体积载荷数量超限"
                    suggestion = "减少 *DLOAD 定义的体积载荷数量"
                elif "nforc" in matched_text:
                    msg = "集中力数量超限"
                    suggestion = "减少 *CLOAD 定义的集中力数量"
                elif "nload" in matched_text:
                    msg = "载荷数量超限"
                    suggestion = "减少载荷定义数量，或合并载荷"
                elif "norien" in matched_text:
                    msg = "方向定义数量超限"
                    suggestion = "减少 *ORIENTATION 定义数量"
                elif "namtot" in matched_text:
                    msg = "总节点/单元属性数量超限"
                    suggestion = "简化模型，减少节点集和单元集数量"
                elif "nprint" in matched_text:
                    msg = "输出请求数量超限"
                    suggestion = "减少 *NODE PRINT 或 *EL PRINT 的输出变量数量"
                elif "dimension" in matched_text:
                    msg = "模型维度或网格尺寸超限"
                    suggestion = "检查网格尺寸是否合理，减小模型规模"
                else:
                    msg = "内存或数量超限"
                    suggestion = "简化模型或增加内存限制参数"
                issues.append(DiagnosticIssue(
                    severity="error",
                    category="limit_exceeded",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_dynamics_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查动力学/模态分析错误（来自 CalculiX 源码）。

    扫描 .stderr 文件，匹配以下模式：
    - "eigenvalue"：特征值问题
    - "frequencies"：频率提取问题
    - "cyclic symmetric"：循环对称问题
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in DYNAMICS_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "eigenvalue" in matched_text:
                    msg = "特征值求解失败"
                    suggestion = "检查模态分析参数，确保结构有足够的约束"
                elif "less than 1 eigenvalue" in matched_text:
                    msg = "特征值数量不足"
                    suggestion = "检查是否所有频率都为零（刚体模态），确保边界条件正确"
                elif "cyclic symmetric" in matched_text:
                    msg = "循环对称分析存在问题"
                    suggestion = "检查循环对称边界条件是否正确设置"
                elif "alpha is greater" in matched_text or "alpha is smaller" in matched_text:
                    msg = "动力学时间积分参数 alpha 不合理"
                    suggestion = "检查 *DYNAMIC 步骤的 alpha 参数（推荐值：-0.05 到 -0.3）"
                else:
                    msg = "动力学/模态分析存在问题"
                    suggestion = "检查动力学分析参数设置"
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="dynamics",
                    message=msg,
                    location=stderr_file.name,
                    suggestion=suggestion,
                ))
                break

    return issues


def _check_inp_file_quality(
    inp_file: Optional[Path],
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    直接扫描 INP 文件，检测被注释的关键卡片和常见错误。

    检测以下问题：
    - 被注释的 *SURFACE BEHAVIOR（接触行为缺失）
    - 被注释的 *ELASTIC（弹性常数缺失）
    - 被注释的 *MATERIAL（材料定义缺失）
    - 缺少 *SOLID SECTION 的材料关联
    - 缺少 *BOUNDARY 边界条件
    - 缺少 *STEP 分析步
    - 载荷施加位置错误（载荷在 *STEP 之前）
    """
    issues: list[DiagnosticIssue] = []

    if not inp_file or not inp_file.exists():
        return issues

    lines = _get_inp_lines(inp_file, ctx=ctx)
    if not lines:
        return issues

    # 收集所有关键字（包含注释行）
    all_keywords: set[str] = set()
    active_keywords: set[str] = set()
    commented_keywords: set[str] = set()

    # 关键字行号（用于定位）
    keyword_lines: dict[str, list[int]] = {}

    i = 0
    while i < len(lines):
        raw_line = lines[i].strip()

        # 跳过空行（块注释行 ** 要继续处理，用于标记被注释的关键字）
        if not raw_line:
            i += 1
            continue

        # 行内注释：取 # 前的部分
        line = raw_line.split("#")[0].strip()

        # 判断是否是块注释（** 开头）
        is_block_comment = raw_line.startswith("**")

        # 匹配关键字行（*开头），提取星号后、逗号前的完整关键字
        # 支持多单词关键字如 SURFACE BEHAVIOR、MATERIAL DEFORMATION 等
        # 对于块注释行（**），先去除 ** 前缀再匹配
        match_line = line
        if is_block_comment:
            # **KEYWORD 或 ** KEYWORD 形式，统一去除 ** 前缀
            match_line = re.sub(r"^\*\*\s*", "*", line, count=1)

        keyword_match = re.match(r"^\*([A-Za-z]+(?:[\s][A-Za-z]+)*)", match_line, re.IGNORECASE)
        if keyword_match:
            kw = keyword_match.group(1).upper()
            all_keywords.add(kw)
            if kw not in keyword_lines:
                keyword_lines[kw] = []
            keyword_lines[kw].append(i + 1)  # 行号从1开始

            # ** 开头是块注释，标记为被注释
            if is_block_comment:
                commented_keywords.add(kw)
            else:
                # 有效关键字（未被注释）
                active_keywords.add(kw)

        i += 1

    # ===== 检查1：被注释的关键材料卡片 =====
    critical_cards = {
        "ELASTIC": ("材料缺少弹性常数（*ELASTIC）", "在 *MATERIAL 中添加 *ELASTIC,TYPE=ISOTROPIC 定义弹性模量和泊松比"),
        "SURFACE BEHAVIOR": ("接触行为可能缺失（*SURFACE BEHAVIOR 被注释）", "检查接触面定义，确保 *SURFACE BEHAVIOR 参数正确设置（pressure= 惩罚刚度）"),
        "DENSITY": ("材料缺少密度定义（*DENSITY 被注释）", "动力学分析需要密度定义，在 *MATERIAL 中添加 *DENSITY"),
    }

    for kw, (msg, suggestion) in critical_cards.items():
        if kw in commented_keywords:
            line_nums = keyword_lines.get(kw, ["?"])
            issues.append(DiagnosticIssue(
                severity="warning",
                category="material",
                message=msg,
                location=f"{inp_file.name} 行 {line_nums[0]}",
                suggestion=suggestion,
            ))

    # ===== 检查2：缺少 *SOLID SECTION（材料未关联到单元） =====
    if "ELASTIC" in active_keywords and "SOLID SECTION" not in active_keywords:
        issues.append(DiagnosticIssue(
            severity="warning",
            category="material",
            message="检测到材料定义但缺少 *SOLID SECTION，材料可能未关联到单元",
            location=inp_file.name,
            suggestion="在 *SOLID SECTION 中指定 ELNAME=材料名称，确保材料属性关联到单元集",
        ))

    # ===== 检查3：缺少边界条件 =====
    if "BOUNDARY" not in active_keywords and "BOUNDARY" not in commented_keywords:
        issues.append(DiagnosticIssue(
            severity="error",
            category="boundary_condition",
            message="INP 文件中未找到 *BOUNDARY 定义",
            location=inp_file.name,
            suggestion="结构必须有边界条件才能求解。添加 *BOUNDARY 约束位移分量（固定端全约束或对称边界）",
        ))

    # ===== 检查4：缺少分析步 =====
    if "STEP" not in active_keywords and "STEP" not in commented_keywords:
        issues.append(DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="INP 文件中未找到 *STEP 定义",
            location=inp_file.name,
            suggestion="必须定义至少一个 *STEP 分析步。添加 *STATIC（静力分析）或 *FREQUENCY（模态分析）等",
        ))

    # ===== 检查5：载荷在 STEP 之前（常见错误） =====
    step_line = None
    load_keywords = {"CLOAD", "DLOAD", "DFLUX", "CFLUX", "BOUNDARY"}
    for kw, lines_list in keyword_lines.items():
        if kw in load_keywords and not any(kw in c for c in commented_keywords):
            if step_line is None:
                # 找第一个 *STEP 的位置
                step_lines = keyword_lines.get("STEP", [float("inf")])
                first_step = step_lines[0] if step_lines else float("inf")
                if lines_list[0] < first_step:
                    issues.append(DiagnosticIssue(
                        severity="warning",
                        category="input_syntax",
                        message=f"{kw} 定义在 *STEP 之前，可能无效",
                        location=f"{inp_file.name} 行 {lines_list[0]}",
                        suggestion="载荷和边界条件通常应定义在 *STEP 块内部（或 *STEP 之后）",
                    ))
                    break

    return issues


def _check_element_quality(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查单元质量：Jacobian 负值、Hourglass 等问题。

    扫描 .sta / .dat / .cvg 文件，使用正则匹配以下模式：
    - NEGATIVE JACOBIAN：单元翻转或畸形
    - HOURGLASSING：减缩积分单元的零能模式
    - HOURGLIM：沙漏控制参数
    - *ERROR.*element：元素相关错误
    """
    issues: list[DiagnosticIssue] = []

    for file_path, text in _iter_result_texts(results_dir, ("*.sta", "*.dat", "*.cvg"), ctx=ctx):
        file_label = file_path.name

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

    return issues


def _check_frd_quality(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """检查网格质量（通过 FrdData 统计推断）。"""
    issues: list[DiagnosticIssue] = []

    try:
        summary = _get_frd_summary(results_dir, ctx=ctx)
        if summary is None:
            return issues

        if summary.node_count > 0 and summary.element_count > 0:
            ratio = summary.node_count / summary.element_count
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

        if summary.disp_count > 0 and summary.disp_sum > 0:
            mean_disp = summary.disp_sum / summary.disp_count
            max_disp = summary.max_displacement
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


def _check_stress_gradient(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """检查应力集中：应力梯度突变 > 50x。"""
    issues: list[DiagnosticIssue] = []

    try:
        summary = _get_frd_summary(results_dir, ctx=ctx)
        if summary is None:
            return issues

        if len(summary.stress_values) > 10:
            sorted_vals = sorted(summary.stress_values)
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


def _check_displacement_range(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """检查位移范围：最大位移 > 模型尺寸 10%。"""
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues

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


def _check_large_strain(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
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
    inp_text = _get_inp_text(inp_file, ctx=ctx)
    if inp_text:
        # 支持 *STEP, NLGEOM 和 *STEP,NLGEOM 两种格式
        has_nlgeom = bool(re.search(r"\*STEP\s*,\s*NLGEOM", inp_text, re.IGNORECASE))

    try:
        summary = _get_frd_summary(results_dir, ctx=ctx)
        if summary is None:
            return issues
        if summary.max_strain <= 0:
            return issues

        # 3. 根据阈值判断
        if summary.max_strain > 0.1:
            if has_nlgeom:
                issues.append(DiagnosticIssue(
                    severity="info",
                    category="large_strain",
                    message=f"检测到大变形（{summary.max_strain_component}={summary.max_strain:.4f}），分析已启用几何非线性（NLGEOM），应变输出为拉格朗日定义",
                    location=f"节点 {summary.max_strain_node}",
                    suggestion="结果为格林/拉格朗日应变，非线性应变值本身是合理的",
                ))
            else:
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="large_strain",
                    message=f"检测到大变形（{summary.max_strain_component}={summary.max_strain:.4f}），但 inp 文件未启用几何非线性（NLGEOM）",
                    location=f"节点 {summary.max_strain_node}",
                    suggestion="在 *STEP 行添加 NLGEOM 参数以启用几何非线性分析：*STEP, NLGEOM",
                ))

    except Exception:
        pass

    return issues


# ------------------------------------------------------------------ #
# 材料屈服强度提取（单位：Pa）
# ------------------------------------------------------------------ #

def _extract_yield_strength(
    inp_file: Optional[Path],
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[float]:
    """
    从 inp 文件提取材料屈服强度。

    支持的材料定义：
    - *DEFORMATION PLASTICITY：E, nu, sigma_y, n, angle → 取第三参数 sigma_y（单位 MPa）
    - *PLASTIC：需解析多行，默认取第一个屈服点（单位 MPa）
    - *ELASTIC：无法获取屈服强度，返回 None

    Returns:
        屈服强度（Pa），无法提取时返回 None
    """
    target = inp_file or (ctx.inp_file if ctx else None)
    if not target or not target.exists():
        return None

    if ctx is not None and target in ctx.yield_strength_cache:
        return ctx.yield_strength_cache[target]

    result: Optional[float] = None
    lines = _get_inp_lines(target, ctx=ctx)
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # DEFORMATION PLASTICITY: E, nu, sigma_y, n, angle
        if line.upper().startswith("*DEFORMATION PLASTICITY"):
            if i + 1 < len(lines):
                parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', lines[i + 1])
                if len(parts) >= 3:
                    # sigma_y 单位是 MPa，转换为 Pa
                    result = float(parts[2]) * 1e6
                    break
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
                    result = float(parts[0]) * 1e6
                    break
                i += 1
            if result is not None:
                break
            continue

        # *ELASTIC 只有 E 和 nu，无法获取屈服强度
        if line.upper().startswith("*ELASTIC"):
            break

        i += 1

    if ctx is not None:
        ctx.yield_strength_cache[target] = result
    return result


# ------------------------------------------------------------------ #
# 刚体模式 & 材料屈服检测
# ------------------------------------------------------------------ #

def _check_rigid_body_mode(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查刚体模式：位移非零但应力几乎为零。

    判断逻辑：
    - 最大位移 > 模型尺寸的 1% 且 最大 von Mises 应力 < 屈服强度的 0.01
    - 注意：刚体运动的特征是"整体"应力很低，用最大应力而不是平均应力更准确
    - 避免粗网格下应力插值误差导致的误报
    """
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues

        max_disp = stats["max_displacement"]
        model_size = max(*stats["model_bounds"], 1e-10)

        # 位移太小（< 模型尺寸 0.5%）不算刚体模式
        if max_disp < model_size * 0.005:
            return issues

        # 获取最大应力
        max_stress = stats["max_stress"]
        if max_stress <= 0:
            return issues

        # 从 inp 获取屈服强度
        yield_strength = _extract_yield_strength(inp_file, ctx=ctx)
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
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    检查材料是否屈服：最大应力是否超过屈服强度。

    判断逻辑：
    - 最大 von Mises 应力 > 屈服强度 → warning: 材料屈服
    - 最大 von Mises 应力 > 屈服强度 * 1.5 → error: 严重屈服
    """
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues
        max_stress = stats["max_stress"]

        if max_stress <= 0:
            return issues

        yield_strength = _extract_yield_strength(inp_file, ctx=ctx)
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
    ctx: Optional[DiagnosisContext] = None,
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

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues
        max_stress = stats["max_stress"]

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
        inp_lines = _get_inp_lines(inp_file, ctx=ctx)
        if inp_lines:
            # 提取 E 值（单位 MPa）
            E_value = None
            for i, line in enumerate(inp_lines):
                if line.upper().startswith("*ELASTIC"):
                    if i + 1 < len(inp_lines):
                        parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', inp_lines[i + 1])
                        if parts:
                            E_value = float(parts[0])
                            break

            if E_value and E_value > 1e8 and max_stress < 1e6:
                issues.append(DiagnosticIssue(
                    severity="warning",
                    category="unit_consistency",
                    message=f"材料弹性模量 E={E_value:.2e} MPa 与应力结果不匹配，可能单位不一致",
                    suggestion="如果 E 用 Pa 而非 MPa，会导致应力结果偏小 1e6 倍。请确认 E 单位是 MPa，尺寸单位是 mm。",
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
    ctx: Optional[DiagnosisContext] = None,
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

    if not inp_file or not inp_file.exists():
        return {"issues": issues, "similar_cases": similar_cases}

    db = _load_reference_case_db()
    if db is None:
        return {"issues": issues, "similar_cases": similar_cases}

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
        issues.extend(_compare_with_reference(results_dir, similar, ctx=ctx))

    except Exception as e:
        log.warning("参考案例对比失败: %s", e)

    return {"issues": issues, "similar_cases": similar_cases}


def _compare_with_reference(
    results_dir: Path,
    similar_cases: list[tuple[CaseMetadata, float]],
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """将用户结果与相似案例的预期范围对比。"""
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues
        user_disp_max = stats["max_displacement"]
        user_stress_max = stats["max_stress"]

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


def _get_max_displacement(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[float]:
    """从 FRD 文件提取用户最大位移，用于参考案例对比。"""
    try:
        frd_data = _get_frd_data(results_dir, ctx=ctx)
        if frd_data is None:
            return None
        disp_result = frd_data.get_result("DISP")

        if not disp_result or not disp_result.values:
            return None

        max_disp = 0.0
        for vals in disp_result.values.values():
            if vals is not None and len(vals) > 0:
                magnitude = sum(float(v) ** 2 for v in vals) ** 0.5
                max_disp = max(max_disp, magnitude)

        return max_disp if max_disp > 0 else None
    except Exception:
        return None


# ------------------------------------------------------------------ #
# Level 3: AI 诊断
# ------------------------------------------------------------------ #

def _run_ai_diagnosis(
    client: LLMClient,
    level1_issues: list[DiagnosticIssue],
    level2_issues: list[DiagnosticIssue],
    similar_cases: list[dict],
    results_dir: Path,
    inp_file: Optional[Path] = None,
    stream: bool = True,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[str]:
    """运行 AI 深度诊断。"""
    try:
        all_issues = level1_issues + level2_issues

        # 只保留当前 prompt 会实际使用的诊断证据，避免额外解析 .frd/.inp。
        stderr_snippets = _get_stderr_snippets(results_dir, all_issues, ctx=ctx)

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

        physical_data = _get_physical_data(results_dir, inp_file, ctx=ctx)
        stderr_summary = _get_stderr_summary(results_dir, ctx=ctx)
        prompt_text = make_diagnose_prompt_v2(
            issue_dicts,
            stderr_snippets,
            physical_data=physical_data,
            stderr_summary=stderr_summary,
            similar_cases=similar_cases,
        )

        if stream:
            handler = StreamHandler()
            tokens = client.complete_streaming(prompt_text)
            return validate_ai_output(handler.stream_tokens(tokens))
        else:
            return validate_ai_output(client.complete(prompt_text))

    except Exception as e:
        log.warning("AI 诊断失败: %s", e)
        return None


def strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks from AI output."""
    return re.sub(r"```[\s\S]*?```", "", text)


def validate_ai_output(text: str) -> str:
    """Remove invalid CalculiX syntax from AI output and add a warning."""
    if not text:
        return text

    if not any(re.search(pattern, text, re.IGNORECASE) for pattern in INVALID_SYNTAX_PATTERNS):
        return text

    sanitized = strip_code_blocks(text)
    sanitized_lines: list[str] = []
    for line in sanitized.splitlines():
        if any(re.search(pattern, line, re.IGNORECASE) for pattern in INVALID_SYNTAX_PATTERNS):
            continue
        sanitized_lines.append(line)

    sanitized = "\n".join(sanitized_lines).strip()
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    if sanitized:
        return f"{sanitized}\n\n{AI_OUTPUT_SYNTAX_WARNING}"
    return AI_OUTPUT_SYNTAX_WARNING


def _get_physical_data(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> str:
    """从 .frd 文件提取关键物理数据用于 AI 分析。"""
    try:
        frd_data = _get_frd_data(results_dir, ctx=ctx)
        if frd_data is None:
            return ""
        lines = []

        # 节点/单元数
        lines.append(f"节点数: {frd_data.node_count}, 单元数: {frd_data.element_count}")

        # 材料弹性模量 E（从 INP 文件提取）
        inp_lines = _get_inp_lines(inp_file, ctx=ctx)
        for i, line in enumerate(inp_lines):
            if line.upper().startswith("*ELASTIC"):
                next_line = inp_lines[i + 1] if i + 1 < len(inp_lines) else ""
                parts = re.findall(r'[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?', next_line)
                if parts:
                    E_val = float(parts[0])
                    lines.append(f"材料弹性模量 E: {E_val:.6e} MPa")
                    break

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


def _get_stderr_summary(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> str:
    """
    从 .sta 文件提取结构化收敛指标，不发送原始数据给 AI。

    返回格式：
    - 最大迭代次数
    - 最终残差
    - 收敛状态
    - 时间/增量信息
    """
    summaries: list[str] = []

    for sta_file, text in _iter_result_texts(results_dir, ("*.sta",), ctx=ctx):
        try:
            lines = text.strip().splitlines()

            # 提取关键收敛指标
            max_iterations = 0
            final_residual = None
            final_force_ratio = None
            final_increment = None
            converged = None

            for line in lines[-100:]:  # 只看最后100行
                # 检测收敛状态
                if "SUMMARY OF CONVERGENCY INFORMATION" in line or "CONVERGENCE" in line.upper():
                    converged = "NOT CONVERGED" if "NOT" in line.upper() or "FAILED" in line.upper() else "CONVERGED"
                # 检测最大迭代次数（step=XXX, inc=XXX, att=XXX, iter=XXX）
                iter_match = re.search(r'iter[=\s]+(\d+)', line, re.IGNORECASE)
                if iter_match:
                    max_iterations = max(max_iterations, int(iter_match.group(1)))
                # 检测残差（resid.=XXX）
                resid_match = re.search(r'resid[.=\s]+(-?[\d.]+)', line, re.IGNORECASE)
                if resid_match:
                    final_residual = float(resid_match.group(1))
                # 检测力比（force%=XXX）
                force_match = re.search(r'force%?\s*=\s*([\d.]+)', line, re.IGNORECASE)
                if force_match:
                    final_force_ratio = float(force_match.group(1))
                # 检测增量（increment size = XXX）
                inc_match = re.search(r'increment\s+size\s*=\s*([\d.eE+-]+)', line, re.IGNORECASE)
                if inc_match:
                    try:
                        final_increment = float(inc_match.group(1))
                    except ValueError:
                        pass

            # 构建结构化摘要（不发原始行）
            if max_iterations > 0 or final_residual is not None:
                parts = [f"文件名: {sta_file.name}"]
                if converged:
                    parts.append(f"收敛状态: {converged}")
                if max_iterations > 0:
                    parts.append(f"最大迭代次数: {max_iterations}")
                if final_residual is not None:
                    parts.append(f"最终残差: {final_residual:.4f}")
                if final_force_ratio is not None:
                    parts.append(f"最终力比: {final_force_ratio:.2f}%")
                if final_increment is not None and final_increment > 0:
                    parts.append(f"最终增量步: {final_increment:.2e}")

                summaries.append(" | ".join(parts))

        except OSError:
            pass

    return "\n".join(summaries) if summaries else "（无收敛数据）"


def _get_stderr_snippets(
    results_dir: Path,
    issues: list,
    ctx: Optional[DiagnosisContext] = None,
) -> str:
    """
    提取与规则检测问题直接相关的 stderr 片段。

    这是规则的直接证据，不是原始数据。
    """
    if not issues:
        return ""

    snippets: list[str] = []
    stderr_file = None

    # 收集所有 stderr 文件
    stderr_files = _glob_cached(results_dir, "*.stderr", ctx=ctx)
    if stderr_files:
        stderr_file = stderr_files[0]

    if stderr_file is None:
        return ""

    try:
        text = _read_text_cached(stderr_file, ctx=ctx)
        lines = text.splitlines()

        # 为每个 issue 找到对应的 stderr 片段
        for issue in issues:
            message = issue.message.lower() if issue.message else ""

            # 关键词匹配
            keywords = []
            if "elastic" in message:
                keywords.extend(["elastic", "elastic constants"])
            if "density" in message:
                keywords.append("density")
            if "converge" in message or "收敛" in message:
                keywords.extend(["converge", "not converged", "divergence"])
            if "jacobian" in message:
                keywords.append("jacobian")
            if "hourglass" in message:
                keywords.append("hourglassing")

            # 找到匹配的行的上下文（前后各2行）
            for i, line in enumerate(lines):
                line_lower = line.lower()
                for kw in keywords:
                    if kw in line_lower:
                        # 提取片段（前后各2行）
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        snippet_lines = lines[start:end]

                        # 标记匹配行
                        for j in range(len(snippet_lines)):
                            if i - start == j:
                                snippet_lines[j] = f">>> {snippet_lines[j]}"
                            else:
                                snippet_lines[j] = f"    {snippet_lines[j]}"

                        snippets.append(f"--- 匹配片段 ({stderr_file.name} 行 {i+1}) ---")
                        snippets.extend(snippet_lines)
                        snippets.append("")
                        break  # 只取第一个匹配

    except OSError:
        pass

    return "\n".join(snippets) if snippets else "（无相关片段）"
