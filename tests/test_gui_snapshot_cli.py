from __future__ import annotations

import json

from typer.testing import CliRunner

from cae.main import app
from cae.runtimes import ContainerRunResult, DockerRuntimeInfo


class _FakeDockerRuntime:
    def inspect(self) -> DockerRuntimeInfo:
        return DockerRuntimeInfo(
            available=True,
            version="25.0.0",
            backend="wsl",
            command=["wsl", "-e", "docker"],
            use_wsl_paths=True,
        )

    def list_images(self) -> list[str]:
        return ["cae-cli:latest"]

    def command(self, args, *, timeout=3600) -> ContainerRunResult:
        return ContainerRunResult(
            stdout="cae-cli:latest\t123MB\n",
            stderr="",
            returncode=0,
            duration_seconds=0.01,
            command=["docker", *args],
        )


def test_gui_snapshot_outputs_real_project_state(tmp_path, monkeypatch) -> None:
    import cae.gui_snapshot as gui_snapshot

    monkeypatch.setattr(gui_snapshot, "DockerRuntime", _FakeDockerRuntime)
    monkeypatch.setattr(gui_snapshot, "_list_ollama_models", lambda: [])
    inp = tmp_path / "model.inp"
    inp.write_text(
        "*HEADING\ndemo\n*NODE\n1,0,0,0\n*ELEMENT, TYPE=C3D8\n1,1,1,1,1,1,1,1,1\n*ENDSTEP\n",
        encoding="utf-8",
    )
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "case.frd").write_text("real result", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "fake.frd").write_text("should be ignored", encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["gui", "snapshot", "--project-root", str(tmp_path), "--inp", str(inp), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["success"] is True
    assert payload["active_input"] == "model.inp"
    assert payload["assets"]["input_files"] == 1
    assert payload["assets"]["result_files"] == 1
    assert payload["inp"]["node_count"] == 1
    assert payload["inp"]["element_count"] == 1
    assert payload["inp"]["unknown_keywords"] == ["*ENDSTEP"]
    assert payload["models"]["active"] == payload["config"]["active_model"]
    assert isinstance(payload["models"]["available"], list)
    assert payload["docker"]["available"] is True
    assert payload["docker"]["local_image_count"] == 1
