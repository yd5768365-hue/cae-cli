from __future__ import annotations

from cae.ai.diagnose import (
    DiagnosticIssue,
    DiagnoseResult,
    build_diagnosis_summary,
    issue_to_dict,
    normalize_issues,
)


def test_diagnosis_output_is_deduplicated_and_sorted() -> None:
    issues = [
        DiagnosticIssue(
            severity="warning",
            category="material",
            message="Material missing elastic constants",
            suggestion="Add *ELASTIC",
        ),
        DiagnosticIssue(
            severity="error",
            category="material",
            message="Material   missing elastic constants",
            suggestion="Add *ELASTIC under *MATERIAL",
        ),
        DiagnosticIssue(
            severity="warning",
            category="unit_consistency",
            message="Possible unit mismatch",
            suggestion="Check E units",
        ),
    ]

    normalized = normalize_issues(issues)

    assert len(normalized) == 2
    assert normalized[0].severity == "error"
    assert normalized[0].category == "material"
    assert normalized[0].priority <= normalized[1].priority
    assert normalized[0].title == "Material Definition Issue"
    assert normalized[0].action == "Add *ELASTIC under *MATERIAL"


def test_build_diagnosis_summary_reports_top_issue() -> None:
    issues = [
        DiagnosticIssue(
            severity="warning",
            category="unit_consistency",
            message="Possible unit mismatch",
            suggestion="Check E units",
        ),
        DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="Unknown keyword found",
            suggestion="Fix misspelled card keyword",
        ),
    ]

    summary = build_diagnosis_summary(issues)

    assert summary["total"] == 2
    assert summary["error_count"] == 1
    assert summary["warning_count"] == 1
    assert summary["top_issue"] is not None
    assert summary["top_issue"].category == "input_syntax"
    assert summary["first_action"] == "Fix misspelled card keyword"


def test_build_diagnosis_summary_includes_triage_plan() -> None:
    summary = build_diagnosis_summary([
        DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="Unknown keyword found",
            suggestion="Fix misspelled card keyword",
            evidence_line="case.stderr:5: unknown keyword",
            evidence_score=0.92,
            evidence_support_count=2,
        ),
        DiagnosticIssue(
            severity="error",
            category="convergence",
            message="Increment did not converge",
            suggestion="Reduce initial increment",
            evidence_line="case.dat:12: increment did not converge",
            evidence_score=0.35,
            evidence_support_count=0,
            evidence_conflict="STA trend indicates healthy convergence.",
        ),
    ])

    assert summary["blocking_count"] == 1
    assert summary["needs_review_count"] == 1
    assert summary["confidence_counts"]["high"] == 1
    assert summary["confidence_counts"]["low"] == 1
    assert summary["triage_counts"]["blocking"] == 1
    assert summary["triage_counts"]["review"] == 1
    assert summary["risk_level"] in {"low", "medium", "high", "critical"}
    assert summary["execution_plan"][0]["triage"] == "blocking"
    assert summary["execution_plan"][0]["confidence"] == "high"


def test_issue_to_dict_exports_confidence_and_triage() -> None:
    payload = issue_to_dict(
        DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="INP file missing *STEP definition",
            suggestion="add a *STEP block",
            evidence_line="case.stderr:3: missing *STEP",
            evidence_score=0.9,
            evidence_support_count=2,
        )
    )

    assert payload["confidence"] == "high"
    assert payload["triage"] == "safe_auto_fix"


def test_diagnose_result_issues_property_returns_normalized_union() -> None:
    result = DiagnoseResult(
        success=True,
        level1_issues=[
            DiagnosticIssue(
                severity="warning",
                category="material",
                message="Material missing elastic constants",
                suggestion="Add *ELASTIC",
            )
        ],
        level2_issues=[
            DiagnosticIssue(
                severity="error",
                category="material",
                message="Material missing elastic constants",
                suggestion="Add *ELASTIC under *MATERIAL",
            )
        ],
    )

    issues = result.issues

    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert issues[0].priority is not None


def test_normalize_issues_uses_safe_autofix_whitelist() -> None:
    issues = normalize_issues([
        DiagnosticIssue(
            severity="error",
            category="boundary_condition",
            message="missing displacement constraint",
            suggestion="add a displacement boundary condition",
            auto_fixable=True,
        )
    ])

    assert issues[0].auto_fixable is False
