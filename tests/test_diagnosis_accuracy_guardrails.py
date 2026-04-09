from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from cae.ai.diagnose import _check_convergence, _check_dynamics_errors, diagnose_results


def _make_workspace() -> Path:
    root = Path(__file__).parent / ".tmp_diagnosis_accuracy"
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_dynamics_check_ignores_normal_eigenvalue_output() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "eigenvalue 1 = 123.45\n"
            "eigenvalue 2 = 456.78\n",
            encoding="utf-8",
        )

        issues = _check_dynamics_errors(workspace)

        assert issues == []
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_dynamics_check_reports_eigenvalue_failure() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "ERROR: eigenvalue solver failed at step 1\n",
            encoding="utf-8",
        )

        issues = _check_dynamics_errors(workspace)

        assert len(issues) == 1
        assert issues[0].category == "dynamics"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_convergence_check_ignores_unrelated_fatal_error() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "fatal error: could not write temporary report\n",
            encoding="utf-8",
        )

        issues = _check_convergence(workspace)

        assert all(issue.category != "convergence" for issue in issues)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_convergence_contradiction_downgrades_when_trend_is_healthy() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.sta").write_text(
            "iter=1 resid.=1.0e+0 force%=100 increment size = 1.0e-2\n"
            "iter=2 resid.=1.0e-1 force%=55 increment size = 5.0e-3\n"
            "iter=3 resid.=1.0e-3 force%=12 increment size = 1.0e-3\n"
            "CONVERGED\n",
            encoding="utf-8",
        )
        (workspace / "case.stderr").write_text(
            "warning: increment did not converge at iteration 2\n",
            encoding="utf-8",
        )

        issues = _check_convergence(workspace)

        assert issues
        assert all(issue.severity != "error" for issue in issues)
        assert any("Auto-downgraded" in (issue.suggestion or "") for issue in issues)
        assert any(issue.evidence_conflict for issue in issues)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_single_source_error_is_downgraded_in_diagnose_results() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "ERROR: increment did not converge\n",
            encoding="utf-8",
        )

        result = diagnose_results(workspace, client=None)
        convergence_issues = [i for i in result.level1_issues if i.category == "convergence"]

        assert convergence_issues
        assert all(i.severity != "error" for i in convergence_issues)
        assert any("Evidence guardrail triggered" in (i.evidence_conflict or "") for i in convergence_issues)
        assert all((i.evidence_support_count or 0) <= 1 for i in convergence_issues)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
