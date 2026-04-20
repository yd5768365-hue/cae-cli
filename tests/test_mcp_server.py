from __future__ import annotations

import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

import cae.mcp_server as mcp_server
from cae.ai.diagnose import DiagnoseResult
from cae.docker import DockerSolverRunResult
from cae.mcp_server import (
    tool_diagnose,
    tool_docker_calculix,
    tool_docker_build_su2_runtime,
    tool_docker_catalog,
    tool_docker_images,
    tool_docker_pull,
    tool_docker_recommend,
    tool_docker_run,
    tool_docker_status,
    tool_health,
    tool_inp_check,
    tool_solve,
)
from cae.solvers.base import SolveResult
from cae.runtimes.docker import ContainerRunResult


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


def test_tool_docker_status_returns_standalone_runtime_info(monkeypatch) -> None:
    class DummyDockerRuntime:
        def inspect(self):
            return {
                "available": True,
                "version": "25.0.0",
                "backend": "wsl",
                "command": ["wsl", "-e", "docker"],
                "use_wsl_paths": True,
                "error": None,
            }

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_status()

    assert payload["ok"] is True
    assert payload["data"]["backend"] == "wsl"
    assert payload["data"]["command"] == ["wsl", "-e", "docker"]


def test_tool_docker_catalog_returns_builtin_aliases() -> None:
    payload = tool_docker_catalog()

    assert payload["ok"] is True
    assert any(item["alias"] == "calculix" for item in payload["data"]["images"])
    assert any(item["alias"] == "openfoam" for item in payload["data"]["images"])
    assert any(item["alias"] == "code-aster" for item in payload["data"]["images"])


def test_tool_docker_catalog_can_filter_by_capability() -> None:
    payload = tool_docker_catalog(capability="cfd", include_experimental=False)

    assert payload["ok"] is True
    assert any(item["alias"] == "openfoam" for item in payload["data"]["images"])
    assert not any(item["alias"] == "su2" for item in payload["data"]["images"])

    runnable = tool_docker_catalog(solver="su2", runnable_only=True)
    assert runnable["ok"] is True
    assert any(item["alias"] == "su2-runtime" for item in runnable["data"]["images"])


def test_tool_docker_recommend_returns_candidates() -> None:
    payload = tool_docker_recommend(query="nonlinear structural contact", limit=3)

    assert payload["ok"] is True
    assert payload["data"]["recommendations"]
    assert payload["data"]["recommendations"][0]["solver"] in {"calculix", "code_aster"}


def test_tool_docker_images_lists_local_images(monkeypatch) -> None:
    class DummyDockerRuntime:
        def list_images(self):
            return ["unifem/calculix-desktop:latest"]

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_images()

    assert payload["ok"] is True
    assert payload["data"]["images"] == ["unifem/calculix-desktop:latest"]


def test_tool_docker_pull_resolves_alias_and_can_set_default(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server.settings, "_data", {})
    monkeypatch.setattr(
        mcp_server.settings,
        "set",
        lambda key, value: mcp_server.settings._data.__setitem__(key, value),
    )

    class DummyDockerRuntime:
        def image_exists(self, image):
            return False

        def pull_image(self, image, *, timeout=3600, use_default_config=False):
            assert image == "unifem/calculix-desktop:latest"
            assert timeout == 12
            assert use_default_config is False
            return ContainerRunResult(
                stdout="pulled",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
                command=["wsl", "-e", "docker", "pull", image],
            )

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_pull(image="calculix", timeout=12, set_default=True)

    assert payload["ok"] is True
    assert payload["data"]["image"] == "unifem/calculix-desktop:latest"
    assert payload["data"]["default_saved"] is True
    assert mcp_server.settings._data["docker_calculix_image"] == "unifem/calculix-desktop:latest"


def test_tool_docker_pull_can_save_existing_local_image_without_refresh(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server.settings, "_data", {})
    monkeypatch.setattr(
        mcp_server.settings,
        "set",
        lambda key, value: mcp_server.settings._data.__setitem__(key, value),
    )

    class DummyDockerRuntime:
        def image_exists(self, image):
            return image == "unifem/calculix-desktop:latest"

        def pull_image(self, image, *, timeout=3600, use_default_config=False):
            raise AssertionError("pull_image should be skipped for existing local image")

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_pull(image="calculix", timeout=12, set_default=True)

    assert payload["ok"] is True
    assert payload["data"]["skipped_pull"] is True
    assert payload["data"]["default_saved"] is True
    assert mcp_server.settings._data["docker_calculix_image"] == "unifem/calculix-desktop:latest"


def test_tool_docker_pull_saves_default_by_solver_family(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server.settings, "_data", {})
    monkeypatch.setattr(
        mcp_server.settings,
        "set",
        lambda key, value: mcp_server.settings._data.__setitem__(key, value),
    )

    class DummyDockerRuntime:
        def image_exists(self, image):
            return image == "simvia/code_aster:stable"

        def pull_image(self, image, *, timeout=3600, use_default_config=False):
            raise AssertionError("pull_image should be skipped for existing local image")

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_pull(image="code-aster", timeout=12, set_default=True)

    assert payload["ok"] is True
    assert payload["data"]["default_key"] == "docker_code_aster_image"
    assert mcp_server.settings._data["docker_code_aster_image"] == "simvia/code_aster:stable"


def test_tool_docker_run_uses_generic_runner(monkeypatch, workspace: Path) -> None:
    cfg = workspace / "case.cfg"
    cfg.write_text("SOLVER=EULER\n", encoding="utf-8")
    out_dir = workspace / "out"

    class DummyDockerRunner:
        def run(self, image, input_path, output_dir, **kwargs):
            assert image == "su2"
            assert input_path == cfg.resolve()
            assert output_dir == out_dir.resolve()
            assert kwargs["command"] == "SU2_CFD case.cfg"
            return DockerSolverRunResult(
                success=True,
                solver="su2",
                image="ghcr.io/su2code/su2/build-su2:250717-1402",
                input_path=cfg,
                output_dir=out_dir,
                command=["SU2_CFD", "case.cfg"],
                output_files=[out_dir / "history.csv"],
                stdout="done",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
            )

    monkeypatch.setattr("cae.mcp_server.DockerSolverRunner", DummyDockerRunner)

    payload = tool_docker_run(
        image="su2",
        input_path=str(cfg),
        output_dir=str(out_dir),
        command="SU2_CFD case.cfg",
    )

    assert payload["ok"] is True
    assert payload["data"]["solver"] == "su2"


def test_tool_docker_build_su2_runtime_sets_default(monkeypatch) -> None:
    monkeypatch.setattr(mcp_server.settings, "_data", {})
    monkeypatch.setattr(
        mcp_server.settings,
        "set",
        lambda key, value: mcp_server.settings._data.__setitem__(key, value),
    )

    class DummyDockerRuntime:
        def build_image(self, *, context_dir, dockerfile, tag, build_args, timeout, pull):
            assert dockerfile.name == "su2-runtime-conda.Dockerfile"
            assert tag == "local/su2-runtime:test"
            assert build_args["SU2_VERSION"] == "8.3.0"
            assert pull is False
            return ContainerRunResult(
                stdout="built",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
                command=["docker", "build"],
            )

    monkeypatch.setattr("cae.mcp_server.DockerRuntime", DummyDockerRuntime)

    payload = tool_docker_build_su2_runtime(
        tag="local/su2-runtime:test",
        pull_base=False,
    )

    assert payload["ok"] is True
    assert payload["data"]["default_saved"] is True
    assert mcp_server.settings._data["docker_su2_image"] == "local/su2-runtime:test"


def test_tool_docker_calculix_is_separate_from_native_solve(monkeypatch, workspace: Path) -> None:
    inp = workspace / "model.inp"
    inp.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")
    out_dir = workspace / "docker_results"
    frd = out_dir / "model.frd"

    class DummyDockerRunner:
        def run(self, inp_file, output_dir, *, image=None, timeout=3600, cpus=None, memory=None):
            output_dir.mkdir(parents=True, exist_ok=True)
            frd.write_text("dummy", encoding="utf-8")
            return SolveResult(
                success=True,
                output_dir=output_dir,
                output_files=[frd],
                stdout="docker ok",
                stderr="",
                returncode=0,
                duration_seconds=0.3,
            )

    monkeypatch.setattr("cae.mcp_server.CalculixDockerRunner", DummyDockerRunner)

    payload = tool_docker_calculix(
        inp_file=str(inp),
        output_dir=str(out_dir),
        image="calculix:test",
        timeout=10,
    )

    assert payload["ok"] is True
    assert payload["data"]["success"] is True
    assert payload["data"]["frd_file"] is not None


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
            "summary": {"total": 0, "execution_plan": []},
            "meta": {"results_dir": str(results_dir)},
        },
    )

    payload = tool_diagnose(results_dir=str(results_dir))

    assert payload["ok"] is True
    assert payload["data"]["success"] is True
    assert payload["data"]["issue_count"] == 0
    assert payload["data"]["agent"]["recommended_next_action"] == "No diagnosis action required."


def test_tool_diagnose_adds_agent_execution_context(monkeypatch, workspace: Path) -> None:
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
            "issue_count": 2,
            "issues": [],
            "summary": {
                "total": 2,
                "blocking_count": 1,
                "needs_review_count": 0,
                "risk_level": "high",
                "execution_plan": [
                    {
                        "step": 1,
                        "triage": "blocking",
                        "category": "boundary_condition",
                        "severity": "error",
                        "confidence": "high",
                        "auto_fixable": False,
                        "action": "Inspect boundary constraints",
                        "evidence_line": "case.stderr:4: zero pivot",
                    },
                    {
                        "step": 2,
                        "triage": "safe_auto_fix",
                        "category": "input_syntax",
                        "severity": "error",
                        "confidence": "high",
                        "auto_fixable": True,
                        "action": "Add missing *STEP block",
                        "evidence_line": "case.stderr:8: missing *STEP",
                    },
                ],
            },
            "meta": {"results_dir": str(results_dir)},
        },
    )

    payload = tool_diagnose(results_dir=str(results_dir))

    assert payload["ok"] is True
    agent = payload["data"]["agent"]
    assert agent["safe_auto_fix_available"] is True
    assert agent["blocking_count"] == 1
    assert agent["risk_level"] == "high"
    assert agent["next_step"]["triage"] == "safe_auto_fix"
    assert agent["next_step"]["source_step"] == 2
    assert agent["recommended_next_action"] == "Add missing *STEP block"


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
