from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

import cae.mcp_server as mcp_server
from cae.ai.diagnose import DiagnoseResult
from cae.mcp_server import tool_diagnose, tool_health, tool_inp_check, tool_solve
from cae.solvers.base import SolveResult


@pytest.fixture
def workspace() -> Iterator[Path]:
    root = Path(__file__).parent / ".tmp_mcp_server"
    root.mkdir(exist_ok=True)
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_tool_health_returns_solver_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        "cae.mcp_server.list_solvers",
        lambda: [
            {
                "name": "calculix",
                "installed": True,
                "version": "2.23",
                "formats": [".inp"],
                "description": "CalculiX",
            }
        ],
    )

    payload = tool_health()

    assert payload["ok"] is True
    assert payload["data"]["service"] == "cae-cli-mcp"
    assert "calculix" in payload["data"]["installed_solvers"]


def test_tool_solve_returns_error_for_missing_inp() -> None:
    payload = tool_solve(inp_file="D:/not-exists/abc.inp")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "not_found"


def test_tool_solve_returns_error_for_empty_inp() -> None:
    payload = tool_solve(inp_file="")

    assert payload["ok"] is False
    assert payload["error"]["code"] == "invalid_input"


def test_tool_solve_returns_structured_result(monkeypatch, workspace: Path) -> None:
    inp = workspace / "model.inp"
    inp.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    out_dir = workspace / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    frd = out_dir / "model.frd"
    frd.write_text("dummy", encoding="utf-8")

    class DummySolver:
        def solve(
            self,
            inp_file: Path,
            output_dir: Path,
            *,
            timeout: int = 3600,
            **kwargs,
        ):
            return SolveResult(
                success=True,
                output_dir=output_dir,
                output_files=[frd],
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=1.2,
                warnings=[],
            )

    monkeypatch.setattr("cae.mcp_server.get_solver", lambda name: DummySolver())

    payload = tool_solve(inp_file=str(inp), output_dir=str(out_dir))

    assert payload["ok"] is True
    data = payload["data"]
    assert data["success"] is True
    assert data["frd_file"] is not None
    assert data["returncode"] == 0


def test_tool_solve_does_not_persist_solver_path(monkeypatch, workspace: Path) -> None:
    monkeypatch.setattr(mcp_server.settings, "_data", {"solver_path": "original-ccx"})

    inp = workspace / "model.inp"
    inp.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    out_dir = workspace / "results"
    fake_solver_path = workspace / "ccx.exe"
    fake_solver_path.write_text("fake", encoding="utf-8")

    class DummySolver:
        def solve(
            self,
            inp_file: Path,
            output_dir: Path,
            *,
            timeout: int = 3600,
            **kwargs,
        ):
            return SolveResult(
                success=True,
                output_dir=output_dir,
                output_files=[],
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
            )

    monkeypatch.setattr("cae.mcp_server.get_solver", lambda name: DummySolver())

    payload = tool_solve(
        inp_file=str(inp),
        output_dir=str(out_dir),
        solver_path=str(fake_solver_path),
    )

    assert payload["ok"] is True
    assert mcp_server.settings._data["solver_path"] == "original-ccx"


def test_tool_solve_wraps_solver_exceptions(monkeypatch, workspace: Path) -> None:
    inp = workspace / "model.inp"
    inp.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")

    class FailingSolver:
        def solve(
            self,
            inp_file: Path,
            output_dir: Path,
            *,
            timeout: int = 3600,
            **kwargs,
        ):
            raise RuntimeError("solver crashed")

    monkeypatch.setattr("cae.mcp_server.get_solver", lambda name: FailingSolver())

    payload = tool_solve(inp_file=str(inp), output_dir=str(workspace / "results"))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "solve_failed"
    assert "solver crashed" in payload["error"]["message"]


def test_tool_diagnose_returns_json_payload(monkeypatch, workspace: Path) -> None:
    results_dir = workspace / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        "cae.mcp_server.diagnose_results",
        lambda *args, **kwargs: DiagnoseResult(success=True),
    )
    monkeypatch.setattr(
        "cae.mcp_server.diagnosis_result_to_dict",
        lambda result, **kwargs: {
            "success": True,
            "issue_count": 0,
            "issues": [],
            "summary": {"total": 0},
            "meta": {"results_dir": str(results_dir)},
        },
    )

    payload = tool_diagnose(results_dir=str(results_dir))

    assert payload["ok"] is True
    assert payload["data"]["success"] is True
    assert payload["data"]["issue_count"] == 0


def test_tool_diagnose_wraps_diagnosis_exceptions(monkeypatch, workspace: Path) -> None:
    results_dir = workspace / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    def fail(*args, **kwargs):
        raise RuntimeError("diagnosis crashed")

    monkeypatch.setattr("cae.mcp_server.diagnose_results", fail)

    payload = tool_diagnose(results_dir=str(results_dir))

    assert payload["ok"] is False
    assert payload["error"]["code"] == "diagnose_failed"
    assert "diagnosis crashed" in payload["error"]["message"]


def test_tool_inp_check_reports_unknown_keyword(workspace: Path) -> None:
    inp = workspace / "x.inp"
    inp.write_text("*FOO\n1,2,3\n", encoding="utf-8")

    payload = tool_inp_check(inp_file=str(inp))

    assert payload["ok"] is True
    assert payload["data"]["valid"] is False
    assert "*FOO" in payload["data"]["unknown_keywords"]
