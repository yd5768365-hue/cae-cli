from __future__ import annotations

from pathlib import Path
from uuid import uuid4
from unittest.mock import MagicMock

from cae.ai.diagnose import (
    DiagnosticIssue,
    DiagnoseResult,
    _apply_category_evidence_guardrails,
    _infer_evidence_source_trust,
    _get_evidence_guardrails,
    _get_stderr_snippets,
    _get_stderr_summary,
    _parse_issue_location_hint,
    _pick_ai_issues,
    _run_ai_diagnosis,
    build_diagnosis_summary,
    diagnosis_result_to_dict,
    normalize_issues,
)


def test_build_diagnosis_summary_includes_distribution_fields() -> None:
    summary = build_diagnosis_summary(
        [
            DiagnosticIssue(
                severity="error",
                category="input_syntax",
                message="Unknown keyword found",
                suggestion="Fix keyword",
            ),
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message="Not converged",
                suggestion="Reduce increment",
            ),
        ]
    )

    assert summary["risk_score"] > 0
    assert summary["by_category"]["input_syntax"] == 1
    assert summary["by_severity"]["error"] == 1
    assert summary["action_items"]


def test_parse_issue_location_hint_handles_line_variants() -> None:
    assert _parse_issue_location_hint("case.stderr:42") == ("case.stderr", 42)
    assert _parse_issue_location_hint("input.inp line 12") == ("input.inp", 12)
    assert _parse_issue_location_hint("input.inp 鐞?6") == ("input.inp", 6)
    assert _parse_issue_location_hint("case.stderr") == ("case.stderr", None)


def test_stderr_snippets_use_category_keywords() -> None:
    tmp_path = Path("tests/.tmp_ai_diag_snippets") / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "case.stderr").write_text(
        "solver start\n"
        "zero pivot in equation solver\n"
        "solver end\n",
        encoding="utf-8",
    )
    issue = DiagnosticIssue(
        severity="error",
        category="boundary_condition",
        message="Potential boundary issue",
    )

    snippets = _get_stderr_snippets(tmp_path, [issue])

    assert "Match" in snippets
    assert "zero pivot" in snippets


def test_ai_prompt_contains_evidence_digest(monkeypatch) -> None:
    monkeypatch.setattr(
        "cae.ai.diagnose._get_physical_data",
        lambda results_dir, inp_file=None, ctx=None: "max_disp=1e-3",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_summary",
        lambda results_dir, ctx=None: "NOT CONVERGED",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_snippets",
        lambda results_dir, issues, ctx=None: ">>> zero pivot",
    )

    client = MagicMock()
    client.complete.side_effect = lambda prompt: prompt

    prompt = _run_ai_diagnosis(
        client,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="boundary_condition",
                message="zero pivot detected",
                suggestion="add constraints",
            )
        ],
        level2_issues=[],
        similar_cases=[{"name": "beam_case", "similarity_score": 90.0}],
        results_dir=Path.cwd(),
        inp_file=None,
        stream=False,
        ctx=None,
    )

    assert prompt is not None
    assert "Evidence coverage:" in prompt
    assert "Issues: total=" in prompt
    assert "Best reference:" in prompt
    assert "Convergence:" in prompt


def test_pick_ai_issues_balances_categories() -> None:
    level1_issues = [
        DiagnosticIssue(
            severity="error",
            category="convergence",
            message=f"Convergence issue {idx}",
            suggestion="Reduce increment",
        )
        for idx in range(10)
    ]
    level1_issues.extend(
        [
            DiagnosticIssue(
                severity="warning",
                category="boundary_condition",
                message=f"Boundary issue {idx}",
                suggestion="Add constraints",
            )
            for idx in range(5)
        ]
    )

    selected = _pick_ai_issues(level1_issues, [])
    categories = {issue.category for issue in selected}

    assert len(selected) <= 12
    assert "convergence" in categories
    assert "boundary_condition" in categories


def test_run_ai_diagnosis_falls_back_when_llm_returns_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "cae.ai.diagnose._get_physical_data",
        lambda results_dir, inp_file=None, ctx=None: "",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_summary",
        lambda results_dir, ctx=None: "",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_snippets",
        lambda results_dir, issues, ctx=None: "",
    )

    client = MagicMock()
    client.complete.return_value = ""

    result = _run_ai_diagnosis(
        client,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="not converged",
                suggestion="reduce initial increment",
            )
        ],
        level2_issues=[],
        similar_cases=[],
        results_dir=Path.cwd(),
        inp_file=None,
        stream=False,
        ctx=None,
    )

    assert result is not None
    assert "reduce initial increment" in result
    assert "1." in result


def test_run_ai_diagnosis_skips_llm_when_evidence_is_sparse(monkeypatch) -> None:
    monkeypatch.setattr(
        "cae.ai.diagnose._get_physical_data",
        lambda results_dir, inp_file=None, ctx=None: "",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_summary",
        lambda results_dir, ctx=None: "no convergence data",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_stderr_snippets",
        lambda results_dir, issues, ctx=None: "",
    )
    monkeypatch.setattr(
        "cae.ai.diagnose._get_convergence_metrics",
        lambda results_dir, ctx=None: [],
    )

    client = MagicMock()
    client.complete.return_value = "LLM should not be used here"

    result = _run_ai_diagnosis(
        client,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="not converged",
                suggestion="reduce initial increment",
            )
        ],
        level2_issues=[],
        similar_cases=[],
        results_dir=Path.cwd(),
        inp_file=None,
        stream=False,
        ctx=None,
    )

    assert result is not None
    assert "reduce initial increment" in result
    client.complete.assert_not_called()

def test_stderr_summary_includes_convergence_trend() -> None:
    tmp_path = Path("tests/.tmp_ai_diag_snippets") / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "case.sta").write_text(
        "step=1 inc=1 iter=1 resid.=1.0 force%=100 increment size = 1.0e-2\n"
        "step=1 inc=1 iter=2 resid.=0.2 force%=60 increment size = 5.0e-3\n"
        "step=1 inc=1 iter=3 resid.=0.01 force%=10 increment size = 1.0e-3\n",
        encoding="utf-8",
    )

    summary = _get_stderr_summary(tmp_path)

    assert "residual_trend=decreasing" in summary
    assert "increment_trend=shrinking" in summary
    assert "final_residual=" in summary


def test_diagnosis_result_to_dict_is_json_ready() -> None:
    result = DiagnoseResult(
        success=True,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="input_syntax",
                message="Unknown keyword",
                suggestion="Fix keyword",
                auto_fixable=True,
            )
        ],
        level2_issues=[],
        level3_diagnosis="Diagnosis text",
        similar_cases=[{"name": "case_a", "similarity_score": 88.0}],
    )

    payload = diagnosis_result_to_dict(
        result,
        results_dir=Path("tmp/results"),
        inp_file=Path("tmp/model.inp"),
        ai_enabled=True,
    )

    assert payload["success"] is True
    assert payload["issue_count"] == 1
    assert payload["summary"]["top_issue"]["category"] == "input_syntax"
    assert payload["issues"][0]["auto_fixable"] is True
    assert payload["meta"]["ai_enabled"] is True
    assert payload["convergence"]["summary"]["file_count"] == 0


def test_diagnosis_result_to_dict_contains_structured_convergence() -> None:
    tmp_path = Path("tests/.tmp_ai_diag_snippets") / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "case.sta").write_text(
        "step=1 inc=1 iter=1 resid.=1.0 force%=100 increment size = 1.0e-2\n"
        "step=1 inc=1 iter=2 resid.=0.2 force%=70 increment size = 5.0e-3\n"
        "step=1 inc=1 iter=3 resid.=0.01 force%=20 increment size = 1.0e-3\n",
        encoding="utf-8",
    )

    payload = diagnosis_result_to_dict(
        DiagnoseResult(success=True),
        results_dir=tmp_path,
        inp_file=None,
        ai_enabled=False,
    )

    conv = payload["convergence"]
    assert conv["summary"]["file_count"] == 1
    assert conv["summary"]["max_iterations"] == 3
    assert conv["files"][0]["residual_trend"] == "decreasing"
    assert conv["files"][0]["increment_trend"] == "shrinking"


def test_diagnosis_result_to_dict_uses_cached_convergence_metrics() -> None:
    result = DiagnoseResult(
        success=True,
        level1_issues=[
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="not converged",
                suggestion="reduce increment",
            )
        ],
        convergence_metrics=[
            {
                "file": "case.sta",
                "status": None,
                "max_iter": 7,
                "final_residual": 0.2,
                "final_force_ratio": None,
                "final_increment": 1e-4,
                "residual_trend": "steady",
                "residual_span": "2.000e-01->2.000e-01",
                "increment_trend": "shrinking",
                "increment_span": "1.000e-03->1.000e-04",
            }
        ],
    )

    payload = diagnosis_result_to_dict(
        result,
        results_dir=Path("tmp/does_not_exist"),
        inp_file=None,
        ai_enabled=False,
    )

    conv = payload["convergence"]
    assert conv["summary"]["file_count"] == 1
    assert conv["summary"]["has_not_converged"] is True
    assert conv["summary"]["max_iterations"] == 7
    assert conv["files"][0]["file"] == "case.sta"


def test_normalize_issues_prefers_duplicate_with_higher_evidence_score() -> None:
    normalized = normalize_issues(
        [
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="increment did not converge",
                suggestion="reduce increment",
                evidence_line="case.stderr:10: increment did not converge",
                evidence_score=0.9,
            ),
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="increment did not converge",
                suggestion="reduce increment",
                evidence_score=0.25,
            ),
        ]
    )

    assert len(normalized) == 1
    assert normalized[0].evidence_line is not None
    assert normalized[0].evidence_score is not None
    assert normalized[0].evidence_score >= 0.9


def test_normalize_issues_prefers_non_conflicting_evidence_when_same_issue() -> None:
    normalized = normalize_issues(
        [
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message="increment did not converge",
                evidence_line="case.stderr:20: increment did not converge",
                evidence_score=0.95,
                evidence_conflict="STA trend indicates healthy convergence.",
            ),
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message="increment did not converge",
                evidence_line="case.stderr:20: increment did not converge",
                evidence_score=0.75,
            ),
        ]
    )

    assert len(normalized) == 1
    assert normalized[0].evidence_conflict is None
    assert normalized[0].evidence_score is not None
    assert normalized[0].evidence_score >= 0.75


def test_normalize_issues_prefers_higher_support_count_when_same_issue() -> None:
    normalized = normalize_issues(
        [
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message="increment did not converge",
                evidence_line="case.stderr:20: increment did not converge",
                evidence_score=0.80,
                evidence_support_count=1,
            ),
            DiagnosticIssue(
                severity="warning",
                category="convergence",
                message="increment did not converge",
                evidence_line="case.stderr:20: increment did not converge",
                evidence_score=0.80,
                evidence_support_count=2,
            ),
        ]
    )

    assert len(normalized) == 1
    assert normalized[0].evidence_support_count == 2


def test_category_guardrail_keeps_input_syntax_error_with_single_source() -> None:
    issues = [
        DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="unknown keyword in *STEP",
            evidence_line="case.stderr:8: unknown keyword",
            evidence_score=0.72,
            evidence_support_count=1,
        )
    ]

    guarded = _apply_category_evidence_guardrails(issues)

    assert len(guarded) == 1
    assert guarded[0].severity == "error"
    assert guarded[0].evidence_conflict is None


def test_default_guardrail_downgrades_unconfigured_low_confidence_error() -> None:
    issues = [
        DiagnosticIssue(
            severity="error",
            category="mesh_quality",
            message="possible distorted element pattern",
            evidence_score=0.35,
            evidence_support_count=0,
        )
    ]

    guarded = _apply_category_evidence_guardrails(issues)

    assert len(guarded) == 1
    assert guarded[0].severity == "warning"
    assert "Evidence guardrail triggered" in (guarded[0].evidence_conflict or "")
    assert "support=0<1" in (guarded[0].evidence_conflict or "")


def test_category_guardrail_uses_external_config_override(monkeypatch) -> None:
    tmp_path = Path("tests/.tmp_ai_diag_snippets") / uuid4().hex
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg_path = tmp_path / "guardrails.json"
    cfg_path.write_text(
        (
            "{\n"
            '  "convergence": {\n'
            '    "min_support": 1,\n'
            '    "min_score": 0.0,\n'
            '    "score_penalty": 0.02\n'
            "  }\n"
            "}\n"
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("CAE_EVIDENCE_GUARDRAILS_PATH", str(cfg_path))
    _get_evidence_guardrails.cache_clear()
    try:
        issues = [
            DiagnosticIssue(
                severity="error",
                category="convergence",
                message="increment did not converge",
                evidence_line="case.stderr:8: increment did not converge",
                evidence_score=0.85,
                evidence_support_count=1,
            )
        ]

        guarded = _apply_category_evidence_guardrails(issues)

        assert len(guarded) == 1
        assert guarded[0].severity == "error"
        assert guarded[0].evidence_conflict is None
    finally:
        _get_evidence_guardrails.cache_clear()


def test_evidence_source_trust_is_lower_for_dat_than_stderr() -> None:
    stderr_issue = DiagnosticIssue(
        severity="warning",
        category="convergence",
        message="not converged",
        evidence_line="case.stderr:9: not converged",
    )
    dat_issue = DiagnosticIssue(
        severity="warning",
        category="convergence",
        message="not converged",
        evidence_line="case.dat:9: not converged",
    )

    stderr_trust = _infer_evidence_source_trust(stderr_issue)
    dat_trust = _infer_evidence_source_trust(dat_issue)

    assert stderr_trust > dat_trust
    assert stderr_trust >= 0.9
    assert dat_trust <= 0.8


def test_category_guardrail_downgrades_low_trust_error() -> None:
    issues = [
        DiagnosticIssue(
            severity="error",
            category="convergence",
            message="increment did not converge",
            evidence_line="case.dat:12: increment did not converge",
            evidence_score=0.92,
            evidence_support_count=2,
        )
    ]

    guarded = _apply_category_evidence_guardrails(issues)

    assert len(guarded) == 1
    assert guarded[0].severity == "warning"
    assert "trust=" in (guarded[0].evidence_conflict or "")
