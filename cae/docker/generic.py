from __future__ import annotations

import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from cae.docker.images import (
    get_image_spec_for_reference,
    render_command_template,
    resolve_image_reference,
)
from cae.runtimes import DockerRuntime


@dataclass(frozen=True)
class DockerSolverRunResult:
    success: bool
    solver: str
    image: str
    input_path: Path
    output_dir: Path
    command: list[str]
    output_files: list[Path]
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    error_message: Optional[str] = None


class DockerSolverRunner:
    """Run non-CalculiX solver containers from the Docker image catalog."""

    def __init__(self, runtime: Optional[DockerRuntime] = None) -> None:
        self.runtime = runtime or DockerRuntime()

    def run(
        self,
        image_ref: str,
        input_path: Path,
        output_dir: Path,
        *,
        command: Optional[Sequence[str] | str] = None,
        timeout: int = 3600,
        cpus: Optional[str] = None,
        memory: Optional[str] = None,
        network: str = "none",
    ) -> DockerSolverRunResult:
        image = resolve_image_reference(image_ref)
        spec = get_image_spec_for_reference(image_ref) or get_image_spec_for_reference(image)
        solver = spec.solver if spec else "custom"

        if not input_path.exists():
            return self._error_result(
                solver=solver,
                image=image,
                input_path=input_path,
                output_dir=output_dir,
                message=f"input path not found: {input_path}",
            )

        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        prepared_input = _prepare_input(input_path.resolve(), output_dir)
        command_parts = self._resolve_command(
            command=command,
            image_ref=image_ref,
            input_path=prepared_input,
        )

        run_result = self.runtime.run(
            image=image,
            workdir=output_dir,
            command=command_parts,
            timeout=timeout,
            cpus=cpus,
            memory=memory,
            network=network,
        )

        combined = run_result.stdout + run_result.stderr
        if combined.strip():
            log_path = output_dir / f"docker-{solver}.log"
            log_path.write_text(combined, encoding="utf-8")

        output_files = sorted(f for f in output_dir.rglob("*") if f.is_file())
        error_message = None
        if run_result.returncode != 0:
            error_message = f"Docker solver exit code: {run_result.returncode}"
            if run_result.stderr.strip():
                error_message += f"\n{run_result.stderr.strip()}"

        return DockerSolverRunResult(
            success=run_result.returncode == 0,
            solver=solver,
            image=image,
            input_path=prepared_input,
            output_dir=output_dir,
            command=command_parts,
            output_files=output_files,
            stdout=run_result.stdout,
            stderr=run_result.stderr,
            returncode=run_result.returncode,
            duration_seconds=run_result.duration_seconds,
            error_message=error_message,
        )

    @staticmethod
    def _resolve_command(
        *,
        command: Optional[Sequence[str] | str],
        image_ref: str,
        input_path: Path,
    ) -> list[str]:
        if isinstance(command, str) and command.strip():
            return shlex.split(command)
        if command:
            return list(command)

        spec = get_image_spec_for_reference(image_ref) or get_image_spec_for_reference(resolve_image_reference(image_ref))
        template = spec.command if spec else []
        input_name = input_path.name
        input_stem = input_path.stem if input_path.is_file() else input_path.name
        return render_command_template(
            template,
            input_file=input_name if input_path.is_file() else ".",
            input_name=input_name,
            input_stem=input_stem,
            job_name=input_stem,
        )

    @staticmethod
    def _error_result(
        *,
        solver: str,
        image: str,
        input_path: Path,
        output_dir: Path,
        message: str,
    ) -> DockerSolverRunResult:
        return DockerSolverRunResult(
            success=False,
            solver=solver,
            image=image,
            input_path=input_path,
            output_dir=output_dir,
            command=[],
            output_files=[],
            stdout="",
            stderr="",
            returncode=-1,
            duration_seconds=0.0,
            error_message=message,
        )


def _prepare_input(input_path: Path, output_dir: Path) -> Path:
    if input_path.is_dir():
        if input_path == output_dir:
            return output_dir
        _copy_directory_contents(input_path, output_dir)
        return output_dir

    dest = output_dir / input_path.name
    if dest.resolve() != input_path.resolve():
        shutil.copy2(input_path, dest)
    _copy_known_sidecar_dirs(input_path, output_dir)
    return dest


def _copy_directory_contents(source: Path, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = dest / item.name
        if item.is_dir():
            if target.resolve() == source.resolve():
                continue
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _copy_known_sidecar_dirs(input_path: Path, output_dir: Path) -> None:
    if input_path.suffix.lower() != ".sif":
        return

    mesh_dir = input_path.parent / "mesh"
    if mesh_dir.is_dir():
        _copy_directory_contents(mesh_dir, output_dir / "mesh")
