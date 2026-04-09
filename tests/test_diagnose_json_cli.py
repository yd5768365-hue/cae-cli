from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

from typer.testing import CliRunner

from cae.main import app


def _make_workspace() -> Path:
    root = Path(__file__).parent / ".tmp_diagnose_json"
    root.mkdir(exist_ok=True)
    workspace = root / uuid4().hex
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def test_diagnose_json_outputs_parseable_payload() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "solver start\n"
            "ERROR: increment did not converge\n",
            encoding="utf-8",
        )
        (workspace / "case.sta").write_text(
            "iter=1 resid.=1.0e+0 force%=100 increment size = 1.0e-2\n"
            "iter=2 resid.=2.0e-1 force%=60 increment size = 5.0e-3\n"
            "iter=3 resid.=1.0e-2 force%=20 increment size = 1.0e-3\n",
            encoding="utf-8",
        )
        runner = CliRunner()

        result = runner.invoke(app, ["diagnose", str(workspace), "--json"])

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["success"] is True
        assert payload["issue_count"] >= 1
        assert payload["meta"]["results_dir"] is not None
        assert payload["summary"]["total"] == payload["issue_count"]
        assert payload["issues"][0]["evidence_line"] is not None
        assert payload["issues"][0]["evidence_line"].startswith("case.stderr:")
        assert payload["issues"][0]["evidence_score"] is not None
        assert payload["issues"][0]["evidence_support_count"] is not None
        assert payload["issues"][0]["evidence_support_count"] >= 1
        assert 0.0 <= payload["issues"][0]["evidence_score"] <= 1.0
        assert payload["issues"][0]["evidence_conflict"] is not None
        assert payload["issues"][0]["evidence_score"] < 0.9
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_diagnose_guardrails_option_overrides_default_rules() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "ERROR: increment did not converge\n",
            encoding="utf-8",
        )
        guardrails = workspace / "guardrails.json"
        guardrails.write_text(
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
        runner = CliRunner()

        result = runner.invoke(
            app,
            [
                "diagnose",
                str(workspace),
                "--json",
                "--guardrails",
                str(guardrails),
            ],
        )

        assert result.exit_code == 0
        payload = json.loads(result.stdout)
        assert payload["issue_count"] >= 1
        assert payload["issues"][0]["category"] == "convergence"
        assert payload["issues"][0]["severity"] == "error"
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
