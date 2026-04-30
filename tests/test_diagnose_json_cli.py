from __future__ import annotations

import json
import re
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


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_diagnose_json_outputs_parseable_payload() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "solver start\nERROR: increment did not converge\n",
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
        assert payload["issues"][0]["evidence_source_trust"] is not None
        assert 0.0 <= payload["issues"][0]["evidence_source_trust"] <= 1.0
        assert payload["issues"][0]["evidence_support_count"] is not None
        assert payload["issues"][0]["evidence_support_count"] >= 1
        assert 0.0 <= payload["issues"][0]["evidence_score"] <= 1.0
        assert payload["issues"][0]["evidence_conflict"] is not None
        assert "history_hits" in payload["issues"][0]
        assert "history_avg_score" in payload["issues"][0]
        assert "history_conflict_rate" in payload["issues"][0]
        assert "history_similarity" in payload["issues"][0]
        assert "history_similar_hits" in payload["issues"][0]
        assert "history_similar_conflict_rate" in payload["issues"][0]
        assert payload["issues"][0]["evidence_score"] < 0.9
        assert payload["routing"]["route"] == "convergence_tuning"
        assert payload["agent"]["selected_route_execution"]["selection_reason"]
        assert "branch_score_breakdown" in payload["routing"]["post_route_step"]
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


def test_diagnose_text_output_includes_evidence_fields() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "solver start\nERROR: increment did not converge\n",
            encoding="utf-8",
        )
        (workspace / "case.sta").write_text(
            "iter=1 resid.=1.0e+0 force%=100 increment size = 1.0e-2\n"
            "iter=2 resid.=2.0e-1 force%=60 increment size = 5.0e-3\n"
            "iter=3 resid.=1.0e-2 force%=20 increment size = 1.0e-3\n",
            encoding="utf-8",
        )
        runner = CliRunner()

        result = runner.invoke(app, ["diagnose", str(workspace)])

        assert result.exit_code == 0
        output = _strip_ansi(result.stdout)
        assert "evidence:" in output
        assert "line=case.stderr:" in output
        assert re.search(r"score=\d+\.\d{2}", output) is not None
        assert re.search(r"support=\d+", output) is not None
        assert re.search(r"trust=\d+\.\d{2}", output) is not None
        assert "evidence_conflict:" in output
        assert "Agent 路由" in output
        assert "路线: convergence_tuning" in output
        assert "选择原因:" in output
        assert "选择评分:" in output
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_diagnose_fix_flag_applies_safe_autofix_without_prompt() -> None:
    workspace = _make_workspace()
    try:
        inp_file = workspace / "model.inp"
        inp_file.write_text(
            "*HEADING\n*MATERIAL, NAME=STEEL\n*DENSITY\n7.85e-09\n",
            encoding="utf-8",
        )
        (workspace / "case.stderr").write_text(
            "ERROR: no elastic constants were assigned to material STEEL\n",
            encoding="utf-8",
        )
        runner = CliRunner()

        result = runner.invoke(app, ["diagnose", str(workspace), "-i", str(inp_file), "--fix"])

        assert result.exit_code == 0
        fixed_file = workspace / "model_fixed.inp"
        backup_file = workspace / "model_original.inp"
        assert fixed_file.exists()
        assert backup_file.exists()
        assert "*ELASTIC" in fixed_file.read_text(encoding="utf-8")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def test_diagnose_json_history_db_accumulates_hits() -> None:
    workspace = _make_workspace()
    try:
        (workspace / "case.stderr").write_text(
            "ERROR: increment did not converge\n",
            encoding="utf-8",
        )
        history_db = workspace / "diagnosis_history.db"
        runner = CliRunner()

        first = runner.invoke(
            app,
            [
                "diagnose",
                str(workspace),
                "--json",
                "--history-db",
                str(history_db),
            ],
        )
        second = runner.invoke(
            app,
            [
                "diagnose",
                str(workspace),
                "--json",
                "--history-db",
                str(history_db),
            ],
        )

        assert first.exit_code == 0
        assert second.exit_code == 0
        payload = json.loads(second.stdout)
        assert payload["issue_count"] >= 1
        assert any((issue.get("history_hits") or 0) >= 1 for issue in payload["issues"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
