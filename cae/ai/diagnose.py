# diagnose.py
"""
娑撳鐪板▎陇鐦栭弬顓犻兇缂?

Level 1: 鐟欏嫬鍨Λ鈧ù瀣剁礄閺冪姵娼禒鑸靛⒔鐞涘矉绱?
  - 閺€鑸垫殐閹嶇窗stderr 閸?*ERROR 閹?returncode != 0
  - 閸楁洖鍘撶拹銊╁櫤閿涙acobian 鐠愮喎鈧鈧笭ourglass閵嗕焦鐭欏蹇斈佸?
  - 缂冩垶鐗哥拹銊╁櫤閿涙俺濡悙?閸楁洖鍘撳В鏂剧伐瀵倸鐖?
  - 鎼存柨濮忛梿鍡曡厬閿涙艾绨查崝娑欘潽鎼达妇鐛婇崣?> 50x
  - 娴ｅ秶些閼煎啫娲块敍姘付婢堆傜秴缁?> 濡€崇€风亸鍝勵嚟 10%
  - 婢堆冨綁瑜邦澁绱版径褍绨查崣妯哄瀻闁?> 0.1 娑撴梹妫?NLGEOM 閳?瀵ら缚顔呴崥顖滄暏閸戠姳缍嶉棃鐐靛殠閹?
  - 閸掓矮缍嬪Ο鈥崇础閿涙矮缍呯粔濠氭姜闂嗘湹绲炬惔鏂垮閹恒儴绻庨梿?閳?濞嗙姷瀹抽弶?
  - 閺夋劖鏋＄仦鍫熸箛閿涙碍娓舵径褍绨查崝娑滅Т鏉╁洤鐪婚張宥呭繁鎼?
  - 閸楁洑缍呮稉鈧懛瀛樷偓褝绱版惔鏂垮闁插繒楠囧鍌氱埗閿? 1 Pa 閹?> 1 TPa閿涘本鍨?E/鎼存柨濮忛崡鏇氱秴娑撳秴灏柊宥忕礆

Level 2: 閸欏倽鈧啯顢嶆笟瀣嚠濮ｆ棑绱欓弮鐘虫蒋娴犺埖澧界悰宀嬬礆
  - 娴?638 娑擃亜鐣奸弬瑙勭ゴ鐠囨洟娉﹂幍鍓ф祲娴煎吋顢嶆笟?
  - 鐎佃鐦悽銊﹀煕缂佹挻鐏夐惃鍕秴缁?鎼存柨濮忛弰顖氭儊閸︺劌鎮撶猾缁橆攳娓氬鎮庨悶鍡氬瘱閸ユ潙鍞?

Level 3: AI 濞ｅ崬瀹抽崚鍡樼€介敍鍫濆讲闁绱濋棁鈧€瑰顥?ai 閹绘帊娆㈤敍?
  - 缂佹挸鎮庣憴鍕灟濡偓濞?+ 閸欏倽鈧啯顢嶆笟瀣嚠濮ｆ梻绮ㄩ弸?
  - 缂佹瑥鍤崗铚傜秼閻ㄥ嫪鎱ㄦ径宥呯紦鐠?
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .llm_client import LLMClient
from .prompts import make_diagnose_prompt_v2
from .solver_output import (
    collect_solver_text_sources,
    extract_solver_convergence_metrics,
    summarize_solver_run,
)
from .stream_handler import StreamHandler
from .explain import _find_frd
from .diagnosis_history import DiagnosisHistoryStore, IssueObservation
from .fix_rules import get_safe_autofix_rule
from .reference_cases import CaseMetadata, CaseDatabase, parse_inp_metadata
from cae.viewer.frd_parser import FrdData, parse_frd

log = logging.getLogger(__name__)

DIAGNOSE_RESULT_NAMES = {"DISP", "STRESS", "TOSTRAIN"}
_FRD_PREFIX_WIDTH = 13
_FRD_VALUE_WIDTH = 12

# 閸欏倽鈧啯顢嶆笟瀣氨鐠侯垰绶?
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
    "solver_runtime": "Solver Runtime Issue",
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
    "solver_runtime": 2,
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
AI_MAX_ISSUES = 12
AI_MAX_SNIPPETS = 12
AI_SNIPPET_CONTEXT_RADIUS = 2
AI_MAX_ISSUES_PER_CATEGORY = 3
ISSUE_TOKEN_STOPWORDS = {
    "with",
    "from",
    "that",
    "this",
    "were",
    "have",
    "has",
    "been",
    "into",
    "while",
    "where",
    "when",
    "your",
    "there",
    "cannot",
    "could",
    "would",
    "should",
    "error",
    "warning",
    "issue",
    "detected",
    "possible",
    "check",
    "model",
    "results",
    "likely",
}
ISSUE_KEYWORDS_BY_CATEGORY = {
    "convergence": ["not converged", "converge", "divergence", "increment size"],
    "material": ["elastic", "density", "material", "conductivity", "specific heat"],
    "input_syntax": ["unknown keyword", "cannot be interpreted", "syntax error"],
    "element_quality": ["jacobian", "hourglass", "distorted element", "aspect ratio"],
    "mesh_quality": ["jacobian", "distorted element", "skewness", "aspect ratio"],
    "load_transfer": ["rhs only consists of 0.0", "concentrated loads"],
    "boundary_condition": ["zero pivot", "singular matrix", "underconstrained", "overconstrained"],
    "contact": ["contact", "slave surface", "master surface", "overclosure", "tied mpc"],
    "file_io": ["could not open file", "file name", "could not open"],
    "solver_runtime": ["fatal error", "segmentation fault", "mpi abort", "exit failure", "aborted"],
    "user_element": ["user element", "umat", "user subroutine"],
    "limit_exceeded": ["increase nmpc", "increase nboun", "increase nk", "increase the dimension"],
    "dynamics": ["eigenvalue", "modal dynamic", "cyclic symmetric"],
}
AI_OUTPUT_SYNTAX_WARNING = (
    "Warning: invalid AI-generated syntax snippets were removed. "
    "Please verify syntax against CalculiX documentation."
)


@dataclass
class DiagnosticIssue:
    """鐠囧﹥鏌囬梻顕€顣介弶锛勬窗閵?"""

    severity: str  # "error" | "warning" | "info"
    category: str  # "convergence" | "mesh_quality" | "stress_concentration" | "displacement" | "reference_comparison"
    message: str
    location: Optional[str] = None
    evidence_line: Optional[str] = None
    evidence_score: Optional[float] = None
    evidence_support_count: Optional[int] = None
    evidence_conflict: Optional[str] = None
    history_hits: Optional[int] = None
    history_avg_score: Optional[float] = None
    history_conflict_rate: Optional[float] = None
    history_similarity: Optional[float] = None
    history_similar_hits: Optional[int] = None
    history_similar_conflict_rate: Optional[float] = None
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
    """鐠囧﹥鏌囩紒鎾寸亯閵?"""

    success: bool
    level1_issues: list[DiagnosticIssue] = field(default_factory=list)  # 鐟欏嫬鍨Λ鈧ù?
    level2_issues: list[DiagnosticIssue] = field(default_factory=list)  # 閸欏倽鈧啯顢嶆笟瀣嚠濮?
    level3_diagnosis: Optional[str] = None  # AI 鐠囧﹥鏌?
    similar_cases: list[dict] = field(default_factory=list)  # 闁烩晠鏅查幎鈧俊妤€鐗呯欢?
    convergence_metrics: list[dict] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def issues(self) -> list[DiagnosticIssue]:
        """閹碘偓閺堝妫舵０妯兼畱閸氬牆鑻熼崚妤勩€冮妴?"""
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
    convergence_metrics: list[dict] = field(default_factory=list, repr=False)
    convergence_metrics_loaded: bool = field(default=False, repr=False)
    solver_text_sources: list[Path] = field(default_factory=list, repr=False)
    solver_text_sources_loaded: bool = field(default=False, repr=False)
    solver_run_summary: Optional[dict] = field(default=None, repr=False)
    solver_run_summary_loaded: bool = field(default=False, repr=False)
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
    return get_safe_autofix_rule(issue) is not None


def _clamp_evidence_score(score: float) -> float:
    return max(0.0, min(1.0, score))


EVIDENCE_CONFLICT_PENALTY = 0.30
EVIDENCE_GUARDRAILS_PATH = Path(__file__).parent / "data" / "evidence_guardrails.json"
HISTORY_BOOST_MIN_HITS = 2
HISTORY_BOOST_MIN_SCORE = 0.75
HISTORY_BOOST_MAX_CONFLICT_RATE = 0.20
HISTORY_PENALTY_MIN_HITS = 2
HISTORY_PENALTY_MIN_CONFLICT_RATE = 0.50
HISTORY_BOOST = 0.05
HISTORY_PENALTY = 0.08
HISTORY_SIMILARITY_MIN = 0.55
HISTORY_SIM_BOOST_MIN_HITS = 3
HISTORY_SIM_BOOST_MIN_SCORE = 0.75
HISTORY_SIM_BOOST_MAX_CONFLICT_RATE = 0.25
HISTORY_SIM_PENALTY_MIN_HITS = 3
HISTORY_SIM_PENALTY_MIN_CONFLICT_RATE = 0.55
HISTORY_SIM_BOOST = 0.03
HISTORY_SIM_PENALTY = 0.06
EVIDENCE_SOURCE_TRUST_BY_EXT: dict[str, float] = {
    ".stderr": 1.0,
    ".sta": 0.95,
    ".dat": 0.75,
    ".cvg": 0.70,
    ".csv": 0.90,
    ".log": 0.85,
    ".inp": 0.65,
}
DEFAULT_EVIDENCE_GUARDRAILS_BY_CATEGORY: dict[str, dict[str, float]] = {
    # Fallback for categories without explicit thresholds.
    # Keep conservative so high-confidence explicit errors still stay as errors.
    "default": {"min_support": 1, "min_score": 0.55, "min_trust": 0.65, "score_penalty": 0.08},
    "convergence": {"min_support": 2, "min_score": 0.72, "min_trust": 0.80, "score_penalty": 0.15},
    "boundary_condition": {
        "min_support": 2,
        "min_score": 0.70,
        "min_trust": 0.80,
        "score_penalty": 0.12,
    },
    "contact": {"min_support": 2, "min_score": 0.72, "min_trust": 0.80, "score_penalty": 0.12},
    "dynamics": {"min_support": 2, "min_score": 0.70, "min_trust": 0.80, "score_penalty": 0.12},
    "load_transfer": {
        "min_support": 2,
        "min_score": 0.68,
        "min_trust": 0.78,
        "score_penalty": 0.10,
    },
    "input_syntax": {"min_support": 1, "min_score": 0.45, "min_trust": 0.60, "score_penalty": 0.06},
    "material": {"min_support": 1, "min_score": 0.45, "min_trust": 0.60, "score_penalty": 0.06},
}


def _validate_guardrail_entry(entry: dict) -> Optional[dict[str, float]]:
    try:
        min_support = max(1, int(entry.get("min_support", 1)))
        min_score = _clamp_evidence_score(float(entry.get("min_score", 0.0)))
        min_trust = _clamp_evidence_score(float(entry.get("min_trust", 0.0)))
        score_penalty = _clamp_evidence_score(float(entry.get("score_penalty", 0.1)))
    except (TypeError, ValueError):
        return None

    return {
        "min_support": float(min_support),
        "min_score": float(min_score),
        "min_trust": float(min_trust),
        "score_penalty": float(score_penalty),
    }


def _infer_evidence_source_trust(issue: DiagnosticIssue) -> float:
    file_name: Optional[str] = None
    if issue.evidence_line and ":" in issue.evidence_line:
        file_name = issue.evidence_line.split(":", 1)[0].strip()
    elif issue.location and issue.location.strip():
        hinted_file, _ = _parse_issue_location_hint(issue.location)
        file_name = hinted_file

    if not file_name:
        return 0.60

    ext = Path(file_name).suffix.lower()
    return EVIDENCE_SOURCE_TRUST_BY_EXT.get(ext, 0.60)


@lru_cache(maxsize=16)
def _get_evidence_guardrails(config_path_override: str = "") -> dict[str, dict[str, float]]:
    merged = {
        category: dict(config)
        for category, config in DEFAULT_EVIDENCE_GUARDRAILS_BY_CATEGORY.items()
    }

    raw_path = config_path_override.strip()
    if not raw_path:
        raw_path = (os.getenv("CAE_EVIDENCE_GUARDRAILS_PATH") or "").strip()
    config_path = Path(raw_path) if raw_path else EVIDENCE_GUARDRAILS_PATH
    if not config_path.exists():
        return merged

    try:
        loaded = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Failed to load evidence guardrails config %s: %s", config_path, exc)
        return merged

    if not isinstance(loaded, dict):
        log.warning("Invalid evidence guardrails config format: %s", config_path)
        return merged

    for category, raw_entry in loaded.items():
        if not isinstance(category, str) or not isinstance(raw_entry, dict):
            continue
        validated = _validate_guardrail_entry(raw_entry)
        if validated is None:
            continue
        merged[category] = validated

    return merged


def _apply_evidence_conflict_penalty(
    score: float,
    issue: DiagnosticIssue,
) -> float:
    if issue.evidence_conflict and issue.evidence_conflict.strip():
        return _clamp_evidence_score(score - EVIDENCE_CONFLICT_PENALTY)
    return _clamp_evidence_score(score)


def _infer_evidence_score(issue: DiagnosticIssue) -> float:
    if issue.evidence_score is not None:
        return round(_clamp_evidence_score(float(issue.evidence_score)), 2)

    score = 0.2
    if issue.location and issue.location.strip():
        score += 0.15
        hinted_file, hinted_line = _parse_issue_location_hint(issue.location)
        if hinted_file:
            score += 0.05
        if hinted_line is not None:
            score += 0.1

    if issue.evidence_line and issue.evidence_line.strip():
        score += 0.45
        if re.search(r":[0-9]+\s*:", issue.evidence_line):
            score += 0.05

    support_count = issue.evidence_support_count
    if support_count is not None:
        if support_count >= 2:
            score += 0.10
        if support_count >= 3:
            score += 0.05
        if support_count <= 1 and issue.severity == "error":
            score -= 0.05

    source_trust = _infer_evidence_source_trust(issue)
    if source_trust >= 0.90:
        score += 0.08
    elif source_trust < 0.75:
        score -= 0.08
        if (support_count or 0) <= 1 and issue.severity == "error":
            score -= 0.05

    return round(_apply_evidence_conflict_penalty(score, issue), 2)


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

    current_has_evidence = bool((current.evidence_line or "").strip())
    candidate_has_evidence = bool((candidate.evidence_line or "").strip())
    if candidate_has_evidence != current_has_evidence:
        return candidate_has_evidence

    current_has_conflict = bool((current.evidence_conflict or "").strip())
    candidate_has_conflict = bool((candidate.evidence_conflict or "").strip())
    if candidate_has_conflict != current_has_conflict:
        return not candidate_has_conflict

    current_support = current.evidence_support_count or 0
    candidate_support = candidate.evidence_support_count or 0
    if candidate_support != current_support:
        return candidate_support > current_support

    current_evidence_score = _infer_evidence_score(current)
    candidate_evidence_score = _infer_evidence_score(candidate)
    if candidate_evidence_score != current_evidence_score:
        return candidate_evidence_score > current_evidence_score

    current_has_location = bool((current.location or "").strip())
    candidate_has_location = bool((candidate.location or "").strip())
    return candidate_has_location and not current_has_location


def _issue_confidence_band(issue: DiagnosticIssue) -> str:
    score = _infer_evidence_score(issue)
    trust = _infer_evidence_source_trust(issue)
    has_conflict = bool((issue.evidence_conflict or "").strip())

    if has_conflict or score < 0.55 or trust < 0.45:
        return "low"
    if score >= 0.80 and trust >= 0.70:
        return "high"
    return "medium"


def _issue_needs_review(issue: DiagnosticIssue) -> bool:
    return _issue_confidence_band(issue) == "low" or bool((issue.evidence_conflict or "").strip())


def _is_blocking_issue(issue: DiagnosticIssue) -> bool:
    return issue.severity == "error" and not _issue_needs_review(issue)


def _issue_triage_label(issue: DiagnosticIssue) -> str:
    if _infer_auto_fixable(issue) and not _issue_needs_review(issue):
        return "safe_auto_fix"
    if _is_blocking_issue(issue):
        return "blocking"
    if _issue_needs_review(issue):
        return "review"
    return "monitor"


def _calculate_risk_score(issues: list[DiagnosticIssue]) -> int:
    score = 0.0
    for issue in issues:
        severity_weight = {
            "error": 28.0,
            "warning": 10.0,
            "info": 3.0,
        }.get(issue.severity, 4.0)
        priority = issue.priority if issue.priority is not None else _infer_priority(issue)
        priority_bonus = max(0, 6 - priority) * 2.0
        confidence = _issue_confidence_band(issue)
        confidence_weight = {
            "high": 1.0,
            "medium": 0.78,
            "low": 0.45,
        }[confidence]
        score += (severity_weight + priority_bonus) * confidence_weight

    error_count = sum(1 for issue in issues if issue.severity == "error")
    if error_count >= 3:
        score += 8.0

    return min(100, int(round(score)))


def _build_execution_plan(issues: list[DiagnosticIssue], limit: int = 5) -> list[dict]:
    plan: list[dict] = []
    for idx, issue in enumerate(issues[:limit], 1):
        action = issue.action or f"Inspect {issue.category.replace('_', ' ')} evidence."
        plan.append(
            {
                "step": idx,
                "triage": _issue_triage_label(issue),
                "category": issue.category,
                "severity": issue.severity,
                "confidence": _issue_confidence_band(issue),
                "auto_fixable": _infer_auto_fixable(issue),
                "action": action,
                "evidence_line": issue.evidence_line,
            }
        )
    return plan


def normalize_issues(issues: list[DiagnosticIssue]) -> list[DiagnosticIssue]:
    deduped: dict[tuple[str, str], DiagnosticIssue] = {}
    for issue in issues:
        normalized = DiagnosticIssue(
            severity=issue.severity,
            category=issue.category,
            message=issue.message.strip(),
            location=issue.location.strip() if issue.location else None,
            evidence_line=issue.evidence_line.strip() if issue.evidence_line else None,
            evidence_score=_infer_evidence_score(issue),
            evidence_support_count=issue.evidence_support_count,
            evidence_conflict=issue.evidence_conflict.strip() if issue.evidence_conflict else None,
            history_hits=issue.history_hits,
            history_avg_score=issue.history_avg_score,
            history_conflict_rate=issue.history_conflict_rate,
            history_similarity=issue.history_similarity,
            history_similar_hits=issue.history_similar_hits,
            history_similar_conflict_rate=issue.history_similar_conflict_rate,
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
            -_infer_evidence_score(issue),
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
    by_category = dict(Counter(issue.category for issue in normalized))
    by_severity = dict(Counter(issue.severity for issue in normalized))
    confidence_counts = dict(Counter(_issue_confidence_band(issue) for issue in normalized))
    triage_counts = dict(Counter(_issue_triage_label(issue) for issue in normalized))
    action_items = [issue.action for issue in normalized if issue.action][:3]
    risk_score = _calculate_risk_score(normalized)
    return {
        "total": len(normalized),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "auto_fixable_count": len(auto_fixable),
        "blocking_count": sum(1 for issue in normalized if _is_blocking_issue(issue)),
        "needs_review_count": sum(1 for issue in normalized if _issue_needs_review(issue)),
        "top_issue": top_issue,
        "first_action": top_issue.action if top_issue else "",
        "by_category": by_category,
        "by_severity": by_severity,
        "confidence_counts": confidence_counts,
        "triage_counts": triage_counts,
        "risk_score": risk_score,
        "risk_level": (
            "critical"
            if risk_score >= 80
            else "high"
            if risk_score >= 55
            else "medium"
            if risk_score >= 25
            else "low"
        ),
        "action_items": action_items,
        "execution_plan": _build_execution_plan(normalized),
    }


def issue_to_dict(issue: DiagnosticIssue) -> dict:
    return {
        "severity": issue.severity,
        "category": issue.category,
        "title": issue.title,
        "message": issue.message,
        "location": issue.location,
        "evidence_line": issue.evidence_line,
        "evidence_score": _infer_evidence_score(issue),
        "evidence_source_trust": round(_infer_evidence_source_trust(issue), 2),
        "evidence_support_count": issue.evidence_support_count,
        "evidence_conflict": issue.evidence_conflict,
        "history_hits": issue.history_hits,
        "history_avg_score": issue.history_avg_score,
        "history_conflict_rate": issue.history_conflict_rate,
        "history_similarity": issue.history_similarity,
        "history_similar_hits": issue.history_similar_hits,
        "history_similar_conflict_rate": issue.history_similar_conflict_rate,
        "suggestion": issue.suggestion,
        "priority": issue.priority,
        "auto_fixable": _infer_auto_fixable(issue),
        "confidence": _issue_confidence_band(issue),
        "triage": _issue_triage_label(issue),
    }


def _summarize_convergence_metrics(
    metrics: list[dict],
    *,
    issues: Optional[list[DiagnosticIssue]] = None,
) -> dict:
    max_iterations = max((item.get("max_iter") or 0 for item in metrics), default=0)
    worst_residual = max(
        (item.get("final_residual") for item in metrics if item.get("final_residual") is not None),
        default=None,
    )
    residual_trends = Counter(
        item.get("residual_trend") for item in metrics if item.get("residual_trend")
    )
    increment_trends = Counter(
        item.get("increment_trend") for item in metrics if item.get("increment_trend")
    )
    issue_list = issues or []
    has_convergence_issue = any(issue.category == "convergence" for issue in issue_list)
    has_not_converged_status = any(
        (item.get("status") or "").upper() == "NOT CONVERGED" for item in metrics
    )

    return {
        "file_count": len(metrics),
        "has_not_converged": has_not_converged_status or has_convergence_issue,
        "max_iterations": max_iterations if max_iterations > 0 else None,
        "worst_final_residual": worst_residual,
        "residual_trend_counts": dict(residual_trends),
        "increment_trend_counts": dict(increment_trends),
    }


def diagnosis_result_to_dict(
    result: DiagnoseResult,
    *,
    results_dir: Optional[Path] = None,
    inp_file: Optional[Path] = None,
    ai_enabled: Optional[bool] = None,
) -> dict:
    summary = build_diagnosis_summary(result.issues)
    top_issue = summary.get("top_issue")
    summary_export = dict(summary)
    summary_export["top_issue"] = (
        issue_to_dict(top_issue) if isinstance(top_issue, DiagnosticIssue) else None
    )
    solver_run = (
        summarize_solver_run(results_dir)
        if results_dir is not None
        else {
            "solver": "unknown",
            "status": "unknown",
            "primary_log": None,
            "status_reason": None,
            "text_sources": [],
            "artifacts": {
                "input_files": [],
                "log_files": [],
                "result_files": [],
            },
        }
    )
    convergence_files = [dict(item) for item in result.convergence_metrics]
    if not convergence_files and results_dir is not None and results_dir.exists():
        convergence_files = _extract_convergence_metrics(results_dir)
    convergence_summary = _summarize_convergence_metrics(
        convergence_files,
        issues=result.issues,
    )

    return {
        "success": result.success,
        "error": result.error,
        "issue_count": result.issue_count,
        "summary": summary_export,
        "issues": [issue_to_dict(issue) for issue in result.issues],
        "level1_issues": [issue_to_dict(issue) for issue in result.level1_issues],
        "level2_issues": [issue_to_dict(issue) for issue in result.level2_issues],
        "ai_diagnosis": result.level3_diagnosis,
        "similar_cases": [dict(case) for case in result.similar_cases],
        "solver_run": solver_run,
        "convergence": {
            "summary": convergence_summary,
            "files": convergence_files,
        },
        "meta": {
            "results_dir": str(results_dir) if results_dir is not None else None,
            "inp_file": str(inp_file) if inp_file is not None else None,
            "ai_enabled": ai_enabled,
            "detected_solver": solver_run.get("solver"),
            "solver_status": solver_run.get("status"),
        },
    }


def _pick_ai_issues(
    level1_issues: list[DiagnosticIssue], level2_issues: list[DiagnosticIssue]
) -> list[DiagnosticIssue]:
    merged = normalize_issues(level1_issues + level2_issues)
    if len(merged) <= AI_MAX_ISSUES:
        return merged

    # Round-robin by category keeps diagnosis evidence diverse.
    by_category: dict[str, list[DiagnosticIssue]] = {}
    for issue in merged:
        by_category.setdefault(issue.category, []).append(issue)

    selected: list[DiagnosticIssue] = []

    # First pass: one issue per category.
    for category, issues in by_category.items():
        if not issues:
            continue
        selected.append(issues.pop(0))
        if len(selected) >= AI_MAX_ISSUES:
            return selected

    # Second pass: fill remaining slots with per-category cap.
    counts = Counter(issue.category for issue in selected)
    while len(selected) < AI_MAX_ISSUES:
        progress = False
        for category, issues in by_category.items():
            if not issues:
                continue
            if counts[category] >= AI_MAX_ISSUES_PER_CATEGORY:
                continue
            selected.append(issues.pop(0))
            counts[category] += 1
            progress = True
            if len(selected) >= AI_MAX_ISSUES:
                break
        if not progress:
            break

    return selected[:AI_MAX_ISSUES]


def _issue_keywords(issue: DiagnosticIssue) -> list[str]:
    keywords: list[str] = []
    keywords.extend(ISSUE_KEYWORDS_BY_CATEGORY.get(issue.category, []))

    text = _normalize_text_key(f"{issue.message} {issue.suggestion or ''}")
    for token in text.split():
        if len(token) < 4 or token.isdigit() or token in ISSUE_TOKEN_STOPWORDS:
            continue
        keywords.append(token)

    deduped: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            deduped.append(kw)
    return deduped[:10]


def _parse_issue_location_hint(location: Optional[str]) -> tuple[Optional[str], Optional[int]]:
    if not location:
        return None, None

    colon_match = re.search(r"([^\s:]+\.[A-Za-z0-9_]+):(\d+)", location)
    if colon_match:
        return colon_match.group(1), int(colon_match.group(2))

    file_match = re.search(r"([^\s]+?\.[A-Za-z0-9_]+)", location)
    if file_match:
        tail = location[file_match.end() :]
        line_match = re.search(r"(?:\bline\b|#|:)?[^\d]{0,12}(\d+)", tail, re.IGNORECASE)
        return file_match.group(1), int(line_match.group(1)) if line_match else None

    return None, None


def _build_issue_evidence_sources(
    results_dir: Path,
    *,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[tuple[str, list[str]]]:
    sources: list[tuple[str, list[str]]] = []
    seen: set[str] = set()

    for path in _get_solver_text_sources(results_dir, ctx=ctx):
        key = str(path.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            sources.append((path.name, _read_lines_cached(path, ctx=ctx)))
        except OSError:
            continue

    if inp_file and inp_file.exists():
        key = str(inp_file.resolve()).lower()
        if key not in seen:
            try:
                sources.append((inp_file.name, _read_lines_cached(inp_file, ctx=ctx)))
            except OSError:
                pass

    return sources


def _format_evidence_line(file_name: str, line_no: int, raw_line: str) -> str:
    excerpt = raw_line.strip()
    if len(excerpt) > 220:
        excerpt = excerpt[:217] + "..."
    return f"{file_name}:{line_no}: {excerpt}"


def _find_best_evidence_line(
    lines: list[str],
    keywords: list[str],
) -> Optional[tuple[int, str, int, int]]:
    best_idx = -1
    best_score = 0

    lowered_keywords = [kw.lower() for kw in keywords if kw]
    unique_keywords = list(dict.fromkeys(lowered_keywords))
    for idx, line in enumerate(lines, 1):
        lowered = line.lower()
        if not lowered.strip():
            continue
        score = sum(1 for kw in unique_keywords if kw in lowered)
        if score > best_score:
            best_score = score
            best_idx = idx

    if best_idx <= 0:
        return None
    return best_idx, lines[best_idx - 1], best_score, max(1, len(unique_keywords))


def _count_supporting_sources(
    sources: list[tuple[str, list[str]]],
    keywords: list[str],
) -> int:
    lowered_keywords = [kw.lower() for kw in keywords if kw]
    if not lowered_keywords:
        return 0

    support = 0
    for _, src_lines in sources:
        found = False
        for raw in src_lines:
            lowered = raw.lower()
            if any(kw in lowered for kw in lowered_keywords):
                found = True
                break
        if found:
            support += 1
    return support


def _attach_issue_evidence(
    results_dir: Path,
    issues: list[DiagnosticIssue],
    *,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    if not issues:
        return issues

    sources = _build_issue_evidence_sources(results_dir, inp_file=inp_file, ctx=ctx)
    if not sources:
        return issues

    by_name: dict[str, tuple[str, list[str]]] = {
        name.lower(): (name, lines) for name, lines in sources
    }

    for issue in issues:
        keywords = _issue_keywords(issue)
        if issue.category == "convergence":
            keywords.extend(["resid", "increment size", "not converged", "diverg"])
        issue.evidence_support_count = _count_supporting_sources(sources, keywords)

        if issue.evidence_line:
            if issue.evidence_score is None:
                issue.evidence_score = _infer_evidence_score(issue)
            continue

        hinted_file, hinted_line = _parse_issue_location_hint(issue.location)
        if hinted_file:
            source = by_name.get(hinted_file.lower())
            if source:
                src_name, src_lines = source
                if hinted_line is not None and 1 <= hinted_line <= len(src_lines):
                    issue.evidence_line = _format_evidence_line(
                        src_name,
                        hinted_line,
                        src_lines[hinted_line - 1],
                    )
                    issue.evidence_support_count = max(
                        issue.evidence_support_count or 0,
                        1,
                    )
                    issue.evidence_score = round(
                        _apply_evidence_conflict_penalty(0.98, issue),
                        2,
                    )
                    continue

        if not keywords:
            continue

        candidate_sources = sources
        if hinted_file:
            source = by_name.get(hinted_file.lower())
            if source:
                candidate_sources = [source] + [
                    item for item in sources if item[0].lower() != hinted_file.lower()
                ]

        for src_name, src_lines in candidate_sources:
            matched = _find_best_evidence_line(src_lines, keywords)
            if matched is None:
                continue
            line_no, raw_line, hit_count, keyword_total = matched
            issue.evidence_line = _format_evidence_line(src_name, line_no, raw_line)
            issue.evidence_support_count = max(issue.evidence_support_count or 0, 1)
            match_ratio = hit_count / max(1, keyword_total)
            issue.evidence_score = round(
                _apply_evidence_conflict_penalty(0.55 + 0.4 * match_ratio, issue),
                2,
            )
            break

        if issue.evidence_score is None:
            issue.evidence_score = _infer_evidence_score(issue)

    return issues


def _build_ai_evidence_digest(
    issues: list[DiagnosticIssue],
    similar_cases: list[dict],
    *,
    stderr_snippets: str = "",
    physical_data: str = "",
    stderr_summary: str = "",
    convergence_summary: Optional[dict] = None,
) -> str:
    if not issues and not similar_cases:
        return ""

    evidence_flags = {
        "issues": bool(issues),
        "stderr_snippets": bool((stderr_snippets or "").strip()),
        "physical_data": bool((physical_data or "").strip()),
        "stderr_summary": bool((stderr_summary or "").strip()),
        "similar_cases": bool(similar_cases),
    }
    evidence_score = round(
        sum(1 for ok in evidence_flags.values() if ok) * 100 / len(evidence_flags)
    )
    missing = [name for name, ok in evidence_flags.items() if not ok]

    lines: list[str] = []
    lines.append(f"Evidence coverage: {evidence_score}%")
    if missing:
        lines.append("Missing evidence: " + ", ".join(missing))

    if issues:
        severity_counter = Counter(issue.severity for issue in issues)
        category_counter = Counter(issue.category for issue in issues)
        top_categories = ", ".join(
            f"{name}:{count}" for name, count in category_counter.most_common(4)
        )
        lines.append(
            "Issues: "
            f"total={len(issues)}, "
            f"errors={severity_counter.get('error', 0)}, "
            f"warnings={severity_counter.get('warning', 0)}, "
            f"categories={top_categories or 'none'}"
        )
        first_actions = [issue.action for issue in issues if issue.action][:3]
        if first_actions:
            lines.append("Top actions: " + " | ".join(first_actions))

    if similar_cases:
        top_case = similar_cases[0]
        lines.append(
            "Best reference: "
            f"{top_case.get('name', 'N/A')} "
            f"(similarity={top_case.get('similarity_score', 'N/A')}%)"
        )

    if convergence_summary:
        lines.append(
            "Convergence: "
            f"files={convergence_summary.get('file_count', 0)}, "
            f"not_converged={convergence_summary.get('has_not_converged', False)}, "
            f"max_iter={convergence_summary.get('max_iterations')}, "
            f"worst_residual={convergence_summary.get('worst_final_residual')}"
        )

    return "\n".join(lines)


def _build_rule_based_diagnosis(issues: list[DiagnosticIssue]) -> str:
    """Generate deterministic fallback diagnosis when LLM output is unavailable."""
    if not issues:
        return "閺堫亜褰傞悳浼存付鐟?AI 濞ｅ崬瀹崇拠濠冩焽閻ㄥ嫰鏁婄拠顖樷偓?"

    top_issues = normalize_issues(issues)[:3]
    lines: list[str] = ["閺堚偓閸欘垵鍏橀弽鐟版礈閿?"]
    for issue in top_issues:
        lines.append(f"- [{issue.severity}] {issue.title}: {issue.cause}")

    lines.append("")
    lines.append("娣囶喖顦插楦款唴閿?")
    for idx, issue in enumerate(top_issues, 1):
        action = (
            issue.action
            or "閹稿顕氶梻顕€顣界猾璇插焼闁劙銆嶅Λ鈧弻銉ㄧ翻閸忋儱宕遍悧鍥モ偓浣界珶閻ｅ苯鎷版潪鍊熷祹鐎规矮绠熼妴?"
        )
        lines.append(f"{idx}. {action}")

    lines.append("")
    lines.append("妤犲矁鐦夊銉╊€冮敍?")
    lines.append(
        "1. 闁插秵鏌婃潻鎰攽濮瑰倽袙楠炲墎鈥樼拋?stderr 娑撳秴鍟€閸戣櫣骞囬崥宀€琚崗鎶芥暛鐠囧秲鈧?"
    )
    lines.append("2. 濡偓閺?.sta 閺€鑸垫殐閻樿埖鈧椒绗屽▓瀣▕閺勵垰鎯侀弨鐟版澖閵?")
    lines.append(
        "3. 鐎佃鐦崗鎶芥暛娴ｅ秶些/鎼存柨濮忛弫浼村櫤缁狙勬Ц閸氾箑娲栭崚鏉挎値閻炲棜瀵栭崶娣偓?"
    )

    return "\n".join(lines)


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


def _get_solver_text_sources(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[Path]:
    if ctx is None:
        return collect_solver_text_sources(results_dir)
    if not ctx.solver_text_sources_loaded:
        ctx.solver_text_sources = collect_solver_text_sources(results_dir)
        ctx.solver_text_sources_loaded = True
    return ctx.solver_text_sources


def _get_solver_run_summary(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> dict:
    if ctx is None:
        return summarize_solver_run(results_dir)
    if not ctx.solver_run_summary_loaded:
        ctx.solver_run_summary = summarize_solver_run(results_dir)
        ctx.solver_run_summary_loaded = True
    return ctx.solver_run_summary or {}


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
                float(line[offset : offset + _FRD_VALUE_WIDTH])
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

            if (
                line.startswith("    2C")
                or line.startswith("    2PSET")
                or line.startswith("    3C")
                or line.startswith("    3PSET")
            ):
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
                                magnitude = (
                                    values[0] ** 2 + values[1] ** 2 + values[2] ** 2
                                ) ** 0.5
                            else:
                                magnitude = abs(values[0])
                            local_disp_count += 1
                            local_disp_sum += magnitude
                            if magnitude > local_max_disp:
                                local_max_disp = magnitude
                                local_max_disp_node = row_id
                        elif field_name == "STRESS":
                            stress_value = (
                                abs(values[3]) if len(values) >= 4 else max(abs(v) for v in values)
                            )
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
        log.warning("閸欏倽鈧啯顢嶆笟瀣氨閸旂姾娴囨径杈Е: %s", exc)
        return None


def diagnose_results(
    results_dir: Path | str,
    client: Optional[LLMClient] = None,
    inp_file: Optional[Path] = None,
    *,
    stream: bool = True,
    guardrails_path: Optional[Path] = None,
    history_db_path: Optional[Path] = None,
) -> DiagnoseResult:
    """
    娑撳鐪板▎陇鐦栭弬顓溾偓?

    Args:
        results_dir: 閸栧懎鎯?.frd / .sta / .dat 閺傚洣娆㈤惃鍕窗瑜?
        client: LLM 鐎广垺鍩涚粩顖ょ礄閸欘垶鈧绱濇稉宥勭炊閹存牔璐?None 閺冩儼鐑︽潻?Level 3閿?
        inp_file: 鏉堟挸鍙嗛惃?.inp 閺傚洣娆㈢捄顖氱窞閿涘牏鏁ゆ禍搴㈠絹閸欐牕鍘撻弫鐗堝祦鏉╂稖顢戝鍫滅伐閸栧綊鍘ら敍?
        stream: 閺勵垰鎯佸ù浣哥础鏉堟挸鍤?

    Returns:
        DiagnoseResult
    """
    result = DiagnoseResult(success=True)

    # 绾喕绻?results_dir 閺?Path 鐎电钖?
    if isinstance(results_dir, str):
        results_dir = Path(results_dir)

    ctx = _build_context(results_dir, inp_file)

    try:
        # ========== Level 1: 鐟欏嫬鍨Λ鈧ù瀣剁礄閺冪姵娼禒鑸靛⒔鐞涘矉绱?=========
        result.level1_issues.extend(_check_solver_run_status(results_dir, ctx=ctx))
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
        result.level1_issues = _attach_issue_evidence(
            results_dir,
            result.level1_issues,
            inp_file=inp_file,
            ctx=ctx,
        )
        result.level1_issues = _apply_category_evidence_guardrails(
            result.level1_issues,
            guardrails_path=guardrails_path,
        )
        result.level1_issues = _apply_history_consistency_guardrails(
            result.level1_issues,
            history_db_path=history_db_path,
        )

        # ========== Level 2: 閸欏倽鈧啯顢嶆笟瀣嚠濮ｆ棑绱欓弮鐘虫蒋娴犺埖澧界悰宀嬬礆==========
        ref_result = _check_reference_cases(results_dir, inp_file, ctx=ctx)
        result.level2_issues = normalize_issues(ref_result["issues"])
        result.level2_issues = _attach_issue_evidence(
            results_dir,
            result.level2_issues,
            inp_file=inp_file,
            ctx=ctx,
        )
        result.level2_issues = _apply_category_evidence_guardrails(
            result.level2_issues,
            guardrails_path=guardrails_path,
        )
        result.level2_issues = _apply_history_consistency_guardrails(
            result.level2_issues,
            history_db_path=history_db_path,
        )
        result.similar_cases = ref_result["similar_cases"]
        result.convergence_metrics = _get_convergence_metrics(results_dir, ctx=ctx)

        # ========== Level 3: AI 濞ｅ崬瀹抽崚鍡樼€介敍鍫滅矌瑜版挸鐡ㄩ崷?error/warning 閺冩儼鐨熼悽顭掔礆==========
        real_issues = [
            i
            for i in normalize_issues(result.level1_issues + result.level2_issues)
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
        result.error = f"鐠囧﹥鏌囨径杈Е: {exc}"
        log.exception("鐠囧﹥鏌囨潻鍥┾柤閸戞椽鏁?")

    return result


# ------------------------------------------------------------------ #
# Level 1: 鐟欏嫬鍨Λ鈧ù瀣毐閺?
# ------------------------------------------------------------------ #

# Jacobian / Hourglass 濡偓濞村膩瀵骏绱欐稉宥呭隘閸掑棗銇囩亸蹇撳晸閿?
JACOBIAN_PATTERNS = [
    re.compile(r"negative jacobian", re.IGNORECASE),
    re.compile(r"hourglassing", re.IGNORECASE),
    re.compile(r"hourlim", re.IGNORECASE),
    re.compile(r"nonpositive jacobian", re.IGNORECASE),
]

# 閺€鑸垫殐閹囨６妫版ɑ顥呭ù瀣佸蹇ョ礄婢х偛宸遍懛?calculix_patterns.txt閿?
CONVERGENCE_PATTERNS = [
    re.compile(r"not\s+converged", re.IGNORECASE),
    re.compile(r"increment\s+size\s+smaller", re.IGNORECASE),
    re.compile(r"divergence", re.IGNORECASE),
    re.compile(r"no\s+convergence", re.IGNORECASE),
    re.compile(r"convergence\s+failed", re.IGNORECASE),
    re.compile(r"fatal error", re.IGNORECASE),
    re.compile(r"ddebdf\s+did\s+not\s+converge", re.IGNORECASE),
]

# 閺冪姵鏅?INP 閸楋紕澧栧Λ鈧ù瀣佸?
INVALID_CARD_PATTERNS = [
    re.compile(r"card image cannot be interpreted", re.IGNORECASE),
    re.compile(r"unknown keyword", re.IGNORECASE),
]

# 閺夋劖鏋＄紓鍝勩亼濡偓濞村膩瀵骏绱欓弶銉ㄥ殰 CalculiX 濠ф劗鐖?528 濡€崇础閿?
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

# 閸欏倹鏆熸稉宥堢槕閸掝偅顥呭ù瀣佸?
PARAMETER_PATTERNS = [
    re.compile(r"parameter not recognized", re.IGNORECASE),
]

# MPC/缁撅附娼弫浼村櫤鐡掑懘妾哄Λ鈧ù瀣佸蹇ョ礄閺夈儴鍤?CalculiX 濠ф劗鐖滈敍?
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

# 鏉炲€熷祹娴肩娀鈧帡妫舵０妯活梾濞村膩瀵?
LOAD_TRANSFER_PATTERNS = [
    re.compile(r"RHS only consists of 0\.0", re.IGNORECASE),
    re.compile(r"concentrated loads:\s*0\s*$", re.IGNORECASE | re.MULTILINE),
]

# 鏉堝湱鏅弶鈥叉闂傤噣顣藉Λ鈧ù瀣佸?
BOUNDARY_PATTERNS = [
    re.compile(r"zero pivot", re.IGNORECASE),
    re.compile(r"singular matrix", re.IGNORECASE),
    re.compile(r"濞嗙姷瀹抽弶鐒瞮nderconstrained", re.IGNORECASE),
    re.compile(r"鏉╁洨瀹抽弶鐒瞣verconstrained", re.IGNORECASE),
]

# 缂冩垶鐗哥拹銊╁櫤闂傤噣顣藉Λ鈧ù瀣佸?
MESH_QUALITY_PATTERNS = [
    re.compile(r"negative.*jacobian", re.IGNORECASE),
    re.compile(r"distorted.*element", re.IGNORECASE),
    re.compile(r"element.*invert", re.IGNORECASE),
    re.compile(r"skewness", re.IGNORECASE),
    re.compile(r"aspect ratio", re.IGNORECASE),
]

# 閹恒儴袝闂傤噣顣藉Λ鈧ù瀣佸蹇ョ礄婢х偛宸遍懛?calculix_patterns.txt閿?
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
    re.compile(r"tied MPC.*(error|fail|not)", re.IGNORECASE),
    re.compile(r"contact.*adjust", re.IGNORECASE),
]

# 閺傚洣娆?I/O 闁挎瑨顕ゅΛ鈧ù瀣佸蹇ョ礄閺夈儴鍤?CalculiX 濠ф劗鐖滈敍?
FILE_IO_PATTERNS = [
    re.compile(r"could not open file", re.IGNORECASE),
    re.compile(r"file name is lacking", re.IGNORECASE),
    re.compile(r"file name too long", re.IGNORECASE),
    re.compile(r"input file name is too long", re.IGNORECASE),
    re.compile(r"could not open", re.IGNORECASE),
    re.compile(r"could not delete file", re.IGNORECASE),
    re.compile(r"syntax error", re.IGNORECASE),
]

# 閻劍鍩涢崡鏇炲帗/閺夋劖鏋￠柨娆掝嚖濡偓濞村膩瀵骏绱欓弶銉ㄥ殰 CalculiX 濠ф劗鐖滈敍?
USER_ELEMENT_PATTERNS = [
    re.compile(r"user element", re.IGNORECASE),
    re.compile(r"umat", re.IGNORECASE),
    re.compile(r"no user material subroutine", re.IGNORECASE),
    re.compile(r"user subroutine", re.IGNORECASE),
]

# 閸斻劌濮忕€?濡剝鈧礁鍨庨弸鎰版晩鐠囶垱膩瀵骏绱欓弶銉ㄥ殰 CalculiX 濠ф劗鐖滈敍?
DYNAMICS_PATTERNS = [
    re.compile(r"frequencies:.*less than 1 eigenvalue", re.IGNORECASE),
    re.compile(r"eigenvalue.*(error|failed|cannot|not)", re.IGNORECASE),
    re.compile(r"modal dynamic.*(error|failed|cannot|not)", re.IGNORECASE),
    re.compile(r"cyclic symmetric.*(error|failed|cannot|not)", re.IGNORECASE),
    re.compile(r"alpha is greater", re.IGNORECASE),
    re.compile(r"alpha is smaller", re.IGNORECASE),
]


def _is_healthy_convergence_trend(metrics: list[dict]) -> bool:
    if not metrics:
        return False

    has_not_converged = any(
        (item.get("status") or "").upper() == "NOT CONVERGED" for item in metrics
    )
    if has_not_converged:
        return False

    residual_trends = [item.get("residual_trend") for item in metrics if item.get("residual_trend")]
    if not residual_trends:
        return False
    if any(trend == "increasing" for trend in residual_trends):
        return False
    if sum(1 for trend in residual_trends if trend == "decreasing") < 1:
        return False

    increment_trends = [
        item.get("increment_trend") for item in metrics if item.get("increment_trend")
    ]
    if any(trend == "growing" for trend in increment_trends):
        return False

    residual_values = [
        float(item["final_residual"]) for item in metrics if item.get("final_residual") is not None
    ]
    if residual_values and max(residual_values) > 1e-2:
        return False

    return True


def _apply_convergence_contradiction_rules(
    issues: list[DiagnosticIssue],
    metrics: list[dict],
) -> list[DiagnosticIssue]:
    if not issues or not _is_healthy_convergence_trend(metrics):
        return normalize_issues(issues)

    adjusted: list[DiagnosticIssue] = []
    conflict_reason = "STA trend indicates healthy convergence."
    for issue in issues:
        if issue.category != "convergence" or issue.severity not in {"error", "warning"}:
            adjusted.append(issue)
            continue

        downgraded_severity = "warning" if issue.severity == "error" else "info"
        note = "Auto-downgraded: convergence trend is healthy in .sta metrics."
        suggestion = (issue.suggestion or "").strip()
        if suggestion:
            if note not in suggestion:
                suggestion = f"{suggestion}; {note}"
        else:
            suggestion = note

        evidence_conflict = (issue.evidence_conflict or "").strip()
        if evidence_conflict:
            if conflict_reason not in evidence_conflict:
                evidence_conflict = f"{evidence_conflict}; {conflict_reason}"
        else:
            evidence_conflict = conflict_reason

        evidence_score = issue.evidence_score
        if evidence_score is not None:
            evidence_score = round(
                _apply_evidence_conflict_penalty(float(evidence_score), issue),
                2,
            )

        adjusted.append(
            DiagnosticIssue(
                severity=downgraded_severity,
                category=issue.category,
                message=issue.message,
                location=issue.location,
                evidence_line=issue.evidence_line,
                evidence_score=evidence_score,
                evidence_support_count=issue.evidence_support_count,
                evidence_conflict=evidence_conflict,
                history_hits=issue.history_hits,
                history_avg_score=issue.history_avg_score,
                history_conflict_rate=issue.history_conflict_rate,
                history_similarity=issue.history_similarity,
                history_similar_hits=issue.history_similar_hits,
                history_similar_conflict_rate=issue.history_similar_conflict_rate,
                suggestion=suggestion,
                priority=issue.priority,
                auto_fixable=issue.auto_fixable,
            )
        )

    return normalize_issues(adjusted)


def _apply_category_evidence_guardrails(
    issues: list[DiagnosticIssue],
    *,
    guardrails_path: Optional[Path] = None,
) -> list[DiagnosticIssue]:
    if not issues:
        return normalize_issues(issues)

    guardrails_key = str(guardrails_path) if guardrails_path is not None else ""
    guardrails = _get_evidence_guardrails(guardrails_key)
    adjusted: list[DiagnosticIssue] = []

    for issue in issues:
        guardrail = (
            guardrails.get(issue.category) or guardrails.get("default") or guardrails.get("*")
        )
        support_count = issue.evidence_support_count
        if support_count is None:
            support_count = 1 if issue.evidence_line else 0

        if issue.severity != "error" or guardrail is None:
            adjusted.append(issue)
            continue

        min_support = int(guardrail.get("min_support", 1))
        min_score = float(guardrail.get("min_score", 0.0))
        min_trust = float(guardrail.get("min_trust", 0.0))
        score_penalty = float(guardrail.get("score_penalty", 0.1))
        evidence_score = issue.evidence_score
        if evidence_score is None:
            evidence_score = _infer_evidence_score(issue)
        source_trust = _infer_evidence_source_trust(issue)

        low_support = support_count < min_support
        low_score = float(evidence_score) < min_score
        low_trust = source_trust < min_trust
        should_downgrade = low_support or low_score or low_trust
        if not should_downgrade:
            adjusted.append(issue)
            continue

        reason_parts: list[str] = []
        if low_support:
            reason_parts.append(f"support={support_count}<{min_support}")
        if low_score:
            reason_parts.append(f"score={float(evidence_score):.2f}<{min_score:.2f}")
        if low_trust:
            reason_parts.append(f"trust={source_trust:.2f}<{min_trust:.2f}")
        reason_suffix = ", ".join(reason_parts)
        conflict_reason = f"Evidence guardrail triggered ({reason_suffix})."
        note = "Auto-downgraded by category evidence guardrail."

        suggestion = (issue.suggestion or "").strip()
        if suggestion:
            if note not in suggestion:
                suggestion = f"{suggestion}; {note}"
        else:
            suggestion = note

        evidence_conflict = (issue.evidence_conflict or "").strip()
        if evidence_conflict:
            if conflict_reason not in evidence_conflict:
                evidence_conflict = f"{evidence_conflict}; {conflict_reason}"
        else:
            evidence_conflict = conflict_reason

        evidence_score = round(_clamp_evidence_score(float(evidence_score) - score_penalty), 2)

        adjusted.append(
            DiagnosticIssue(
                severity="warning",
                category=issue.category,
                message=issue.message,
                location=issue.location,
                evidence_line=issue.evidence_line,
                evidence_score=evidence_score,
                evidence_support_count=support_count,
                evidence_conflict=evidence_conflict,
                history_hits=issue.history_hits,
                history_avg_score=issue.history_avg_score,
                history_conflict_rate=issue.history_conflict_rate,
                history_similarity=issue.history_similarity,
                history_similar_hits=issue.history_similar_hits,
                history_similar_conflict_rate=issue.history_similar_conflict_rate,
                suggestion=suggestion,
                priority=issue.priority,
                auto_fixable=issue.auto_fixable,
            )
        )

    return normalize_issues(adjusted)


def _apply_history_consistency_guardrails(
    issues: list[DiagnosticIssue],
    *,
    history_db_path: Optional[Path] = None,
) -> list[DiagnosticIssue]:
    if not issues:
        return normalize_issues(issues)

    store = DiagnosisHistoryStore(history_db_path)
    if not store.enabled:
        return normalize_issues(issues)

    normalized = normalize_issues(issues)
    adjusted: list[DiagnosticIssue] = []
    observations: list[IssueObservation] = []

    for issue in normalized:
        issue_key = _issue_dedup_key(issue)[1]
        stats = store.get_stats(issue_key=issue_key, category=issue.category)
        similar_stats = None
        if stats.hits <= 0:
            similar_candidates = store.get_similar_stats(
                issue_key=issue_key,
                category=issue.category,
                limit=1,
                min_similarity=HISTORY_SIMILARITY_MIN,
            )
            if similar_candidates:
                similar_stats = similar_candidates[0]

        evidence_score = float(
            issue.evidence_score
            if issue.evidence_score is not None
            else _infer_evidence_score(issue)
        )
        evidence_conflict = (issue.evidence_conflict or "").strip()
        suggestion = issue.suggestion
        severity = issue.severity

        if (
            stats.hits >= HISTORY_PENALTY_MIN_HITS
            and stats.conflict_rate >= HISTORY_PENALTY_MIN_CONFLICT_RATE
        ):
            evidence_score = _clamp_evidence_score(evidence_score - HISTORY_PENALTY)
            reason = (
                "Historical consistency low "
                f"(hits={stats.hits}, conflict_rate={stats.conflict_rate:.2f})."
            )
            if evidence_conflict:
                if reason not in evidence_conflict:
                    evidence_conflict = f"{evidence_conflict}; {reason}"
            else:
                evidence_conflict = reason
            if severity == "error":
                severity = "warning"
                note = "Auto-downgraded by history consistency guardrail."
                suggestion = (suggestion or "").strip()
                if suggestion:
                    if note not in suggestion:
                        suggestion = f"{suggestion}; {note}"
                else:
                    suggestion = note
        elif (
            stats.hits >= HISTORY_BOOST_MIN_HITS
            and stats.avg_score >= HISTORY_BOOST_MIN_SCORE
            and stats.conflict_rate <= HISTORY_BOOST_MAX_CONFLICT_RATE
        ):
            evidence_score = _clamp_evidence_score(evidence_score + HISTORY_BOOST)
        elif similar_stats is not None:
            if (
                similar_stats.hits >= HISTORY_SIM_PENALTY_MIN_HITS
                and similar_stats.conflict_rate >= HISTORY_SIM_PENALTY_MIN_CONFLICT_RATE
            ):
                evidence_score = _clamp_evidence_score(evidence_score - HISTORY_SIM_PENALTY)
                reason = (
                    "Historical similar issues unstable "
                    f"(sim={similar_stats.similarity:.2f}, hits={similar_stats.hits}, "
                    f"conflict_rate={similar_stats.conflict_rate:.2f})."
                )
                if evidence_conflict:
                    if reason not in evidence_conflict:
                        evidence_conflict = f"{evidence_conflict}; {reason}"
                else:
                    evidence_conflict = reason
                if severity == "error":
                    severity = "warning"
                    note = "Auto-downgraded by similar-history guardrail."
                    suggestion = (suggestion or "").strip()
                    if suggestion:
                        if note not in suggestion:
                            suggestion = f"{suggestion}; {note}"
                    else:
                        suggestion = note
            elif (
                similar_stats.hits >= HISTORY_SIM_BOOST_MIN_HITS
                and similar_stats.avg_score >= HISTORY_SIM_BOOST_MIN_SCORE
                and similar_stats.conflict_rate <= HISTORY_SIM_BOOST_MAX_CONFLICT_RATE
            ):
                evidence_score = _clamp_evidence_score(evidence_score + HISTORY_SIM_BOOST)

        support_count = issue.evidence_support_count
        if support_count is None:
            support_count = 1 if issue.evidence_line else 0
        source_trust = _infer_evidence_source_trust(issue)

        adjusted_issue = DiagnosticIssue(
            severity=severity,
            category=issue.category,
            message=issue.message,
            location=issue.location,
            evidence_line=issue.evidence_line,
            evidence_score=round(evidence_score, 2),
            evidence_support_count=support_count,
            evidence_conflict=evidence_conflict or None,
            history_hits=stats.hits,
            history_avg_score=round(float(stats.avg_score), 2) if stats.hits > 0 else 0.0,
            history_conflict_rate=round(float(stats.conflict_rate), 2) if stats.hits > 0 else 0.0,
            history_similarity=round(float(similar_stats.similarity), 2)
            if similar_stats is not None
            else None,
            history_similar_hits=int(similar_stats.hits) if similar_stats is not None else None,
            history_similar_conflict_rate=(
                round(float(similar_stats.conflict_rate), 2) if similar_stats is not None else None
            ),
            suggestion=suggestion,
            priority=issue.priority,
            auto_fixable=issue.auto_fixable,
        )
        adjusted.append(adjusted_issue)
        observations.append(
            IssueObservation(
                issue_key=issue_key,
                category=issue.category,
                evidence_score=adjusted_issue.evidence_score or 0.0,
                source_trust=source_trust,
                support_count=support_count,
                has_conflict=bool(adjusted_issue.evidence_conflict),
            )
        )

    store.record_observations(observations)
    return normalize_issues(adjusted)


def _check_convergence(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲鏁归弫娑㈡６妫版﹫绱濇导妯哄帥娴ｈ法鏁ょ紒鎾寸€崠?.sta 閹稿洦鐖ｉ敍灞芥礀闁偓閸?stderr 閺傚洦婀扮拠浣瑰祦閵?
    閸戝棛鈥橀幀褏鐡ラ悾銉窗
    - 閸忓牏婀呯紒鎾寸€崠鏍ㄦ暪閺佹稒瀵氶弽鍥风礄闁灝鍘ゆ禒鍛殶閸忔娊鏁拠宥堫嚖閹躲儻绱?
    - 閺傚洦婀板Ο鈥崇础娴犲懎婀?stderr 娑擃叀袝閸?    - fatal error 韫囧懘銆忔导鎾閺€鑸垫殐鐠囶厼顣ㄩ崗鎶芥暛鐠?"""
    issues: list[DiagnosticIssue] = []
    metrics = _get_convergence_metrics(results_dir, ctx=ctx)
    summary = _summarize_convergence_metrics(metrics)

    if summary.get("has_not_converged"):
        worst_residual = summary.get("worst_final_residual")
        suggestion = "濡偓閺屻儴娴囬懡閿嬵劄鐠佸墽鐤嗛敍灞筋杻婢堆嗗嚡娴狅絾顐奸弫鐗堝灗鐠嬪啯鏆ｉ弨鑸垫殐鐎圭懓妯?"
        if worst_residual is not None and worst_residual > 1e-1:
            suggestion = "濞堝妯婃潏鍐彯閿涘奔绱崗鍫燁梾閺屻儴绔熼悾?閹恒儴袝/鏉炲€熷祹鐎规矮绠熼敍灞借嫙閸戝繐鐨崚婵嗩潗婢х偤鍣?"
        issues.append(
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="缂佹挻鐎崠鏍ㄦ暪閺佹稒瀵氶弽鍥ㄦ▔缁€鐑樻弓閺€鑸垫殐閹存牗鏁归弫娑㈩棑闂勨晠鐝?",
                location=".sta metrics",
                suggestion=suggestion,
            )
        )
        return _apply_convergence_contradiction_rules(issues, metrics)

    if metrics:
        max_iter = summary.get("max_iterations") or 0
        worst_residual = summary.get("worst_final_residual")
        increasing_count = summary.get("residual_trend_counts", {}).get("increasing", 0)
        if (
            max_iter >= 25
            and worst_residual is not None
            and worst_residual > 1e-2
            and increasing_count > 0
        ):
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="convergence",
                    message="閺€鑸垫殐鐡掑濞嶆稉宥嚽旂€规熬绱版潻顓濆敩濞嗏剝鏆熸潏鍐彯娑撴梹鐣顔芥弓閺勫孩妯夋稉瀣",
                    location=".sta metrics",
                    suggestion="鐏忔繆鐦崙蹇撶毈閸掓繂顫愬銉╂毐閿涘本顥呴弻銉﹀复鐟欙缚绗屾潏鍦櫕閺夆€叉閿涘苯鑻熸径宥嗙壋濮瑰倽袙閹貉冨煑閸欏倹鏆?",
                )
            )

    convergence_tokens = ("converg", "increment", "diverg")
    for file_path, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        file_label = file_path.name
        for idx, line in enumerate(text.splitlines(), 1):
            lowered = line.lower()
            if not lowered.strip():
                continue

            msg: Optional[str] = None
            suggestion: Optional[str] = None

            if "increment size smaller" in lowered:
                msg = "婢х偤鍣哄銉ョ毈娴滃孩娓剁亸蹇撯偓纭风礉閺€鑸垫殐閸ヤ即姣?"
                suggestion = "閸戝繐鐨崚婵嗩潗濮濄儵鏆遍敍?STATIC 妫ｆ牕寮弫甯礆閿涘本鍨ㄩ弨鎯ь啍閺€鑸垫殐鐎圭懓妯?"
            elif "not converged" in lowered or "did not converge" in lowered:
                msg = "鏉╊厺鍞張顏呮暪閺?"
                suggestion = "濡偓閺屻儴娴囬懡閿嬵劄鐠佸墽鐤嗛敍灞筋杻婢堆嗗嚡娴狅絾顐奸弫鐗堝灗鐠嬪啯鏆ｉ弨鑸垫殐鐎圭懓妯?"
            elif "divergence" in lowered:
                msg = "濮瑰倽袙閸欐垶鏆?"
                suggestion = "濡偓閺屻儴绔熼悾灞炬蒋娴犺泛鎷版潪鍊熷祹閺勵垰鎯侀崥鍫㈡倞閿涘苯绻€鐟曚焦妞傞崙蹇撶毈鏉炲€熷祹婢х偤鍣?"
            elif "fatal error" in lowered and any(token in lowered for token in convergence_tokens):
                msg = "濮瑰倽袙閸ｃ劍濮ら崨濠冩暪閺佹稓娴夐崗瀹犲毀閸涗粙鏁婄拠?"
                suggestion = "濡偓閺屻儴绔熼悾灞炬蒋娴犺翰鈧焦甯寸憴锕€鎷版潪鍊熷祹鐎规矮绠熼敍灞借嫙婢跺秵鐗虫晶鐐哄櫤閹貉冨煑"

            if msg and suggestion:
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="convergence",
                        message=msg,
                        location=f"{file_label}:{idx}",
                        suggestion=suggestion,
                    )
                )
                break

    return _apply_convergence_contradiction_rules(issues, metrics)


def _check_solver_run_status(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    summary = _get_solver_run_summary(results_dir, ctx=ctx)
    solver = str(summary.get("solver") or "unknown")
    status = str(summary.get("status") or "unknown").lower()
    reason = str(summary.get("status_reason") or "").strip()
    location = summary.get("primary_log")

    if solver in {"unknown", "calculix"}:
        return []

    if status == "failed":
        message = reason or f"{solver} runtime failed before producing a valid solution."
        return [
            DiagnosticIssue(
                severity="error",
                category="solver_runtime",
                message=message,
                location=location,
                suggestion=(
                    f"Inspect {location or 'the runtime log'} and repair solver inputs, "
                    "environment, or container command before trusting the outputs."
                ),
            )
        ]

    if status == "not_converged":
        message = reason or f"{solver} finished without reaching its convergence target."
        return [
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message=message,
                location=location,
                suggestion=(
                    f"Review {location or 'the convergence log'}, then adjust iteration limits, "
                    "time-step controls, or initialization before re-running."
                ),
            )
        ]

    return []


def _check_time_increment_stagnation(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲妞傞梻鏉戭杻闁插繐浠犲鐑囩窗鏉╃偟鐢?娑擃亜顤冮柌蹇旑劄 INC TIME 娑撳秴顤冩径褋鈧?

    閹殿偅寮?.sta 閸?.stderr 閺傚洣娆㈤敍宀冃掗弸?"increment size=" 濡€崇础閿?
    鏉╃偟鐢?娑擃亜顤冮柌蹇旑劄閻ㄥ嫭妞傞梻鏉戭杻闁插繑鐥呴張澶婎杻閸旂姴鍨憴锕€褰傜拃锕€鎲￠妴?
    """
    issues: list[DiagnosticIssue] = []

    import re

    for file_path, text in _iter_result_texts(results_dir, ("*.sta", "*.stderr"), ctx=ctx):
        file_label = file_path.name

        # 閸栧綊鍘?"increment size= 1.000000e+00" 閺嶇厧绱?
        inc_times: list[float] = []
        for line in text.splitlines():
            match = re.search(r"increment\s+size=\s*([0-9eE.+\-]+)", line)
            if match:
                try:
                    val = float(match.group(1))
                    inc_times.append(val)
                except ValueError:
                    pass

        # 濡偓閺屻儴绻涚紒?娑擃亜顤冮柌蹇旀Ц閸氾箑浠犲?
        if len(inc_times) >= 5:
            stagnant_count = 0
            for i in range(1, len(inc_times)):
                if inc_times[i] <= inc_times[i - 1]:
                    stagnant_count += 1
                else:
                    stagnant_count = 0  # 闁插秶鐤嗙拋鈩冩殶閸?
                if stagnant_count >= 5:
                    issues.append(
                        DiagnosticIssue(
                            severity="warning",
                            category="convergence",
                            message="閺冨爼妫挎晶鐐哄櫤閸嬫粍绮搁敍宀冪箾缂?娑擃亜顤冮柌蹇旑劄 INC TIME 閺堫亜顤冩径?",
                            location=file_label,
                            suggestion="濡偓閺屻儲甯寸憴锕侇啎缂冾喗鍨ㄩ崙蹇撶毈閸掓繂顫愬銉╂毐閿?STATIC 妫ｆ牕寮弫甯礆閵嗗倹甯寸憴锕傛６妫版ê缂撶拋顕嗙窗1) 濡偓閺屻儲甯寸憴锕傛桨鐎规矮绠熼弰顖氭儊濮濓絿鈥?2) 閸戝繐鐨幒銉ㄐ曢崚姘閹晝缍掗崶鐘茬摍閿?SURFACE BEHAVIOR 閻?pressure= 閸欏倹鏆熼敍?) 娴ｈ法鏁?*CONTROLS, PARAMETER=FIELD 鐠嬪啯鏆ｆ潻顓濆敩閸欏倹鏆?",
                        )
                    )
                    break

    return issues


def _check_input_syntax(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺?INP 鏉堟挸鍙嗛弬鍥︽鐠囶厽纭堕敍姘￥閺佸牆宕遍悧鍥╃搼闁挎瑨顕ら妴?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "card image cannot be interpreted"閿涙碍妫ゅ▔鏇＄槕閸掝偆娈戦崡锛勫
    - "unknown keyword"閿涙碍婀惌銉ュ彠闁款喛鐦?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in INVALID_CARD_PATTERNS:
            match = pattern.search(text)
            if match:
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="input_syntax",
                        message="濡偓濞村鍩岄弮鐘虫櫏 INP 閸忔娊鏁拠宥忕礉閸欘垵鍏橀弰顖涘閸愭瑩鏁婄拠顖涘灗閻楀牊婀版稉宥呭悑鐎?",
                        location=stderr_file.name,
                        suggestion="濡偓閺?INP 閺傚洣娆㈡稉顓犳畱閸楋紕澧栭幏鐓庡晸閿涘瞼鈥樻穱婵呯瑢 CalculiX 閺€顖涘瘮閻ㄥ嫬鍙ч柨顔跨槤娑撯偓閼锋番鈧倸鐖剁憴渚€鏁婄拠顖ょ窗閹风厧鍟撻柨娆掝嚖閵嗕礁銇囩亸蹇撳晸娑撳秴灏柊宥冣偓浣风瑝閺€顖涘瘮閻ㄥ嫬宕遍悧鍥ㄧ壐瀵繈鈧?",
                    )
                )
                break  # 濮ｅ繋閲滈弬鍥︽閸欘亝濮ゆ稉鈧▎?

    return issues


def _check_material_definition(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲娼楅弬娆忕暰娑斿鐣弫瀛樷偓褝绱伴弶鎰灐鐏炵偞鈧呭繁婢惰京鐡戦柨娆掝嚖閵?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ礄閺夈儴鍤?CalculiX 濠ф劗鐖滈敍澶涚窗
    - "no elastic constants"閿涙氨宸辩亸鎴濊剨閹冪埗閺?
    - "no density was assigned"閿涙氨宸辩亸鎴濈槕鎼?
    - "no material was assigned"閿涙碍婀崚鍡涘帳閺夋劖鏋?
    - "no specific heat"閿涙氨宸辩亸鎴炵槷閻戭厼顔?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in MATERIAL_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "no elastic" in matched_text:
                    msg = "閺夋劖鏋＄紓鍝勭毌瀵鈧冪埗閺佸府绱橢lastic modulus閿?"
                    suggestion = "閸?*MATERIAL 娑擃厽鍧婇崝?*ELASTIC 閹?*ELASTIC,TYPE=ISOTROPIC 鐎规矮绠熷瑙勨偓褎膩闁?"
                elif "no density" in matched_text:
                    msg = "閺夋劖鏋＄紓鍝勭毌鐎靛棗瀹崇€规矮绠?"
                    suggestion = "閸?*MATERIAL 娑擃厽鍧婇崝?*DENSITY 鐎规矮绠熼弶鎰灐鐎靛棗瀹抽敍鍫濆З閸旀稑顒熼崚鍡樼€借箛鍛存付閿?"
                elif "no material" in matched_text:
                    msg = "閸楁洖鍘撻張顏勫瀻闁板秵娼楅弬娆忕潣閹?"
                    suggestion = (
                        "濡偓閺?*SOLID SECTION 閺勵垰鎯佸锝団€橀崗瀹犱粓娴滃棙娼楅弬娆忔倳缁?"
                    )
                elif "no specific heat" in matched_text:
                    msg = "閺夋劖鏋＄紓鍝勭毌濮ｆ梻鍎圭€圭懓鐣炬稊?"
                    suggestion = "閸?*MATERIAL 娑擃厽鍧婇崝?*SPECIFIC HEAT 鐎规矮绠熷В鏃傚劰鐎圭櫢绱欓悜顓炲瀻閺嬫劕绻€闂団偓閿?"
                elif "no conductivity" in matched_text:
                    msg = "閺夋劖鏋＄紓鍝勭毌閻戭厺绱剁€佃偐閮撮弫?"
                    suggestion = (
                        "閸?*MATERIAL 娑擃厽鍧婇崝?*CONDUCTIVITY 鐎规矮绠熼悜顓濈炊鐎佃偐閮撮弫?"
                    )
                else:
                    msg = "閺夋劖鏋＄仦鐐粹偓褍鐣炬稊澶夌瑝鐎瑰本鏆?"
                    suggestion = "濡偓閺屻儲娼楅弬娆忓幢閻楀洦妲搁崥锕€鐣弫鏉戠暰娑?"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="material",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_parameter_syntax(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱宕遍悧鍥у棘閺佹媽顕㈠▔鏇窗閸欏倹鏆熸稉宥堢槕閸掝偆鐡戦柨娆掝嚖閵?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁?"parameter not recognized" 濡€崇础閵?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        if PARAMETER_PATTERNS[0].search(text):
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    category="input_syntax",
                    message="閸楋紕澧栭崣鍌涙殶娑撳秷顫︾拠鍡楀焼",
                    location=stderr_file.name,
                    suggestion="濡偓閺屻儱宕遍悧鍥у棘閺佺増瀚鹃崘娆愭Ц閸氾附顒滅涵顔衡偓渚癮lculiX 閸欏倹鏆熼崥宥呭隘閸掑棗銇囩亸蹇撳晸閿涘苯鐖剁憴渚€鏁婄拠顖ょ窗PARAMETERS 閼板矂娼?PARAMETER",
                )
            )
            break

    return issues


def _check_load_transfer(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儴娴囬懡铚傜炊闁帡妫舵０姗堢窗鏉炲€熷祹閺堫亝顒滅涵顔荤炊闁帒鍩岀紒鎾寸€妴?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "RHS only consists of 0.0"閿涙俺娴囬懡宄版倻闁插繋璐熼梿璁圭礉闁艾鐖堕弰顖濃偓锕€鎮庣痪锔芥将闁板秶鐤嗛柨娆掝嚖
    - "concentrated loads: 0"閿涙岸娉︽稉顓℃祰閼介攱鏆熼柌蹇庤礋闂?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in LOAD_TRANSFER_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "rhs only consists of 0.0" in matched_text:
                    msg = "鏉炲€熷祹閸氭垿鍣烘稉娲祩閿涘湩HS only consists of 0.0閿涘绱濇潪鍊熷祹閺堫亝顒滅涵顔荤炊闁帒鍩岀紒鎾寸€?"
                    suggestion = (
                        "濡偓閺屻儰浜掓稉瀣讲閼宠棄甯崶鐙呯窗\n"
                        "1) *COUPLING 娑?*DISTRIBUTING 閼辨梻鏁ら弮璁圭礉鏉炲€熷祹韫囧懘銆忔担璺ㄦ暏 *DLOAD 閼板矂娼?*CLOAD\n"
                        "2) 濡偓閺?*COUPLING 閻?REF NODE 閺勵垰鎯佸锝団€樼拋鍓х枂\n"
                        "3) 濡偓閺屻儴鈧箑鎮庣痪锔芥将閻?DOF 閺勵垰鎯佹稉搴ゆ祰閼介攱鏌熼崥鎴滅閼风⒍n"
                        "4) 婵″倹鐏夋担璺ㄦ暏 DISTRIBUTING 閼帮箑鎮庨敍灞炬暭閻?*DLOAD 閸︺劏銆冮棃銏℃煢閸旂姴鍨庣敮鍐祰閼?"
                    )
                else:
                    msg = "闂嗗棔鑵戞潪鍊熷祹閺佷即鍣烘稉娲祩閿涘矁娴囬懡閿嬫弓濮濓絿鈥樼€规矮绠?"
                    suggestion = "濡偓閺?*CLOAD 閹?*DLOAD 閺勵垰鎯佸锝団€橀弬钘夊"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="load_transfer",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_boundary_issues(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儴绔熼悾灞炬蒋娴犲爼妫舵０姗堢窗濞嗙姷瀹抽弶?鏉╁洨瀹抽弶鐔奉嚤閼峰娈戦崚姘秼鏉╂劕濮╅幋鏍ь殞瀵倹鈧佲偓?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "zero pivot"閿涙岸娴傛稉璇插帗閿涘矂鈧艾鐖堕弰顖濈珶閻ｅ本娼禒鏈电瑝鐎瑰本鏆?
    - "singular matrix"閿涙氨鐓╅梼闈涱殞瀵偊绱濆▎鐘靛閺夌喐鍨ㄦ潻鍥╁閺?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in BOUNDARY_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "zero pivot" in matched_text:
                    msg = "濡偓濞村鍩岄梿鏈靛瘜閸忓喛绱檢ero pivot閿涘绱濋崣顖濆厴閺勵垵绔熼悾灞炬蒋娴犳湹绗夌€瑰本鏆?"
                    suggestion = (
                        "濡偓閺屻儰浜掓稉瀣讲閼宠棄甯崶鐙呯窗\n"
                        "1) 缂佹挻鐎弰顖氭儊鐞氼偄鐣崗銊у閺夌噦绱欑亸銈呭従閺冨娴嗛懛顏嗘暠鎼达讣绱歕n"
                        "2) 婢瑰啿宕熼崗鍐╂Ц閸氾附婀佺搾鍐差檮閻ㄥ嫯绔熼悾宀€瀹抽弶鐒卬"
                        "3) 閹恒儴袝闂堛垺妲搁崥锔筋劀绾喖鐣炬稊濉"
                        "4) 閼哄倻鍋ｇ紓鏍у娇閺勵垰鎯佹潻鐐电敾"
                    )
                elif "singular matrix" in matched_text:
                    msg = "閻晠妯€婵傚洤绱撻敍宀€绮ㄩ弸鍕摠閸︺劍鐟虹痪锔芥将閹存牞绻冪痪锔芥将"
                    suggestion = (
                        "濡偓閺屻儴绔熼悾灞炬蒋娴犺绱癨n"
                        "1) 绾喕绻氶幍鈧張澶夌秴缁夎鍨庨柌蹇涘厴鐞氼偆瀹抽弶鐒卬"
                        "2) 濡偓閺屻儲妲搁崥锕€鐡ㄩ崷銊ュ暱缁愪胶娈戞潏鍦櫕閺夆€叉\n"
                        "3) 婢?濮婁胶绮ㄩ弸鍕付鐟曚線娼版径鏍閺?"
                    )
                else:
                    msg = "鏉堝湱鏅弶鈥叉閸欘垵鍏樼€涙ê婀梻顕€顣?"
                    suggestion = "濡偓閺屻儴绔熼悾灞炬蒋娴犺埖妲搁崥锕€鐣弫缈犵瑬閺冪姴鍟跨粣?"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="boundary_condition",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_contact_issues(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲甯寸憴锕傛６妫版﹫绱伴幒銉ㄐ曠€规矮绠熼柨娆掝嚖閵嗕焦甯寸憴锔芥弓閹垫儳鍩岀粵澶堚偓?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ礄婢х偛宸遍懛?calculix_patterns.txt閿涘绱?
    - "contact not found"閿涙碍甯寸憴锕傛桨閺堫亝澹橀崚?
    - "overclosure"閿涙俺绻冮惄鍫ュ櫤鏉╁洤銇?
    - "contact stress negative"閿涙碍甯寸憴锕€绨查崝娑楄礋鐠?
    - "slave/master surface"閿涙矮瀵屾禒搴ㄦ桨闂傤噣顣?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in CONTACT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "contact" in matched_text and "not" in matched_text and "found" in matched_text:
                    msg = "閹恒儴袝闂堛垺婀幍鎯у煂閿涘本甯寸憴锕€鐣炬稊澶婂讲閼充粙鏁婄拠?"
                    suggestion = (
                        "濡偓閺屻儰浜掓稉瀣讲閼宠棄甯崶鐙呯窗\n"
                        "1) 娑撹绮犻棃銏℃Ц閸氾附顒滅涵顔款啎缂冪敍n"
                        "2) 閹恒儴袝闂堫澀绠ｉ梻瀛樻Ц閸氾附婀侀崚婵嗩潗闂傛挳娈璡n"
                        "3) 閹恒儴袝闂堛垼濡悙瑙勬Ц閸氾箑婀崥灞肩娴ｅ秶鐤哱n"
                        "4) 閹恒儴袝闂堛垺纭堕崥鎴炴煙閸氭垶妲搁崥锔筋劀绾?"
                    )
                elif "overclosure" in matched_text:
                    msg = "閹恒儴袝鏉╁洨娉╅柌蹇氱箖婢?"
                    suggestion = "濡偓閺屻儱鍨垫慨瀣殤娴ｆ洑缍呯純顕嗙礉绾喕绻氶幒銉ㄐ曢棃顫闂傚瓨鐥呴張澶庣箖婢堆呮畱鏉╁洨娉╅柌?"
                elif "contact stress" in matched_text and "negative" in matched_text:
                    msg = "閹恒儴袝鎼存柨濮忔稉楦跨閿涘苯褰查懗钘夌摠閸︺劎鈹涢柅蹇涙６妫?"
                    suggestion = "濡偓閺屻儲甯寸憴锕€鍨版惔锕侇啎缂冾喖鎷伴崚婵嗩潗闂傛挳娈?"
                elif "slave surface" in matched_text or "master surface" in matched_text:
                    msg = "閹恒儴袝娑撹绮犻棃銏犵暰娑斿鐡ㄩ崷銊╂６妫?"
                    suggestion = "濡偓閺?*CONTACT PAIR 娑?SLAVE 閸?MASTER 闂堛垻娈戠拋鍓х枂閺勵垰鎯佸锝団€?"
                elif "slave node" in matched_text:
                    msg = "閹恒儴袝娴犲氦濡悙鐟扮暰娑斿鐡ㄩ崷銊╂６妫?"
                    suggestion = "濡偓閺屻儲甯寸憴锔跨矤閼哄倻鍋ｉ惃鍕偓澶婂絿閺勵垰鎯佸锝団€?"
                elif "no tied" in matched_text or "tied mpc" in matched_text:
                    msg = "閹恒儴袝缂佹垵鐣?缁ɑ甯撮梻顕€顣?"
                    suggestion = "濡偓閺?*TIE 閸涙垝鎶ら惃鍕拨鐎规岸娼扮拋鍓х枂"
                else:
                    msg = "閹恒儴袝鐎规矮绠熼崣顖濆厴鐎涙ê婀梻顕€顣?"
                    suggestion = "濡偓閺?*CONTACT PAIR 閻ㄥ嫪瀵屾禒搴ㄦ桨鐠佸墽鐤嗛崪?*SURFACE INTERACTION 閸欏倹鏆?"
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="contact",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_file_io_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲鏋冩禒?I/O 闁挎瑨顕ら敍鍫熸降閼?CalculiX 濠ф劗鐖?528 濡€崇础閿涘鈧?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "could not open file"閿涙碍鏋冩禒鑸靛ⅵ瀵偓婢惰精瑙?
    - "file name is lacking"閿涙碍鏋冩禒璺烘倳缂傚搫銇?
    - "file name too long"閿涙碍鏋冩禒璺烘倳鏉╁洭鏆?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in FILE_IO_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "could not open file" in matched_text:
                    msg = "閺傚洣娆㈤幍鎾崇磻婢惰精瑙?"
                    suggestion = "濡偓閺?INP 閺傚洣娆㈢捄顖氱窞閺勵垰鎯佸锝団€橀敍宀€鈥樻穱婵囨瀮娴犺泛鐡ㄩ崷銊ょ瑬閺堝顕伴崣鏍ㄦ綀闂?"
                elif "could not open" in matched_text:
                    msg = "閺傚洣娆㈤幍鎾崇磻婢惰精瑙?"
                    suggestion = "濡偓閺屻儲鏋冩禒璺烘倳閸滃矁鐭惧鍕Ц閸氾附顒滅涵?"
                elif "file name is lacking" in matched_text:
                    msg = "閺傚洣娆㈤崥宥囧繁婢?"
                    suggestion = (
                        "濡偓閺?INP 閺傚洣娆㈡稉顓熸Ц閸氾妇宸辩亸鎴ｇ翻閸忋儲鏋冩禒璺烘倳缁?"
                    )
                elif (
                    "file name too long" in matched_text
                    or "input file name is too long" in matched_text
                ):
                    msg = "閺傚洣娆㈤崥宥堢箖闂€?"
                    suggestion = "缂傗晝鐓潏鎾冲弳閺傚洣娆㈤惃鍕熅瀵板嫭鍨ㄩ弬鍥︽閸氬稄绱滳alculiX 鐎佃鏋冩禒璺烘倳闂€鍨閺堝妾洪崚?"
                elif "could not delete" in matched_text:
                    msg = "閺傚洣娆㈤崚鐘绘珟婢惰精瑙?"
                    suggestion = "濡偓閺屻儲鏋冩禒鑸垫Ц閸氾箒顫﹂崗鏈电铂缁嬪绨崡鐘垫暏閿涘本鍨ㄩ弰顖氭儊閺堝鍟撻崗銉︽綀闂?"
                elif "syntax error" in matched_text:
                    msg = "鏉堟挸鍙嗛弬鍥︽鐠囶厽纭堕柨娆掝嚖"
                    suggestion = "濡偓閺?INP 閺傚洣娆㈤弽鐓庣础閺勵垰鎯佸锝団€橀敍宀€鈥樻穱婵嗗幢閻楀洩顕㈠▔鏇狀儊閸?CalculiX 鐟欏嫯瀵?"
                else:
                    msg = "閺傚洣娆?I/O 闁挎瑨顕?"
                    suggestion = "濡偓閺屻儴绶崗銉ㄧ翻閸戠儤鏋冩禒鎯扮熅瀵板嫬鎷伴弶鍐"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="file_io",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_user_element_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儳鏁ら幋宄板礋閸?閺夋劖鏋￠柨娆掝嚖閿涘牊娼甸懛?CalculiX 濠ф劗鐖滈敍澶堚偓?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "user element"閿涙氨鏁ら幋宄板礋閸忓啴妫舵０?
    - "umat"閿涙氨鏁ら幋閿嬫綏閺傛瑥鐡欑粙瀣碍闂傤噣顣?
    - "user subroutine"閿涙氨鏁ら幋宄扮摍缁嬪绨梻顕€顣?
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in USER_ELEMENT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if (
                    "no user material" in matched_text
                    or "umat" in matched_text
                    and "no" in matched_text
                ):
                    msg = "閻劍鍩涢弶鎰灐鐎涙劗鈻兼惔蹇ョ礄UMAT閿涘婀幍鎯у煂"
                    suggestion = "绾喕绻?*USER MATERIAL 鐎涙劗鈻兼惔蹇撳嚒濮濓絿鈥樼紓鏍槯楠炲爼鎽奸幒銉礉閹存牔濞囬悽銊︾垼閸戝棙娼楅弬娆惸侀崹?"
                elif "user element" in matched_text:
                    msg = "閻劍鍩涢崡鏇炲帗閿涘湶ELS閿涘鐡ㄩ崷銊╂６妫?"
                    suggestion = "濡偓閺屻儳鏁ら幋宄板礋閸忓啫鐡欑粙瀣碍閺勵垰鎯佸锝団€樼€圭偟骞囬崪宀勬懠閹?"
                elif "umat" in matched_text:
                    msg = "閻劍鍩涢弶鎰灐鐎涙劗鈻兼惔蹇ョ礄UMAT閿涘鐡ㄩ崷銊╂６妫?"
                    suggestion = "濡偓閺?UMAT 鐎涙劗鈻兼惔蹇曟畱鏉堟挸鍙嗛崣鍌涙殶閸滃本娼楅弬娆忓棘閺佺増妲搁崥锔筋劀绾?"
                else:
                    msg = "閻劍鍩涚€涙劗鈻兼惔蹇撶摠閸︺劑妫舵０?"
                    suggestion = "濡偓閺屻儳鏁ら幋鐤殰鐎规矮绠熺€涙劗鈻兼惔蹇旀Ц閸氾附顒滅涵顔剧椽鐠囨垵鎷伴柧鐐复"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="user_element",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_mpc_limits(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺?MPC/缁撅附娼弫浼村櫤鐡掑懘妾洪柨娆掝嚖閿涘牊娼甸懛?CalculiX 濠ф劗鐖滈敍澶堚偓?

    閹殿偅寮?.stderr 閺傚洣娆㈤敍灞藉爱闁板秳浜掓稉瀣佸蹇ョ窗
    - "increase nmpc_"閿涙瓉PC 閺佷即鍣虹搾鍛存
    - "increase nboun_"閿涙俺绔熼悾灞炬蒋娴犺埖鏆熼柌蹇氱Т闂?
    - "increase nk_"閿涙俺濡悙瑙勬殶闁插繗绉撮梽?
    - "increase memmpc_"閿涙瓉PC 閸愬懎鐡ㄧ搾鍛存
    """
    issues: list[DiagnosticIssue] = []

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        for pattern in MPC_LIMIT_PATTERNS:
            match = pattern.search(text)
            if match:
                matched_text = match.group(0).lower()
                if "nmpc" in matched_text:
                    msg = "MPC閿涘牆顦块悙鍦閺夌噦绱氶弫浼村櫤鐡掑懘妾?"
                    suggestion = "閸戝繐鐨Ο鈥崇€锋稉顓犳畱 MPC 閺佷即鍣洪敍灞惧灗閸?*MPCACABLE 閸欏倹鏆熸稉顓烆杻閸旂娀妾洪崚璺衡偓?"
                elif "nboun" in matched_text:
                    msg = "鏉堝湱鏅弶鈥叉閺佷即鍣虹搾鍛存"
                    suggestion = "缁犫偓閸栨牞绔熼悾灞炬蒋娴犺泛鐣炬稊澶涚礉閸戝繐鐨潏鍦櫕閺夆€叉閺佷即鍣?"
                elif "nk" in matched_text:
                    msg = "閼哄倻鍋ｉ弫浼村櫤鐡掑懘妾?"
                    suggestion = "濡偓閺屻儳缍夐弽鑹板Ν閻愬湱绱崣閿嬫Ц閸氾箑鎮庨悶鍡礉绾喕绻氶懞鍌滃仯閺佷即鍣洪崷銊ュ帒鐠佹瓕瀵栭崶鏉戝敶"
                elif "memmpc" in matched_text:
                    msg = "MPC 閸愬懎鐡ㄩ崚鍡涘帳鐡掑懘妾?"
                    suggestion = "閸戝繐鐨径宥嗘絽 MPC 缁撅附娼敍灞惧灗婢х偛濮?*MPCABLE 閻?MEMMPCC 閸欏倹鏆?"
                elif "nbody" in matched_text:
                    msg = "娴ｆ挾袧鏉炲€熷祹閺佷即鍣虹搾鍛存"
                    suggestion = "閸戝繐鐨?*DLOAD 鐎规矮绠熼惃鍕秼缁夘垵娴囬懡閿嬫殶闁?"
                elif "nforc" in matched_text:
                    msg = "闂嗗棔鑵戦崝娑欐殶闁插繗绉撮梽?"
                    suggestion = "閸戝繐鐨?*CLOAD 鐎规矮绠熼惃鍕肠娑擃厼濮忛弫浼村櫤"
                elif "nload" in matched_text:
                    msg = "鏉炲€熷祹閺佷即鍣虹搾鍛存"
                    suggestion = "閸戝繐鐨潪鍊熷祹鐎规矮绠熼弫浼村櫤閿涘本鍨ㄩ崥鍫濊嫙鏉炲€熷祹"
                elif "norien" in matched_text:
                    msg = "閺傜懓鎮滅€规矮绠熼弫浼村櫤鐡掑懘妾?"
                    suggestion = "閸戝繐鐨?*ORIENTATION 鐎规矮绠熼弫浼村櫤"
                elif "namtot" in matched_text:
                    msg = "閹槒濡悙?閸楁洖鍘撶仦鐐粹偓褎鏆熼柌蹇氱Т闂?"
                    suggestion = (
                        "缁犫偓閸栨牗膩閸ㄥ绱濋崙蹇撶毌閼哄倻鍋ｉ梿鍡楁嫲閸楁洖鍘撻梿鍡樻殶闁?"
                    )
                elif "nprint" in matched_text:
                    msg = "鏉堟挸鍤拠閿嬬湴閺佷即鍣虹搾鍛存"
                    suggestion = "閸戝繐鐨?*NODE PRINT 閹?*EL PRINT 閻ㄥ嫯绶崙鍝勫綁闁插繑鏆熼柌?"
                elif "dimension" in matched_text:
                    msg = "濡€崇€风紒鏉戝閹存牜缍夐弽鐓庢槀鐎垫瓕绉撮梽?"
                    suggestion = (
                        "濡偓閺屻儳缍夐弽鐓庢槀鐎靛憡妲搁崥锕€鎮庨悶鍡礉閸戝繐鐨Ο鈥崇€风憴鍕?"
                    )
                else:
                    msg = "閸愬懎鐡ㄩ幋鏍ㄦ殶闁插繗绉撮梽?"
                    suggestion = "缁犫偓閸栨牗膩閸ㄥ鍨ㄦ晶鐐插閸愬懎鐡ㄩ梽鎰煑閸欏倹鏆?"
                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="limit_exceeded",
                        message=msg,
                        location=stderr_file.name,
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_dynamics_errors(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱濮╅崝娑橆劅/濡剝鈧礁鍨庨弸鎰版晩鐠囶垽绱欓弶銉ㄥ殰 CalculiX 濠ф劗鐖滃Ο鈥崇础閿涘鈧?
    娑撴椽妾锋担搴ゎ嚖閹躲儻绱濇禒鍛躬閳ユ粓鏁婄拠顖濐嚔婢у啠鈧繀绗呯憴锕€褰傞敍?    - eigenvalue 鐞涘苯绻€妞よ瀵橀崥?error/failed/cannot/not/invalid 娑斿绔?
    - cyclic symmetric 鐞涘苯绻€妞よ瀵橀崥顐︽晩鐠囶垵顕㈡晶?    - frequencies less than 1 eigenvalue 閻╁瓨甯撮崚銈呯暰
    - alpha is greater/smaller 閻╁瓨甯撮崚銈呯暰
    """
    issues: list[DiagnosticIssue] = []
    error_tokens = ("error", "failed", "cannot", "not", "invalid")

    for stderr_file, text in _iter_result_texts(results_dir, ("*.stderr",), ctx=ctx):
        lines = text.splitlines()
        for idx, line in enumerate(lines, 1):
            lowered = line.lower()
            if not lowered.strip():
                continue

            msg: Optional[str] = None
            suggestion: Optional[str] = None

            if "frequencies" in lowered and "less than 1 eigenvalue" in lowered:
                msg = "閻楃懓绶涢崐鍏兼殶闁插繋绗夌搾?"
                suggestion = "濡偓閺屻儲妲搁崥锔藉閺堝顣堕悳鍥厴娑撴椽娴傞敍鍫濆灠娴ｆ挻膩閹緤绱氶敍宀€鈥樻穱婵婄珶閻ｅ本娼禒鑸殿劀绾?"
            elif "eigenvalue" in lowered and any(token in lowered for token in error_tokens):
                msg = "閻楃懓绶涢崐鍏肩湴鐟欙絽銇戠拹?"
                suggestion = "濡偓閺屻儲膩閹礁鍨庨弸鎰棘閺佸府绱濈涵顔荤箽缂佹挻鐎張澶庡喕婢剁喓娈戠痪锔芥将"
            elif "cyclic symmetric" in lowered and any(token in lowered for token in error_tokens):
                msg = "瀵邦亞骞嗙€靛湱袨閸掑棙鐎界€涙ê婀梻顕€顣?"
                suggestion = (
                    "濡偓閺屻儱鎯婇悳顖氼嚠缁夋媽绔熼悾灞炬蒋娴犺埖妲搁崥锔筋劀绾喛顔曠純?"
                )
            elif "alpha is greater" in lowered or "alpha is smaller" in lowered:
                msg = "閸斻劌濮忕€涳附妞傞梻瀵感濋崚鍡楀棘閺?alpha 娑撳秴鎮庨悶?"
                suggestion = "濡偓閺?*DYNAMIC 濮濄儵顎冮惃?alpha 閸欏倹鏆熼敍鍫熷腹閼芥劕鈧》绱?0.05 閸?-0.3閿?"

            if msg and suggestion:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="dynamics",
                        message=msg,
                        location=f"{stderr_file.name}:{idx}",
                        suggestion=suggestion,
                    )
                )
                break

    return issues


def _check_inp_file_quality(
    inp_file: Optional[Path],
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    閻╁瓨甯撮幍顐ｅ伎 INP 閺傚洣娆㈤敍灞绢梾濞村顫﹀▔銊╁櫞閻ㄥ嫬鍙ч柨顔煎幢閻楀洤鎷扮敮姝岊潌闁挎瑨顕ら妴?

    濡偓濞村浜掓稉瀣６妫版﹫绱?
    - 鐞氼偅鏁為柌濠勬畱 *SURFACE BEHAVIOR閿涘牊甯寸憴锕侇攽娑撹櫣宸辨径鎲嬬礆
    - 鐞氼偅鏁為柌濠勬畱 *ELASTIC閿涘牆鑴婇幀褍鐖堕弫鎵繁婢舵唻绱?
    - 鐞氼偅鏁為柌濠勬畱 *MATERIAL閿涘牊娼楅弬娆忕暰娑斿宸辨径鎲嬬礆
    - 缂傚搫鐨?*SOLID SECTION 閻ㄥ嫭娼楅弬娆忓彠閼?
    - 缂傚搫鐨?*BOUNDARY 鏉堝湱鏅弶鈥叉
    - 缂傚搫鐨?*STEP 閸掑棙鐎藉?
    - 鏉炲€熷祹閺傝棄濮炴担宥囩枂闁挎瑨顕ら敍鍫ｆ祰閼藉嘲婀?*STEP 娑斿澧犻敍?
    """
    issues: list[DiagnosticIssue] = []

    if not inp_file or not inp_file.exists():
        return issues

    lines = _get_inp_lines(inp_file, ctx=ctx)
    if not lines:
        return issues

    # 閺€鍫曟肠閹碘偓閺堝鍙ч柨顔肩摟閿涘牆瀵橀崥顐ｆ暈闁插﹨顢戦敍?
    all_keywords: set[str] = set()
    active_keywords: set[str] = set()
    commented_keywords: set[str] = set()

    # 閸忔娊鏁€涙顢戦崣鍑ょ礄閻劋绨€规矮缍呴敍?
    keyword_lines: dict[str, list[int]] = {}

    i = 0
    while i < len(lines):
        raw_line = lines[i].strip()

        # 鐠哄疇绻冪粚楦款攽閿涘牆娼″▔銊╁櫞鐞?** 鐟曚胶鎴风紒顓烆槱閻炲棴绱濋悽銊ょ艾閺嶅洩顔囩悮顐ｆ暈闁插﹦娈戦崗鎶芥暛鐎涙绱?
        if not raw_line:
            i += 1
            continue

        # 鐞涘苯鍞村▔銊╁櫞閿涙艾褰?# 閸撳秶娈戦柈銊ュ瀻
        line = raw_line.split("#")[0].strip()

        # 閸掋倖鏌囬弰顖氭儊閺勵垰娼″▔銊╁櫞閿?* 瀵偓婢惰揪绱?
        is_block_comment = raw_line.startswith("**")

        # 閸栧綊鍘ら崗鎶芥暛鐎涙顢戦敍?瀵偓婢惰揪绱氶敍灞惧絹閸欐牗妲﹂崣宄版倵閵嗕線鈧褰块崜宥囨畱鐎瑰本鏆ｉ崗鎶芥暛鐎?
        # 閺€顖涘瘮婢舵艾宕熺拠宥呭彠闁款喖鐡ф俊?SURFACE BEHAVIOR閵嗕府ATERIAL DEFORMATION 缁?
        # 鐎甸€涚艾閸ф鏁為柌濠咁攽閿?*閿涘绱濋崗鍫濆箵闂?** 閸撳秶绱戦崘宥呭爱闁?
        match_line = line
        if is_block_comment:
            # **KEYWORD 閹?** KEYWORD 瑜般垹绱￠敍宀€绮烘稉鈧崢濠氭珟 ** 閸撳秶绱?
            match_line = re.sub(r"^\*\*\s*", "*", line, count=1)

        keyword_match = re.match(r"^\*([A-Za-z]+(?:[\s][A-Za-z]+)*)", match_line, re.IGNORECASE)
        if keyword_match:
            kw = keyword_match.group(1).upper()
            all_keywords.add(kw)
            if kw not in keyword_lines:
                keyword_lines[kw] = []
            keyword_lines[kw].append(i + 1)  # 鐞涘苯褰挎禒?瀵偓婵?

            # ** 瀵偓婢跺瓨妲搁崸妤佹暈闁插绱濋弽鍥唶娑撻缚顫﹀▔銊╁櫞
            if is_block_comment:
                commented_keywords.add(kw)
            else:
                # 閺堝鏅ラ崗鎶芥暛鐎涙绱欓張顏囶潶濞夈劑鍣撮敍?
                active_keywords.add(kw)

        i += 1

    # ===== 濡偓閺?閿涙俺顫﹀▔銊╁櫞閻ㄥ嫬鍙ч柨顔芥綏閺傛瑥宕遍悧?=====
    critical_cards = {
        "ELASTIC": (
            "*ELASTIC card is missing or commented out.",
            "Add a valid *MATERIAL / *ELASTIC definition and verify units.",
        ),
        "SURFACE BEHAVIOR": (
            "*SURFACE BEHAVIOR card is missing or commented out.",
            "Define *SURFACE BEHAVIOR with pressure-overclosure settings.",
        ),
        "DENSITY": (
            "*DENSITY card is missing or commented out.",
            "Add *DENSITY under the corresponding *MATERIAL block.",
        ),
    }

    for kw, (msg, suggestion) in critical_cards.items():
        if kw in commented_keywords:
            line_nums = keyword_lines.get(kw, ["?"])
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="material",
                    message=msg,
                    location=f"{inp_file.name} line {line_nums[0]}",
                    suggestion=suggestion,
                )
            )

    # ===== 濡偓閺?閿涙氨宸辩亸?*SOLID SECTION閿涘牊娼楅弬娆愭弓閸忓疇浠堥崚鏉垮礋閸忓喛绱?=====
    if "ELASTIC" in active_keywords and "SOLID SECTION" not in active_keywords:
        issues.append(
            DiagnosticIssue(
                severity="warning",
                category="material",
                message="Material definition exists but no *SOLID SECTION card was found.",
                location=inp_file.name,
                suggestion="Add a *SOLID SECTION card that references the element set and material name.",
            )
        )

    # ===== 濡偓閺?閿涙氨宸辩亸鎴ｇ珶閻ｅ本娼禒?=====
    if "BOUNDARY" not in active_keywords and "BOUNDARY" not in commented_keywords:
        issues.append(
            DiagnosticIssue(
                severity="error",
                category="boundary_condition",
                message="INP file does not contain an active *BOUNDARY card.",
                location=inp_file.name,
                suggestion="Add appropriate constraints with *BOUNDARY to remove rigid body motion before solving.",
            )
        )

    # ===== 濡偓閺?閿涙氨宸辩亸鎴濆瀻閺嬫劖顒?=====
    if "STEP" not in active_keywords and "STEP" not in commented_keywords:
        issues.append(
            DiagnosticIssue(
                severity="error",
                category="input_syntax",
                message="INP file does not contain an active *STEP card.",
                location=inp_file.name,
                suggestion="Add a valid analysis step, for example *STEP followed by *STATIC and a matching *END STEP.",
            )
        )
    else:
        active_step_count = sum(1 for line in lines if line.strip().upper().startswith("*STEP"))
        active_end_step_count = sum(
            1 for line in lines if line.strip().upper().startswith("*END STEP")
        )
        if active_step_count > active_end_step_count:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    category="input_syntax",
                    message=(
                        f"*STEP block is not closed: found {active_step_count} *STEP "
                        f"but only {active_end_step_count} *END STEP"
                    ),
                    location=inp_file.name,
                    suggestion="Ensure each *STEP has a matching *END STEP; append missing *END STEP at file end.",
                )
            )

    # ===== 载荷/边界条件应位于分析步内 =====
    step_line = None
    load_keywords = {"CLOAD", "DLOAD", "DFLUX", "CFLUX", "BOUNDARY"}
    for kw, lines_list in keyword_lines.items():
        if kw in load_keywords and not any(kw in c for c in commented_keywords):
            if step_line is None:
                step_lines = keyword_lines.get("STEP", [float("inf")])
                first_step = step_lines[0] if step_lines else float("inf")
                if lines_list[0] < first_step:
                    issues.append(
                        DiagnosticIssue(
                            severity="warning",
                            category="input_syntax",
                            message=f"{kw} appears before the first *STEP block.",
                            location=f"{inp_file.name}: line {lines_list[0]}",
                            suggestion=(
                                "Move loads and boundary conditions into a valid "
                                "*STEP ... *END STEP block, or confirm they are intended as model-level data."
                            ),
                        )
                    )
                    break

    return issues


def _check_element_quality(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱宕熼崗鍐窛闁插骏绱癑acobian 鐠愮喎鈧鈧笭ourglass 缁涘妫舵０妯糕偓?

    閹殿偅寮?.sta / .dat / .cvg 閺傚洣娆㈤敍灞煎▏閻劍顒滈崚娆忓爱闁板秳浜掓稉瀣佸蹇ョ窗
    - NEGATIVE JACOBIAN閿涙艾宕熼崗鍐倳鏉烆剚鍨ㄩ悾绋胯埌
    - HOURGLASSING閿涙艾鍣虹紓鈺冃濋崚鍡楀礋閸忓啰娈戦梿鎯板厴濡€崇础
    - HOURGLIM閿涙碍鐭欏蹇斿付閸掕泛寮弫?
    - *ERROR.*element閿涙艾鍘撶槐鐘垫祲閸忔娊鏁婄拠?
    """
    issues: list[DiagnosticIssue] = []

    for file_path, text in _iter_result_texts(results_dir, ("*.sta", "*.dat", "*.cvg"), ctx=ctx):
        file_label = file_path.name

        for pattern in JACOBIAN_PATTERNS:
            match = pattern.search(text)
            if match:
                # 閺嶈宓侀崠褰掑帳閸掓壆娈戦崗鎶芥暛鐠囧秶鈥樼€规艾鍙挎担鎾绘６妫版琚崹?
                matched_text = match.group(0).lower()
                if "negative jacobian" in matched_text:
                    issue_type = "Jacobian 鐠愮喎鈧?"
                    suggestion = "濡偓閺屻儳缍夐弽鑹板窛闁插骏绱濋悾绋胯埌閸楁洖鍘撴导姘嚤閼?Jacobian 鐠愮喎鈧鈧倸鐨剧拠鏇窗1) 閸旂姴鐦戠純鎴炵壐 2) 閺€鐟版澖閸楁洖鍘撹ぐ銏㈠Ц 3) 娴ｈ法鏁ら崗銊濋崚鍡楀礋閸忓啯娴涙禒锝呭櫤缂傗晝袧閸?"
                elif "hourglassing" in matched_text:
                    issue_type = "Hourglass 濡€崇础"
                    suggestion = "濡偓濞村鍩屽▽娆愮础/闂嗘儼鍏樺Ο鈥崇础閵嗗倽袙閸愮绱?) 閸旂姴鐦戠純鎴炵壐 2) 娴ｈ法鏁ら崗銊濋崚鍡楀礋閸忓喛绱欐俊?C3D8 閼板矂娼?C3D8R閿?) 鐠嬪啯鏆?HOURGLIM 閸欏倹鏆?"
                elif "hourlim" in matched_text:
                    issue_type = "Hourglass 閹貉冨煑"
                    suggestion = "濞屾瑦绱￠幒褍鍩楅崣鍌涙殶瀵倸鐖堕妴鍌涱梾閺屻儻绱?) 缂冩垶鐗搁弰顖氭儊婢额亞鐭?2) 閺勵垰鎯佹担璺ㄦ暏娴滃棗鍣虹紓鈺冃濋崚鍡楀礋閸?"
                else:
                    issue_type = "閸楁洖鍘撻柨娆掝嚖"
                    suggestion = "濡偓濞村鍩岄崗鍐閻╃鍙ч柨娆掝嚖閵嗗倹顥呴弻銉х秹閺嶈壈宸濋柌蹇撴嫲閸楁洖鍘撶猾璇茬€风拋鍓х枂"

                issues.append(
                    DiagnosticIssue(
                        severity="error",
                        category="element_quality",
                        message=f"Detected element quality issue: {issue_type}",
                        location=file_label,
                        suggestion=suggestion,
                    )
                )
                break  # 濮ｅ繋閲滈弬鍥︽閸欘亝濮ゆ稉鈧▎?

    return issues


def _check_frd_quality(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """濡偓閺屻儳缍夐弽鑹板窛闁插骏绱欓柅姘崇箖 FrdData 缂佺喕顓搁幒銊︽焽閿涘鈧?"""
    issues: list[DiagnosticIssue] = []

    try:
        summary = _get_frd_summary(results_dir, ctx=ctx)
        if summary is None:
            return issues

        if summary.node_count > 0 and summary.element_count > 0:
            ratio = summary.node_count / summary.element_count
            if ratio < 0.5:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="mesh_quality",
                        message=f"閼哄倻鍋?閸楁洖鍘撳В鏂剧伐鏉╁洣缍?({ratio:.2f})閿涘苯褰查懗钘夌摠閸︺劋缍嗙拹銊╁櫤閸楁洖鍘?",
                        suggestion="濡偓閺屻儳缍夐弽鐓庡灊閸掑棗寮弫甯礉绾喕绻氬▽鈩冩箒閻ｇ鑸伴崡鏇炲帗",
                    )
                )
            elif ratio > 50:
                issues.append(
                    DiagnosticIssue(
                        severity="info",
                        category="mesh_quality",
                        message=f"閼哄倻鍋?閸楁洖鍘撳В鏂剧伐鏉堝啴鐝?({ratio:.2f})",
                        suggestion="閼板啳妾婚崝鐘茬槕缂冩垶鐗告禒銉﹀絹妤傛绨挎惔?",
                    )
                )

        if summary.disp_count > 0 and summary.disp_sum > 0:
            mean_disp = summary.disp_sum / summary.disp_count
            max_disp = summary.max_displacement
            if max_disp > 0 and mean_disp > 0 and max_disp / mean_disp > 100:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="mesh_quality",
                        message=f"娴ｅ秶些閸掑棗绔烽弸浣风瑝閸у洤瀵戦敍灞炬付婢?楠炲啿娼?= {max_disp / mean_disp:.1f}x",
                        suggestion="閸欘垵鍏樼€涙ê婀惔鏂垮闂嗗棔鑵戦幋鏍珶閻ｅ本娼禒鍫曟晩鐠?",
                    )
                )

    except Exception:
        pass

    return issues


def _check_stress_gradient(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """濡偓閺屻儱绨查崝娑㈡肠娑擃叏绱版惔鏂垮濮婎垰瀹崇粣浣稿綁 > 50x閵?"""
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
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="stress_concentration",
                        message="鎼存柨濮忓顖氬閺嬩礁銇囬敍鍫濇▕瀵?> 50x閿涘绱濋崣顖濆厴鐎涙ê婀惔鏂垮闂嗗棔鑵?",
                        suggestion="閸︺劌绨查崝娑㈡肠娑擃厼灏崺鐔峰鐎靛棛缍夐弽纭风礉閹存牔绱崠鏍у殤娴ｆ洖鑸伴悩?",
                    )
                )

    except Exception:
        pass

    return issues


def _check_displacement_range(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """濡偓閺屻儰缍呯粔鏄忓瘱閸ヨ揪绱伴張鈧径褌缍呯粔?> 濡€崇€风亸鍝勵嚟 10%閵?"""
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues

        max_disp = stats["max_displacement"]
        bx, by, bz = stats["model_bounds"]
        model_size = max(bx, by, bz)

        # 閺佹澘鈧吋瀛╅崙鐑橆梾濞村绱版担宥囆?> 1e10 閺勵垱鐪扮憴锝嗘弓閺€鑸垫殐閻ㄥ嫭鐖ｈ箛?
        if max_disp > 1e10:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    category="displacement",
                    message=f"閺堚偓婢堆傜秴缁夎绱撶敮绋挎硶婢堆嶇礄{max_disp:.2e}閿涘绱濋悿鎴滄妧閺佹澘鈧吋瀛╅崙?",
                    suggestion="濮瑰倽袙閸欘垵鍏橀張顏呮暪閺佹稏鈧倹顥呴弻銉窗1) 閹恒儴袝鐠佸墽鐤嗛弰顖氭儊濮濓絿鈥?2) 鏉炲€熷祹濮濄儲妲搁崥锕€鎮庨悶?3) 缂冩垶鐗搁弰顖氭儊鏉╁洣绨悾绋胯埌",
                )
            )
            return issues  # 閺佹澘鈧吋瀛╅崙铏规畱閹懎鍠屾稉瀣╃瑝缂佈呯敾閸掋倖鏌囬崚姘闂傤噣顣?

        if model_size > 0 and max_disp / model_size > 0.1:
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="displacement",
                    message=f"閺堚偓婢堆傜秴缁?({max_disp:.2e}) 鐡掑懓绻冨Ο鈥崇€风亸鍝勵嚟閻?10%閿涘苯褰查懗钘夊灠鎼达缚绗夌搾?",
                    suggestion="閼板啳妾绘晶鐐插閸樻艾瀹抽妴浣瑰潑閸旂姾鍊犻弶鎸庡灗娴ｈ法鏁ら弴鎾彯瀵搫瀹抽弶鎰灐",
                )
            )

    except Exception:
        pass

    return issues


def _check_large_strain(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱銇囬崣妯鸿埌閿涙艾绨查崣妯哄瀻闁?> 0.1閿?0%鎼存柨褰夐敍澶嬫閸掋倖鏌囬弰顖氭儊閸氼垳鏁ゆ禍鍡楀殤娴ｆ洟娼痪鎸庘偓褋鈧?

    鐟欏嫬鍨敍?
    - 鎼存柨褰夐崚鍡涘櫤 > 0.1 娑?inp 閺?NLGEOM 閳?warning: 瀵ら缚顔呴崥顖滄暏閸戠姳缍嶉棃鐐靛殠閹?
    - 鎼存柨褰夐崚鍡涘櫤 > 0.1 娑?inp 閺?NLGEOM 閳?info: 婢堆冨綁瑜般垹鍨庨弸鎰剁礉鎼存柨褰夋稉鐑樺閺嶅吋婀曢弮銉ョ暰娑?
    - NLGEOM 濡偓濞村鏁幐浣疯⒈缁夊秵鐗稿蹇ョ窗*STEP, NLGEOM 閸?*STEP,NLGEOM閿涘牊妫ょ粚鐑樼壐閿?
    """
    issues: list[DiagnosticIssue] = []

    # 1. 濡偓閺?inp 閺傚洣娆㈤弰顖氭儊閺?NLGEOM
    has_nlgeom = False
    inp_text = _get_inp_text(inp_file, ctx=ctx)
    if inp_text:
        # 閺€顖涘瘮 *STEP, NLGEOM 閸?*STEP,NLGEOM 娑撱倗顫掗弽鐓庣础
        has_nlgeom = bool(re.search(r"\*STEP\s*,\s*NLGEOM", inp_text, re.IGNORECASE))

    try:
        summary = _get_frd_summary(results_dir, ctx=ctx)
        if summary is None:
            return issues
        if summary.max_strain <= 0:
            return issues

        # 3. 閺嶈宓侀梼鍫濃偓鐓庡灲閺?
        if summary.max_strain > 0.1:
            if has_nlgeom:
                issues.append(
                    DiagnosticIssue(
                        severity="info",
                        category="large_strain",
                        message=f"濡偓濞村鍩屾径褍褰夎ぐ顫礄{summary.max_strain_component}={summary.max_strain:.4f}閿涘绱濋崚鍡樼€藉鎻掓儙閻劌鍤戞担鏇㈡姜缁炬寧鈧嶇礄NLGEOM閿涘绱濇惔鏂垮綁鏉堟挸鍤稉鐑樺閺嶅吋婀曢弮銉ョ暰娑?",
                        location=f"閼哄倻鍋?{summary.max_strain_node}",
                        suggestion="缂佹挻鐏夋稉鐑樼壐閺?閹峰鐗搁張妤佹）鎼存柨褰夐敍宀勬姜缁炬寧鈧冪安閸欐ê鈧吋婀伴煬顐ｆЦ閸氬牏鎮婇惃?",
                    )
                )
            else:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="large_strain",
                        message=f"濡偓濞村鍩屾径褍褰夎ぐ顫礄{summary.max_strain_component}={summary.max_strain:.4f}閿涘绱濇担?inp 閺傚洣娆㈤張顏勬儙閻劌鍤戞担鏇㈡姜缁炬寧鈧嶇礄NLGEOM閿?",
                        location=f"閼哄倻鍋?{summary.max_strain_node}",
                        suggestion="閸?*STEP 鐞涘本鍧婇崝?NLGEOM 閸欏倹鏆熸禒銉ユ儙閻劌鍤戞担鏇㈡姜缁炬寧鈧冨瀻閺嬫劧绱?STEP, NLGEOM",
                    )
                )

    except Exception:
        pass

    return issues


# ------------------------------------------------------------------ #
# 閺夋劖鏋＄仦鍫熸箛瀵搫瀹抽幓鎰絿閿涘牆宕熸担宥忕窗Pa閿?
# ------------------------------------------------------------------ #


def _extract_yield_strength(
    inp_file: Optional[Path],
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[float]:
    """
    娴?inp 閺傚洣娆㈤幓鎰絿閺夋劖鏋＄仦鍫熸箛瀵搫瀹抽妴?

    閺€顖涘瘮閻ㄥ嫭娼楅弬娆忕暰娑斿绱?
    - *DEFORMATION PLASTICITY閿涙, nu, sigma_y, n, angle 閳?閸欐牜顑囨稉澶婂棘閺?sigma_y閿涘牆宕熸担?MPa閿?
    - *PLASTIC閿涙岸娓剁憴锝嗙€芥径姘愁攽閿涘矂绮拋銈呭絿缁楊兛绔存稉顏勭溁閺堝秶鍋ｉ敍鍫濆礋娴?MPa閿?
    - *ELASTIC閿涙碍妫ゅ▔鏇″箯閸欐牕鐪婚張宥呭繁鎼达讣绱濇潻鏂挎礀 None

    Returns:
        鐏炲牊婀囧鍝勫閿涘湧a閿涘绱濋弮鐘崇《閹绘劕褰囬弮鎯扮箲閸?None
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
                parts = re.findall(r"[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?", lines[i + 1])
                if len(parts) >= 3:
                    # sigma_y 閸楁洑缍呴弰?MPa閿涘矁娴嗛幑顫礋 Pa
                    result = float(parts[2]) * 1e6
                    break
            i += 1
            continue

        # *PLASTIC: 鐏炲牊婀囨惔鏂垮閿涘牏顑囨稉鈧崚妤嬬礆閿涘苯宕熸担?MPa
        if line.upper().startswith("*PLASTIC"):
            # 鐠囪褰囬崥搴ｇ敾闂堢偞鏁為柌濠咁攽閿涘苯褰囩粭顑跨娑擃亝鏆熼幑顔款攽閻ㄥ嫮顑囨稉鈧崚?
            i += 1
            while i < len(lines):
                data_line = lines[i].strip()
                if not data_line or data_line.startswith("**") or data_line.startswith("*"):
                    i += 1
                    continue
                parts = re.findall(r"[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?", data_line)
                if parts:
                    # 閸楁洑缍?MPa閿涘矁娴嗛幑顫礋 Pa
                    result = float(parts[0]) * 1e6
                    break
                i += 1
            if result is not None:
                break
            continue

        # *ELASTIC 閸欘亝婀?E 閸?nu閿涘本妫ゅ▔鏇″箯閸欐牕鐪婚張宥呭繁鎼?
        if line.upper().startswith("*ELASTIC"):
            break

        i += 1

    if ctx is not None:
        ctx.yield_strength_cache[target] = result
    return result


# ------------------------------------------------------------------ #
# 閸掓矮缍嬪Ο鈥崇础 & 閺夋劖鏋＄仦鍫熸箛濡偓濞?
# ------------------------------------------------------------------ #


def _check_rigid_body_mode(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱鍨版担鎾茨佸蹇ョ窗娴ｅ秶些闂堢偤娴傛担鍡楃安閸旀稑鍤戞稊搴濊礋闂嗚翰鈧?

    閸掋倖鏌囬柅鏄忕帆閿?
    - 閺堚偓婢堆傜秴缁?> 濡€崇€风亸鍝勵嚟閻?1% 娑?閺堚偓婢?von Mises 鎼存柨濮?< 鐏炲牊婀囧鍝勫閻?0.01
    - 濞夈劍鍓伴敍姘灠娴ｆ捁绻嶉崝銊ф畱閻楃懓绶涢弰?閺佺繝缍?鎼存柨濮忓鍫滅秵閿涘瞼鏁ら張鈧径褍绨查崝娑溾偓灞肩瑝閺勵垰閽╅崸鍥х安閸旀稒娲块崙鍡欌€?
    - 闁灝鍘ょ划妤冪秹閺嶉棿绗呮惔鏂垮閹绘帒鈧壈顕ゅ顔碱嚤閼峰娈戠拠顖涘Г
    """
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues

        max_disp = stats["max_displacement"]
        model_size = max(*stats["model_bounds"], 1e-10)

        # 娴ｅ秶些婢额亜鐨敍? 濡€崇€风亸鍝勵嚟 0.5%閿涘绗夌粻妤€鍨版担鎾茨佸?
        if max_disp < model_size * 0.005:
            return issues

        # 閼惧嘲褰囬張鈧径褍绨查崝?
        max_stress = stats["max_stress"]
        if max_stress <= 0:
            return issues

        # 娴?inp 閼惧嘲褰囩仦鍫熸箛瀵搫瀹?
        yield_strength = _extract_yield_strength(inp_file, ctx=ctx)
        if yield_strength is None:
            yield_strength = 250e6  # 姒涙顓荤紒鎾寸€柦?

        # 閺堚偓婢堆冪安閸?< 鐏炲牊婀囧鍝勫閻?0.01閿?%閿涘顓绘稉鐑樻Ц閸掓矮缍嬫潻鎰З
        if max_disp > model_size * 0.01 and max_stress < yield_strength * 0.01:
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="rigid_body_mode",
                    message=f"Large displacement with low stress detected (disp={max_disp:.2e}, stress={max_stress:.2e} Pa).",
                    location=f"閺堚偓婢堆冪安閸?鐏炲牊婀囧鍝勫濮? {max_stress / yield_strength:.4e}",
                    suggestion="濡偓閺屻儴绔熼悾灞炬蒋娴犺绱扮涵顔荤箽缂佹挻鐎悮顐㈢暚閸忋劎瀹抽弶鐕傜礄鐏忋倕鍙鹃弮瀣祮閼奉亞鏁辨惔锔肩礆閿涘本澧嶉張澶夌秴缁夎鍨庨柌蹇涘厴鐞氼偊妾洪崚?",
                )
            )

    except Exception:
        pass

    return issues


def _check_material_yield(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儲娼楅弬娆愭Ц閸氾箑鐪婚張宥忕窗閺堚偓婢堆冪安閸旀稒妲搁崥锕佺Т鏉╁洤鐪婚張宥呭繁鎼达负鈧?

    閸掋倖鏌囬柅鏄忕帆閿?
    - 閺堚偓婢?von Mises 鎼存柨濮?> 鐏炲牊婀囧鍝勫 閳?warning: 閺夋劖鏋＄仦鍫熸箛
    - 閺堚偓婢?von Mises 鎼存柨濮?> 鐏炲牊婀囧鍝勫 * 1.5 閳?error: 娑撱儵鍣哥仦鍫熸箛
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
            # 缁惧灝鑴婇幀褎娼楅弬娆欑礄*ELASTIC閿涘妫ょ仦鍫熸箛瀵搫瀹崇€规矮绠熼敍宀冪儲鏉╁洤鐪婚張宥嗩梾閺?
            log.info(
                "缁惧灝鑴婇幀褎娼楅弬娆欑礉閺冪姴鐪婚張宥呭繁鎼达箑鐣炬稊澶涚礉鐠哄疇绻冪仦鍫熸箛濡偓閺?"
            )
            return issues

        ratio = max_stress / yield_strength

        if ratio > 1.5:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    category="material_yield",
                    message=f"Max stress exceeds yield strength (stress={max_stress:.2e} Pa, yield={yield_strength:.2e} Pa, ratio={ratio:.1f}x).",
                    suggestion="1) 濡偓閺屻儴娴囬懡閿嬫Ц閸氾箒绉撮崙楦款啎鐠佲€斥偓?2) 閼板啳妾绘晶鐐插閺夋劖鏋￠崢姘閹存牔濞囬悽銊︽纯妤傛ê宸辨惔锔芥綏閺?3) 濡偓閺屻儴娴囬懡閿嬫煙閸氭垵鎷版潏鍦櫕閺夆€叉閺勵垰鎯佸锝団€?",
                )
            )
        elif ratio > 1.0:
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="material_yield",
                    message=f"閺夋劖鏋＄仦鍫熸箛閿涙碍娓舵径褍绨查崝娑崇礄{max_stress:.2e} Pa閿涘绉存潻鍥х溁閺堝秴宸辨惔锔肩礄{yield_strength:.2e} Pa閿涘娈?{ratio:.1f}x",
                    suggestion="濡偓閺屻儴娴囬懡閿嬫Ц閸氾箒绉撮崙楦款啎鐠佲€斥偓纭风礉閼板啳妾绘晶鐐插閺夋劖鏋￠崢姘閹存牔濞囬悽銊︽纯妤傛ê宸辨惔锔芥綏閺?",
                )
            )

    except Exception:
        pass

    return issues


def _check_unit_consistency(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """
    濡偓閺屻儱宕熸担宥勭閼峰瓨鈧嶇窗鎼存柨濮忛崐濂稿櫤缁狙勬Ц閸氾箑鎮庨悶鍡愨偓?

    閸掋倖鏌囬柅鏄忕帆閿?
    - 濮濓絽鐖剁紒鎾寸€惔鏂垮閼煎啫娲块敍?e2 ~ 1e9 Pa閿?00 Pa ~ 1 GPa閿?
    - < 1e0 (1 Pa)閿涙艾褰查懗鑺ユЦ閸楁洑缍呴幖鐐烘晩娴滃棴绱欐惔鏃囶嚉閻?MPa閿?
    - > 1e12 (1 TPa)閿涙氨澧块悶鍡曠瑐娑撳秴褰查懗鏂ょ礉濮濓絽鐖堕弶鎰灐娑撳秳绱版潏鎯у煂鏉╂瑤閲滈柌蹇曢獓

    鐢瓕顫嗛崡鏇氱秴闁挎瑨顕ら敍?
    - 閺夋劖鏋?E 閻?MPa閿涘奔绲炬潪鍊熷祹閻?N閿涘瞼娲块幒銉ヮ嚤閼锋潙绨查崝娑氱波閺嬫粌妯?1e6 閸?
    - 閸戠姳缍嶇亸鍝勵嚟 mm vs m 娑撳秳绔撮懛?
    """
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues
        max_stress = stats["max_stress"]

        if max_stress <= 0:
            return issues

        # 濡偓閺屻儵鍣虹痪褍绱撶敮?
        if max_stress < 1.0:
            issues.append(
                DiagnosticIssue(
                    severity="warning",
                    category="unit_consistency",
                    message=f"閺堚偓婢堆冪安閸旀稒鐎担搴礄{max_stress:.2e} Pa閿涘绱濋崣顖濆厴鐎涙ê婀崡鏇氱秴娑撳秳绔撮懛?",
                    suggestion="濡偓閺屻儲娼楅弬娆忓棘閺佹澘宕熸担宥忕窗E/nu 闁艾鐖堕悽?MPa閿涘矂鏆辨惔锔炬暏 mm閿涘瞼鈥樻穱婵婃祰閼藉嘲宕熸担宥勭閼?",
                )
            )
        elif max_stress > 1e12:
            issues.append(
                DiagnosticIssue(
                    severity="error",
                    category="unit_consistency",
                    message=f"閺堚偓婢堆冪安閸旀稑绱撶敮绋挎硶婢堆嶇礄{max_stress:.2e} Pa閿涘绱濋崣顖濆厴鐎涙ê婀崡鏇氱秴娑撱儵鍣告稉宥勭閼?",
                    suggestion="濡偓閺屻儲澧嶉張澶婂礋娴ｅ稄绱伴弶鎰灐閻?MPa 閺冭绱濋崙鐘辩秿韫囧懘銆忛悽?mm閿涘矁娴囬懡椋庢暏 N",
                )
            )

        # 妫版繂顦诲Λ鈧弻銉窗娴?inp 閹恒劍鏌囬張鐔告箿閻ㄥ嫬宕熸担宥堝瘱閸?
        # 婵″倹鐏夐弶鎰灐 E > 1e8 (> 100 GPa)閿涘矁鈧苯绨查崝?< 1e6 (< 1 MPa)閿涘苯褰查懗钘夊礋娴ｅ秵璐╂稊?
        inp_lines = _get_inp_lines(inp_file, ctx=ctx)
        if inp_lines:
            # 閹绘劕褰?E 閸婄》绱欓崡鏇氱秴 MPa閿?
            E_value = None
            for i, line in enumerate(inp_lines):
                if line.upper().startswith("*ELASTIC"):
                    if i + 1 < len(inp_lines):
                        parts = re.findall(r"[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?", inp_lines[i + 1])
                        if parts:
                            E_value = float(parts[0])
                            break

            if E_value and E_value > 1e8 and max_stress < 1e6:
                issues.append(
                    DiagnosticIssue(
                        severity="warning",
                        category="unit_consistency",
                        message=f"閺夋劖鏋″瑙勨偓褎膩闁?E={E_value:.2e} MPa 娑撳骸绨查崝娑氱波閺嬫粈绗夐崠褰掑帳閿涘苯褰查懗钘夊礋娴ｅ秳绗夋稉鈧懛?",
                        suggestion="婵″倹鐏?E 閻?Pa 閼板矂娼?MPa閿涘奔绱扮€佃壈鍤ф惔鏂垮缂佹挻鐏夐崑蹇撶毈 1e6 閸婂秲鈧倽顕涵顔款吇 E 閸楁洑缍呴弰?MPa閿涘苯鏄傜€电宕熸担宥嗘Ц mm閵?",
                    )
                )

    except Exception:
        pass

    return issues


# ------------------------------------------------------------------ #
# Level 2: 閸欏倽鈧啯顢嶆笟瀣嚠濮?
# ------------------------------------------------------------------ #


def _check_reference_cases(
    results_dir: Path,
    inp_file: Optional[Path] = None,
    ctx: Optional[DiagnosisContext] = None,
) -> dict:
    """
    娑撳骸寮懓鍐╊攳娓氬绨辩€佃鐦敍灞绢梾閺屻儳绮ㄩ弸婊勬Ц閸氾箑婀崥鍫㈡倞閼煎啫娲块崘鍛偓?

    Returns:
        {
            "issues": list[DiagnosticIssue],
            "similar_cases": list[dict],  # 閻╅晲鎶€濡楀牅绶ユ穱鈩冧紖
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

        # 娑撱倝妯佸▓鍨梾缁?
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

        # 娑撳海娴夋导鍏碱攳娓氬顕В鏃傜波閺?
        issues.extend(_compare_with_reference(results_dir, similar, ctx=ctx))

    except Exception as e:
        log.warning("閸欏倽鈧啯顢嶆笟瀣嚠濮ｆ柨銇戠拹? %s", e)

    return {"issues": issues, "similar_cases": similar_cases}


def _compare_with_reference(
    results_dir: Path,
    similar_cases: list[tuple[CaseMetadata, float]],
    ctx: Optional[DiagnosisContext] = None,
) -> list[DiagnosticIssue]:
    """鐏忓棛鏁ら幋椋庣波閺嬫粈绗岄惄闀愭妧濡楀牅绶ラ惃鍕暕閺堢喕瀵栭崶鏉戭嚠濮ｆ柣鈧?"""
    issues: list[DiagnosticIssue] = []

    try:
        stats = _get_frd_stats(results_dir, ctx=ctx)
        if stats is None:
            return issues
        user_disp_max = stats["max_displacement"]
        user_stress_max = stats["max_stress"]

        for ref_case, score in similar_cases:
            # 鐎佃鐦担宥囆?
            if ref_case.expected_disp_max and ref_case.expected_disp_max > 0:
                ratio = user_disp_max / ref_case.expected_disp_max
                if ratio > 10:
                    issues.append(
                        DiagnosticIssue(
                            severity="warning",
                            category="reference_comparison",
                            message=f"閺堚偓婢堆傜秴缁夌粯妲搁崥宀€琚崣鍌濃偓鍐╊攳娓氬娈?{ratio:.1f}x閿涘牊顢嶆笟? {ref_case.name}閿?",
                            location=f"濡楀牅绶ラ惄闀愭妧鎼? {score * 100:.0f}%",
                            suggestion="濡偓閺屻儴绔熼悾灞炬蒋娴犺埖妲搁崥锔跨瑢閸欏倽鈧啯顢嶆笟瀣╃閼疯揪绱濋幋鏍祰閼介攱妲搁崥锕佺箖婢?",
                        )
                    )
                    break
                elif ratio < 0.1 and ratio > 0:
                    issues.append(
                        DiagnosticIssue(
                            severity="info",
                            category="reference_comparison",
                            message=f"閺堚偓婢堆傜秴缁夌粯妲搁崥宀€琚崣鍌濃偓鍐╊攳娓氬娈?{ratio:.1f}x閿涘牊顢嶆笟? {ref_case.name}閿涘绱濋崣顖濆厴閸掓艾瀹虫潻鍥彯",
                            location=f"濡楀牅绶ラ惄闀愭妧鎼? {score * 100:.0f}%",
                            suggestion="缂佹挻鐏夐崑蹇撶毈閿涘苯褰查懗浠嬫付鐟曚焦顥呴弻銉ㄦ祰閼介攱妲搁崥锔筋劀绾喗鏌﹂崝?",
                        )
                    )

            # 鐎佃鐦惔鏂垮
            if (
                ref_case.expected_stress_max
                and ref_case.expected_stress_max > 0
                and user_stress_max > 0
            ):
                stress_ratio = user_stress_max / ref_case.expected_stress_max
                if stress_ratio > 10:
                    issues.append(
                        DiagnosticIssue(
                            severity="warning",
                            category="reference_comparison",
                            message=f"閺堚偓婢堆冪安閸旀稒妲搁崥宀€琚崣鍌濃偓鍐╊攳娓氬娈?{stress_ratio:.1f}x閿涘牊顢嶆笟? {ref_case.name}閿?",
                            location=f"濡楀牅绶ラ惄闀愭妧鎼? {score * 100:.0f}%",
                            suggestion="濡偓閺屻儲娼楅弬娆忓棘閺佺増妲搁崥锔筋劀绾噯绱濋幋鏍ㄦЦ閸氾箑鐡ㄩ崷銊ョ安閸旀盯娉︽稉?",
                        )
                    )
                    break

    except Exception as e:
        log.warning("鐎佃鐦崣鍌濃偓鍐╊攳娓氬妞傞崙娲晩: %s", e)

    return issues


def _get_max_stress(frd_data) -> float:
    """娴?FrdData 閼惧嘲褰囬張鈧径褍绨查崝娑栤偓?"""
    stress_result = frd_data.get_result("STRESS")
    if not stress_result or not stress_result.values:
        return 0.0

    max_stress = 0.0
    for vals in stress_result.values.values():
        if len(vals) >= 4:
            # 閸?von Mises閿涘牆浜ｇ拋鍓ь儑4娑擃亜鍨庨柌蹇旀Ц缁涘鏅ユ惔鏂垮閿?
            max_stress = max(max_stress, abs(vals[3]))
        elif vals:
            max_stress = max(max_stress, max(abs(v) for v in vals))
    return max_stress


def _get_max_displacement(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> Optional[float]:
    """娴?FRD 閺傚洣娆㈤幓鎰絿閻劍鍩涢張鈧径褌缍呯粔浼欑礉閻劋绨崣鍌濃偓鍐╊攳娓氬顕В鏂烩偓?"""
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
# Level 3: AI 鐠囧﹥鏌?
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
    """鏉╂劘顢?AI 濞ｅ崬瀹崇拠濠冩焽閵?"""
    all_issues: list[DiagnosticIssue] = []
    try:
        all_issues = _pick_ai_issues(level1_issues, level2_issues)

        # 閸欘亙绻氶悾娆忕秼閸?prompt 娴兼艾鐤勯梽鍛▏閻劎娈戠拠濠冩焽鐠囦焦宓侀敍宀勪缉閸忓秹顤傛径鏍掗弸?.frd/.inp閵?
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
        convergence_metrics = _get_convergence_metrics(results_dir, ctx=ctx)
        convergence_summary = _summarize_convergence_metrics(
            convergence_metrics,
            issues=all_issues,
        )
        stderr_summary = _get_stderr_summary(results_dir, ctx=ctx)
        evidence_sources = [
            bool(stderr_snippets.strip()),
            bool(physical_data.strip()),
            bool(stderr_summary.strip())
            and stderr_summary.strip().lower() != "no convergence data",
            bool(similar_cases),
            bool(convergence_summary.get("file_count")),
        ]
        if sum(1 for flag in evidence_sources if flag) < 2:
            # Insufficient grounded evidence: use deterministic diagnosis to avoid hallucination.
            return _build_rule_based_diagnosis(all_issues)

        evidence_digest = _build_ai_evidence_digest(
            all_issues,
            similar_cases,
            stderr_snippets=stderr_snippets,
            physical_data=physical_data,
            stderr_summary=stderr_summary,
            convergence_summary=convergence_summary,
        )
        prompt_text = make_diagnose_prompt_v2(
            issue_dicts,
            stderr_snippets,
            physical_data=physical_data,
            stderr_summary=stderr_summary,
            similar_cases=similar_cases,
            evidence_digest=evidence_digest,
        )

        if stream:
            handler = StreamHandler()
            tokens = client.complete_streaming(prompt_text)
            ai_text = validate_ai_output(handler.stream_tokens(tokens))
        else:
            ai_text = validate_ai_output(client.complete(prompt_text))

        if ai_text and ai_text.strip():
            return ai_text
        return _build_rule_based_diagnosis(all_issues)

    except Exception as e:
        log.warning("AI 鐠囧﹥鏌囨径杈Е: %s", e)
        return _build_rule_based_diagnosis(all_issues)


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
    """娴?.frd 閺傚洣娆㈤幓鎰絿閸忔娊鏁悧鈺冩倞閺佺増宓侀悽銊ょ艾 AI 閸掑棙鐎介妴?"""
    try:
        frd_data = _get_frd_data(results_dir, ctx=ctx)
        if frd_data is None:
            return ""
        lines = []

        # 閼哄倻鍋?閸楁洖鍘撻弫?
        lines.append(f"閼哄倻鍋ｉ弫? {frd_data.node_count}, 閸楁洖鍘撻弫? {frd_data.element_count}")

        # 閺夋劖鏋″瑙勨偓褎膩闁?E閿涘牅绮?INP 閺傚洣娆㈤幓鎰絿閿?
        inp_lines = _get_inp_lines(inp_file, ctx=ctx)
        for i, line in enumerate(inp_lines):
            if line.upper().startswith("*ELASTIC"):
                next_line = inp_lines[i + 1] if i + 1 < len(inp_lines) else ""
                parts = re.findall(r"[+-]?\d+\.?\d*(?:[eE][-+]?\d+)?", next_line)
                if parts:
                    E_val = float(parts[0])
                    lines.append(f"閺夋劖鏋″瑙勨偓褎膩闁?E: {E_val:.6e} MPa")
                    break

        # 娴ｅ秶些
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
            lines.append(f"閺堚偓婢堆傜秴缁? {max_disp:.6e} (閼哄倻鍋?{max_node})")

        # 鎼存柨濮?
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
            lines.append(f"閺堚偓婢?von Mises 鎼存柨濮? {max_stress:.6e} (閸楁洖鍘?{max_elem})")

        # 鎼存柨褰夐崚鍡涘櫤閿涘湵OSTRAIN 閸栧懎鎯?EXX, EYY, EZZ, EXY, EYZ, EZX閿?
        strain_result = frd_data.get_result("TOSTRAIN")
        if strain_result and strain_result.components and strain_result.values:
            strain_components = strain_result.components
            strain_vals_by_node = strain_result.values

            # 閹垫儳鍤В蹇庨嚋閸掑棝鍣洪惃鍕付婢堆冣偓?
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
                lines.append("\n鎼存柨褰夐崚鍡涘櫤閿涘牏绮风€电懓鈧吋娓舵径褝绱?")
                for comp_name in strain_components:
                    if comp_name in max_vals:
                        lines.append(
                            f"  {comp_name}: {max_vals[comp_name]:.6e} (閼哄倻鍋?{max_nodes[comp_name]})"
                        )

                # 濡偓濞村妲搁崥锕€鐡ㄩ崷銊ャ亣閸欐ê鑸伴悧鐟扮窙閿涘牆绨查崣?> 0.1閿?
                large_strain_components = {k: v for k, v in max_vals.items() if v > 0.1}
                if large_strain_components:
                    lines.append(
                        "\n閳跨媴绗?婢堆冨綁瑜般垼顒熼崨濠忕窗濡偓濞村鍩屾禒銉ょ瑓鎼存柨褰夐崚鍡涘櫤 > 0.1閿?0%閸欐ê鑸伴敍?"
                    )
                    for comp_name, val in large_strain_components.items():
                        lines.append(f"  {comp_name}: {val:.4f}")

        return "\n".join(lines)
    except Exception as e:
        log.warning("閹绘劕褰囬悧鈺冩倞閺佺増宓佹径杈Е: %s", e)
        return ""


def _classify_series_trend(
    values: list[float],
    *,
    neutral_ratio: float = 0.15,
    direction_words: tuple[str, str, str] = ("decreasing", "increasing", "steady"),
) -> str:
    if len(values) < 2:
        return "insufficient"

    first = values[0]
    last = values[-1]

    if first == 0:
        if last == 0:
            return direction_words[2]
        return direction_words[1] if last > 0 else direction_words[0]

    ratio = (last - first) / abs(first)
    if ratio <= -neutral_ratio:
        return direction_words[0]
    if ratio >= neutral_ratio:
        return direction_words[1]
    return direction_words[2]


def _format_series_bounds(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{values[0]:.3e}->{values[-1]:.3e}"


def _extract_convergence_metrics(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[dict]:
    del ctx
    return extract_solver_convergence_metrics(results_dir)


def _get_convergence_metrics(
    results_dir: Path,
    *,
    ctx: Optional[DiagnosisContext] = None,
) -> list[dict]:
    if ctx is None:
        return _extract_convergence_metrics(results_dir, ctx=None)
    if not ctx.convergence_metrics_loaded:
        ctx.convergence_metrics = _extract_convergence_metrics(results_dir, ctx=ctx)
        ctx.convergence_metrics_loaded = True
    return ctx.convergence_metrics


def _get_stderr_summary(
    results_dir: Path,
    ctx: Optional[DiagnosisContext] = None,
) -> str:
    """Extract compact convergence metrics and trends from .sta files."""
    items = _get_convergence_metrics(results_dir, ctx=ctx)
    if not items:
        return "no convergence data"

    summaries: list[str] = []
    for item in items:
        parts = [f"file={item['file']}"]
        if item.get("status"):
            parts.append(f"status={item['status']}")
        if item.get("max_iter") is not None:
            parts.append(f"max_iter={item['max_iter']}")
        if item.get("final_residual") is not None:
            parts.append(f"final_residual={item['final_residual']:.3e}")
        if item.get("final_force_ratio") is not None:
            parts.append(f"final_force_ratio={item['final_force_ratio']:.2f}%")
        if item.get("final_increment") is not None and item["final_increment"] > 0:
            parts.append(f"final_increment={item['final_increment']:.3e}")
        if item.get("residual_trend"):
            span = item.get("residual_span") or "n/a"
            parts.append(f"residual_trend={item['residual_trend']}({span})")
        if item.get("increment_trend"):
            span = item.get("increment_span") or "n/a"
            parts.append(f"increment_trend={item['increment_trend']}({span})")
        summaries.append(" | ".join(parts))

    return "\n".join(summaries)


def _get_stderr_snippets(
    results_dir: Path,
    issues: list,
    ctx: Optional[DiagnosisContext] = None,
) -> str:
    """Extract runtime snippets relevant to current diagnosis issues."""
    if not issues:
        return ""

    snippets: list[str] = []
    candidate_files = _get_solver_text_sources(results_dir, ctx=ctx)
    if not candidate_files:
        return ""

    preferred_suffixes = {".stderr", ".log"}
    preferred = [path for path in candidate_files if path.suffix.lower() in preferred_suffixes]
    search_files = preferred or candidate_files[:2]

    try:
        used_ranges: set[tuple[str, int, int]] = set()

        for source_file in search_files:
            text = _read_text_cached(source_file, ctx=ctx)
            lines = text.splitlines()
            lowered_lines = [line.lower() for line in lines]

            for issue in normalize_issues(issues):
                keywords = _issue_keywords(issue)
                if not keywords:
                    continue

                for i, line_lower in enumerate(lowered_lines):
                    if not any(kw in line_lower for kw in keywords):
                        continue

                    start = max(0, i - AI_SNIPPET_CONTEXT_RADIUS)
                    end = min(len(lines), i + AI_SNIPPET_CONTEXT_RADIUS + 1)
                    range_key = (source_file.name, start, end)
                    if range_key in used_ranges:
                        continue
                    used_ranges.add(range_key)

                    snippet_lines = lines[start:end]
                    for j in range(len(snippet_lines)):
                        if i - start == j:
                            snippet_lines[j] = f">>> {snippet_lines[j]}"
                        else:
                            snippet_lines[j] = f"    {snippet_lines[j]}"

                    snippets.append(
                        f"--- Match ({source_file.name} line {i + 1}) [{issue.category}] ---"
                    )
                    snippets.extend(snippet_lines)
                    snippets.append("")

                    if len(used_ranges) >= AI_MAX_SNIPPETS:
                        break
                    break

                if len(used_ranges) >= AI_MAX_SNIPPETS:
                    break

            if len(used_ranges) >= AI_MAX_SNIPPETS:
                break

        if not snippets:
            fallback_file = search_files[0]
            fallback_lines = _read_text_cached(fallback_file, ctx=ctx).splitlines()[:20]
            if fallback_lines:
                snippets.append(f"--- Fallback ({fallback_file.name}) ---")
                snippets.extend(f"    {line}" for line in fallback_lines)

    except OSError:
        pass

    return "\n".join(snippets) if snippets else "No relevant snippets found."
