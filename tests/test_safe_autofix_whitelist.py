from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from cae.ai.diagnose import DiagnosticIssue
from cae.ai.fix_rules import fix_inp, get_safe_autofixable_issues


def _make_workspace() -> Path:
    root = Path(__file__).parent / ".tmp_safe_autofix"
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_autofix_rejects_non_whitelist_physics_changing_issue() -> None:
    workspace = _make_workspace()
    try:
        inp_file = workspace / "model.inp"
        inp_file.write_text(
            "*HEADING\n"
            "*STEP\n"
            "*STATIC\n"
            "0.1, 1.0\n"
            "*END STEP\n",
            encoding="utf-8",
        )

        issue = DiagnosticIssue(
            severity="error",
            category="boundary_condition",
            message="missing boundary value",
            suggestion="add a displacement boundary",
        )

        result = fix_inp(inp_file, [issue], workspace)

        assert result.success is False
        assert "whitelist" in (result.error or "").lower()
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_autofix_accepts_missing_elastic_issue() -> None:
    workspace = _make_workspace()
    try:
        inp_file = workspace / "model.inp"
        inp_file.write_text(
            "*HEADING\n"
            "*MATERIAL, NAME=STEEL\n"
            "*DENSITY\n"
            "7.85e-09\n"
            "*STEP\n"
            "*STATIC\n"
            "0.1, 1.0\n"
            "*END STEP\n",
            encoding="utf-8",
        )
        (workspace / "case.stderr").write_text(
            "ERROR: no elastic constants were assigned to material STEEL\n",
            encoding="utf-8",
        )

        issue = DiagnosticIssue(
            severity="error",
            category="material",
            message="material missing elastic constants",
            suggestion="add *ELASTIC under *MATERIAL",
        )

        result = fix_inp(inp_file, [issue], workspace)

        assert result.success is True
        assert result.fixed_path is not None and result.fixed_path.exists()
        fixed_text = result.fixed_path.read_text(encoding="utf-8")
        assert "*ELASTIC" in fixed_text
        assert "210000, 0.3" in fixed_text
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_get_safe_autofixable_issues_filters_to_explicit_whitelist() -> None:
    issues = [
        DiagnosticIssue(
            severity="error",
            category="material",
            message="material missing elastic constants",
            suggestion="add *ELASTIC",
        ),
        DiagnosticIssue(
            severity="error",
            category="boundary_condition",
            message="zero pivot detected",
            suggestion="add displacement constraints",
        ),
        DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="INP file missing *STEP definition",
            suggestion="add a *STEP block",
        ),
    ]

    safe_issues = get_safe_autofixable_issues(issues)

    assert len(safe_issues) == 2
    assert all(issue.category in {"material", "input_syntax"} for issue in safe_issues)
