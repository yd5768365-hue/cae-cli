from __future__ import annotations

import json

from typer.testing import CliRunner

from cae.main import app


def test_inp_check_json_reports_unknown_keyword(tmp_path) -> None:
    inp = tmp_path / "bad.inp"
    inp.write_text("*FOO\n1,2,3\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["inp", "check", str(inp), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["valid"] is False
    assert payload["block_count"] == 1
    assert payload["unknown_keywords"] == ["*FOO"]
    assert payload["blocks"][0]["status"] == "needs_review"
    assert payload["blocks"][0]["issues"][0]["code"] == "unknown_keyword"


def test_inp_check_json_reports_missing_required_argument(tmp_path) -> None:
    inp = tmp_path / "missing_required.inp"
    inp.write_text("*BEAM SECTION\n1,2,3\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["inp", "check", str(inp), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["valid"] is False
    assert payload["missing_required"]
    assert any(
        item["keyword"] == "*BEAM SECTION" and item["argument"] == "ELSET"
        for item in payload["missing_required"]
    )
    assert payload["blocks"][0]["line_start"] == 1
