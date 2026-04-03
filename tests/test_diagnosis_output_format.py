from __future__ import annotations

from cae.ai.diagnose import DiagnosticIssue, DiagnoseResult, build_diagnosis_summary, normalize_issues


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
