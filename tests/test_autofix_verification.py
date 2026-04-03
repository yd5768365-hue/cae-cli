from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from cae.ai.diagnose import DiagnosticIssue
from cae.ai.fix_rules import fix_inp


def _make_workspace() -> Path:
    root = Path(__file__).parent / ".tmp_autofix_verification"
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_missing_elastic_autofix_reports_passed_verification() -> None:
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
        assert result.verification_status == "passed"
        assert "material_missing_elastic" in result.verification_notes
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_missing_step_autofix_reports_passed_verification() -> None:
    workspace = _make_workspace()
    try:
        inp_file = workspace / "model.inp"
        inp_file.write_text(
            "*HEADING\n"
            "*NODE\n"
            "1, 0, 0, 0\n",
            encoding="utf-8",
        )

        issue = DiagnosticIssue(
            severity="error",
            category="input_syntax",
            message="INP file missing *STEP definition",
            suggestion="add a *STEP block",
        )

        result = fix_inp(inp_file, [issue], workspace)

        assert result.success is True
        assert result.verification_status == "passed"
        assert "*STEP/*END STEP block present" in result.verification_notes
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_convergence_autofix_reports_reduced_increment() -> None:
    workspace = _make_workspace()
    try:
        inp_file = workspace / "model.inp"
        inp_file.write_text(
            "*HEADING\n"
            "*STEP\n"
            "*STATIC\n"
            "0.2, 1.0\n"
            "*END STEP\n",
            encoding="utf-8",
        )

        issue = DiagnosticIssue(
            severity="error",
            category="convergence",
            message="convergence issue detected",
            suggestion="reduce initial step increment in *STATIC",
        )

        result = fix_inp(inp_file, [issue], workspace)

        assert result.success is True
        assert result.verification_status == "passed"
        assert "reduced from 0.2 to 0.02" in result.verification_notes
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
