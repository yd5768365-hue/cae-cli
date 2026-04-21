from __future__ import annotations

import subprocess
import shutil
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

from cae.config import settings
from cae.docker import (
    CalculixDockerRunner,
    DockerSolverRunner,
    list_image_spec_dicts,
    recommend_image_specs,
    resolve_image_command,
    resolve_image_reference,
    solver_config_key,
)
from cae.runtimes.docker import ContainerRunResult, DockerRuntime, _DockerCommand


@pytest.fixture
def workspace() -> Iterator[Path]:
    root = Path(__file__).parent / ".tmp_docker_feature"
    root.mkdir(exist_ok=True)
    path = root / uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_docker_runtime_inspect_reports_wsl_backend(monkeypatch) -> None:
    runtime = DockerRuntime()
    monkeypatch.setattr(
        runtime,
        "_detect_command",
        lambda: _DockerCommand(["wsl", "-e", "docker"], use_wsl_paths=True),
    )
    monkeypatch.setattr(
        runtime,
        "_run_probe",
        lambda command: subprocess.CompletedProcess(
            args=list(command),
            returncode=0,
            stdout="25.0.0\n",
            stderr="",
        ),
    )

    info = runtime.inspect()

    assert info.available is True
    assert info.backend == "wsl"
    assert info.command == ["wsl", "-e", "docker"]
    assert info.use_wsl_paths is True
    assert info.version == "25.0.0"


def test_docker_image_catalog_resolves_alias() -> None:
    catalog = list_image_spec_dicts()

    assert any(item["alias"] == "calculix" for item in catalog)
    assert any(item["alias"] == "openfoam" for item in catalog)
    assert any(item["alias"] == "code-aster" for item in catalog)
    assert resolve_image_reference("calculix") == "unifem/calculix-desktop:latest"
    assert resolve_image_command("calculix-parallelworks", "model") == [
        "/opt/ccx-215/src/ccx_2.15",
        "-i",
        "model",
    ]
    assert resolve_image_command("su2-runtime", "case.cfg") == ["case.cfg"]
    assert resolve_image_reference("openfoam-lite") == "microfluidica/openfoam:11"
    assert resolve_image_reference("custom/image:tag") == "custom/image:tag"
    assert solver_config_key("code_aster") == "docker_code_aster_image"


def test_docker_catalog_filters_and_recommends_solver_domains() -> None:
    cfd_items = list_image_spec_dicts(capability="cfd", include_experimental=False)
    recommended = recommend_image_specs("steady CFD turbulence")
    aerodynamic = recommend_image_specs("external aerodynamic CFD")

    assert any(item["alias"] == "openfoam" for item in cfd_items)
    assert not any(item["alias"] == "su2" for item in cfd_items)
    assert any(item["alias"] == "su2-runtime" for item in list_image_spec_dicts(solver="su2", runnable_only=True))
    assert recommended
    assert recommended[0].alias in {"openfoam", "su2-runtime"}
    assert not any(spec.solver in {"calculix", "code_aster"} for spec in aerodynamic)


def test_docker_pull_uses_isolated_config_for_wsl(monkeypatch) -> None:
    captured: dict[str, list[str]] = {}
    runtime = DockerRuntime()
    monkeypatch.setattr(
        runtime,
        "_detect_command",
        lambda: _DockerCommand(["wsl", "-e", "docker"], use_wsl_paths=True),
    )

    def fake_run(command, *, timeout):
        captured["command"] = command
        return ContainerRunResult(
            stdout="pulled",
            stderr="",
            returncode=0,
            duration_seconds=0.1,
            command=command,
        )

    monkeypatch.setattr(runtime, "_run_docker_command", fake_run)

    result = runtime.pull_image("unifem/calculix-desktop:latest", timeout=9)

    assert result.returncode == 0
    assert captured["command"][:3] == ["wsl", "-e", "sh"]
    assert "DOCKER_CONFIG=/tmp/cae-cli-docker" in captured["command"][-1]
    assert "docker pull unifem/calculix-desktop:latest" in captured["command"][-1]


def test_docker_build_image_converts_paths_for_wsl(monkeypatch, workspace: Path) -> None:
    captured: dict[str, list[str]] = {}
    dockerfile = workspace / "Dockerfile"
    dockerfile.write_text("FROM scratch\n", encoding="utf-8")
    runtime = DockerRuntime()
    monkeypatch.setattr(
        runtime,
        "_detect_command",
        lambda: _DockerCommand(["wsl", "-e", "docker"], use_wsl_paths=True),
    )

    def fake_run(command, *, timeout):
        captured["command"] = command
        return ContainerRunResult(
            stdout="built",
            stderr="",
            returncode=0,
            duration_seconds=0.1,
            command=command,
        )

    monkeypatch.setattr(runtime, "_run_docker_command", fake_run)

    result = runtime.build_image(
        context_dir=workspace,
        dockerfile=dockerfile,
        tag="local/test:latest",
        build_args={"FOO": "bar"},
        timeout=9,
    )

    assert result.returncode == 0
    assert captured["command"][:3] == ["wsl", "-e", "sh"]
    assert "DOCKER_CONFIG=/tmp/cae-cli-docker" in captured["command"][-1]
    assert "local/test:latest" in captured["command"][-1]
    assert "/mnt/" in captured["command"][-1]
    assert "FOO=bar" in captured["command"][-1]


def test_windows_path_to_wsl_converts_drive_path() -> None:
    converted = DockerRuntime.windows_path_to_wsl(Path("D:/CAE-CLI/case"))

    assert converted.endswith("/CAE-CLI/case")
    assert converted.startswith("/mnt/d/")


def test_calculix_docker_runner_requires_image(workspace: Path, monkeypatch) -> None:
    monkeypatch.delenv("CAE_CALCULIX_DOCKER_IMAGE", raising=False)
    monkeypatch.setitem(settings._data, "docker_calculix_image", "")
    monkeypatch.setitem(settings._data, "calculix_docker_image", "")
    inp_file = workspace / "model.inp"
    inp_file.write_text("*NODE\n1,0,0,0\n", encoding="utf-8")

    result = CalculixDockerRunner().run(inp_file, workspace / "out")

    assert result.success is False
    assert "requires an image" in (result.error_message or "")


def test_calculix_docker_runner_runs_through_runtime(workspace: Path) -> None:
    inp_file = workspace / "model.inp"
    inp_file.write_text(
        "*HEADING\n"
        "*NODE\n"
        "1,0,0,0\n"
        "*STEP\n"
        "*STATIC\n"
        "0.1,1.0\n"
        "*END STEP\n",
        encoding="utf-8",
    )
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None):
            (workdir / "model.frd").write_text("fake frd", encoding="utf-8")
            assert image == "calculix:test"
            assert command == ["ccx", "-i", "model"]
            assert cpus == "2"
            assert memory == "4g"
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
                command=["docker", "run"],
            )

    result = CalculixDockerRunner(runtime=DummyRuntime()).run(
        inp_file,
        output_dir,
        image="calculix:test",
        timeout=20,
        cpus="2",
        memory="4g",
    )

    fixed_input = (output_dir / "model.inp").read_text(encoding="utf-8")
    assert result.success is True
    assert result.frd_file is not None
    assert "*NODE FILE" in fixed_input
    assert "*EL FILE" in fixed_input


def test_calculix_docker_runner_uses_catalog_command_for_known_image(workspace: Path) -> None:
    inp_file = workspace / "model.inp"
    inp_file.write_text(
        "*HEADING\n"
        "*NODE\n"
        "1,0,0,0\n"
        "*STEP\n"
        "*STATIC\n"
        "0.1,1.0\n"
        "*END STEP\n",
        encoding="utf-8",
    )
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None):
            (workdir / "model.frd").write_text("fake frd", encoding="utf-8")
            assert image == "parallelworks/calculix:v2.15_exo"
            assert command == ["/opt/ccx-215/src/ccx_2.15", "-i", "model"]
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.1,
                command=["docker", "run"],
            )

    result = CalculixDockerRunner(runtime=DummyRuntime()).run(
        inp_file,
        output_dir,
        image="calculix-parallelworks",
        timeout=20,
    )

    assert result.success is True


def test_generic_docker_runner_uses_catalog_command_and_copies_input(workspace: Path) -> None:
    cfg = workspace / "case.cfg"
    cfg.write_text("SOLVER=EULER\n", encoding="utf-8")
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None, network="none"):
            assert image == "custom/su2-runtime:test"
            assert command == ["SU2_CFD", "case.cfg"]
            assert network == "none"
            assert (workdir / "case.cfg").exists()
            (workdir / "history.csv").write_text("ok", encoding="utf-8")
            return ContainerRunResult(
                stdout="done",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
                command=["docker", "run"],
            )

    result = DockerSolverRunner(runtime=DummyRuntime()).run(
        "custom/su2-runtime:test",
        cfg,
        output_dir,
        command="SU2_CFD case.cfg",
        timeout=30,
    )

    assert result.success is True
    assert result.solver == "custom"
    assert output_dir / "history.csv" in result.output_files


def test_generic_docker_runner_copies_elmer_mesh_sidecar(workspace: Path) -> None:
    case_dir = workspace / "elmer_case"
    mesh_dir = case_dir / "mesh"
    mesh_dir.mkdir(parents=True)
    sif = case_dir / "case.sif"
    sif.write_text('Header\n  Mesh DB "." "mesh"\nEnd\n', encoding="utf-8")
    (mesh_dir / "mesh.header").write_text("4 1 4\n", encoding="utf-8")
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None, network="none"):
            assert image == "eperera/elmerfem:latest"
            assert command == ["ElmerSolver", "case.sif"]
            assert (workdir / "case.sif").exists()
            assert (workdir / "mesh" / "mesh.header").exists()
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
                command=["docker", "run"],
            )

    result = DockerSolverRunner(runtime=DummyRuntime()).run(
        "elmer",
        sif,
        output_dir,
        timeout=30,
    )

    assert result.success is True


def test_generic_docker_runner_copies_su2_mesh_sidecar(workspace: Path) -> None:
    case_dir = workspace / "su2_case"
    mesh_dir = case_dir / "mesh"
    mesh_dir.mkdir(parents=True)
    cfg = case_dir / "case.cfg"
    cfg.write_text(
        "SOLVER= EULER\n"
        "MESH_FILENAME= mesh/plate.su2\n",
        encoding="utf-8",
    )
    (mesh_dir / "plate.su2").write_text("NDIME= 2\n", encoding="utf-8")
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None, network="none"):
            assert image == "local/su2-runtime:8.3.0"
            assert command == ["case.cfg"]
            assert (workdir / "case.cfg").exists()
            assert (workdir / "mesh" / "plate.su2").exists()
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
                command=["docker", "run"],
            )

    result = DockerSolverRunner(runtime=DummyRuntime()).run(
        "su2-runtime",
        cfg,
        output_dir,
        timeout=30,
    )

    assert result.success is True


def test_generic_docker_runner_copies_additional_su2_sidecar_inputs(workspace: Path) -> None:
    case_dir = workspace / "su2_struct_case"
    case_dir.mkdir(parents=True)
    cfg = case_dir / "case.cfg"
    cfg.write_text(
        "SOLVER= ELASTICITY\n"
        "MESH_FILENAME= mesh.su2\n"
        "FEA_FILENAME= material.dat\n"
        "RESTART_FILENAME= direct.dat\n",
        encoding="utf-8",
    )
    (case_dir / "mesh.su2").write_text("NDIME= 2\n", encoding="utf-8")
    (case_dir / "material.dat").write_text("1 1.0\n", encoding="utf-8")
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None, network="none"):
            assert command == ["case.cfg"]
            assert (workdir / "mesh.su2").exists()
            assert (workdir / "material.dat").exists()
            assert not (workdir / "direct.dat").exists()
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
                command=["docker", "run"],
            )

    result = DockerSolverRunner(runtime=DummyRuntime()).run(
        "su2-runtime",
        cfg,
        output_dir,
        timeout=30,
    )

    assert result.success is True


def test_generic_docker_runner_copies_code_aster_export_sidecars(workspace: Path) -> None:
    case_dir = workspace / "code_aster_case"
    case_dir.mkdir(parents=True)
    export_file = case_dir / "case.export"
    export_file.write_text(
        "P actions make_etude\n"
        "F comm case.comm D 1\n"
        "F mmed mesh.med D 20\n"
        "F rmed result.rmed R 80\n",
        encoding="utf-8",
    )
    (case_dir / "case.comm").write_text("DEBUT();\nFIN();\n", encoding="utf-8")
    (case_dir / "mesh.med").write_text("MED", encoding="utf-8")
    output_dir = workspace / "out"

    class DummyRuntime:
        def run(self, *, image, workdir, command, timeout, cpus=None, memory=None, network="none"):
            assert image == "simvia/code_aster:stable"
            assert command == [
                "bash",
                "-lc",
                'source /opt/activate.sh && run_aster "$1"',
                "bash",
                "case.export",
            ]
            assert (workdir / "case.export").exists()
            assert (workdir / "case.comm").exists()
            assert (workdir / "mesh.med").exists()
            assert not (workdir / "result.rmed").exists()
            return ContainerRunResult(
                stdout="ok",
                stderr="",
                returncode=0,
                duration_seconds=0.2,
                command=["docker", "run"],
            )

    result = DockerSolverRunner(runtime=DummyRuntime()).run(
        "code-aster",
        export_file,
        output_dir,
        timeout=30,
    )

    assert result.success is True
