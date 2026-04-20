from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from cae.config import settings
from cae.docker.images import resolve_image_command, resolve_image_reference
from cae.runtimes import DockerRuntime
from cae.solvers.base import SolveResult

_ERROR_MARKERS = ("*ERROR", "Error in ", "error in ", "FATAL", "fatal error")
_WARN_MARKERS = ("*WARNING", "Warning", "warning:")


class CalculixDockerRunner:
    """Run CalculiX in a Docker container as a standalone feature."""

    def __init__(self, runtime: Optional[DockerRuntime] = None) -> None:
        self.runtime = runtime or DockerRuntime()

    def run(
        self,
        inp_file: Path,
        output_dir: Path,
        *,
        image: Optional[str] = None,
        timeout: int = 3600,
        cpus: Optional[str] = None,
        memory: Optional[str] = None,
    ) -> SolveResult:
        resolved_image = self._resolve_image(image)
        if not resolved_image:
            return self._error_result(
                output_dir,
                "Docker CalculiX requires an image. Pass --image, set CAE_CALCULIX_DOCKER_IMAGE, "
                "or configure docker_calculix_image.",
            )

        ok, msg = self._validate_input(inp_file)
        if not ok:
            return self._error_result(output_dir, msg)

        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        job_name = inp_file.stem
        inp_dest = output_dir / inp_file.name
        if inp_dest.resolve() != inp_file.resolve():
            shutil.copy2(inp_file, inp_dest)
        _ensure_frd_output(inp_dest)

        run_result = self.runtime.run(
            image=resolved_image,
            workdir=output_dir,
            command=resolve_image_command(resolved_image, job_name),
            timeout=timeout,
            cpus=cpus,
            memory=memory,
        )

        combined = run_result.stdout + run_result.stderr
        if combined.strip():
            stderr_path = output_dir / f"{job_name}.stderr"
            stderr_path.write_text(combined, encoding="utf-8")

        errors = _extract_lines(combined, _ERROR_MARKERS)
        warnings = _extract_lines(combined, _WARN_MARKERS)
        output_files = sorted(
            f for f in output_dir.iterdir()
            if f.is_file() and f.name != inp_file.name
        )

        has_frd = any(f.suffix == ".frd" for f in output_files)
        success = run_result.returncode == 0 and not errors and has_frd

        error_message: Optional[str] = None
        if errors:
            error_message = "\n".join(errors[:3])
        elif run_result.returncode != 0 and not has_frd:
            error_message = f"Docker CalculiX exit code: {run_result.returncode}; no result file generated."
            if run_result.stderr.strip():
                error_message += f"\n{run_result.stderr.strip()}"
        elif not has_frd:
            error_message = "Docker CalculiX finished but did not generate a .frd result file."

        return SolveResult(
            success=success,
            output_dir=output_dir,
            output_files=output_files,
            stdout=run_result.stdout,
            stderr=run_result.stderr,
            returncode=run_result.returncode,
            duration_seconds=run_result.duration_seconds,
            error_message=error_message,
            warnings=warnings[:10],
        )

    @staticmethod
    def _resolve_image(image: Optional[str]) -> str:
        raw = (
            image
            or os.environ.get("CAE_CALCULIX_DOCKER_IMAGE")
            or settings.get("docker_calculix_image")
            or settings.get("calculix_docker_image")
            or ""
        ).strip()
        return resolve_image_reference(raw) if raw else ""

    @staticmethod
    def _validate_input(inp_file: Path) -> tuple[bool, str]:
        if not inp_file.exists():
            return False, f"file not found: {inp_file}"
        if not inp_file.is_file():
            return False, f"path is not a file: {inp_file}"
        if inp_file.suffix.lower() != ".inp":
            return False, f"unsupported input format '{inp_file.suffix}', expected .inp"
        return True, ""

    @staticmethod
    def _error_result(output_dir: Path, message: str) -> SolveResult:
        return SolveResult(
            success=False,
            output_dir=output_dir,
            output_files=[],
            stdout="",
            stderr="",
            returncode=-1,
            duration_seconds=0.0,
            error_message=message,
        )


def _ensure_frd_output(inp_file: Path) -> None:
    text = inp_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    upper_lines = [line.upper().strip() for line in lines]

    has_node_file = False
    has_el_file = False
    in_step = False
    for line in upper_lines:
        if line.startswith("*STEP"):
            in_step = True
        elif line.startswith("*END") and "STEP" in line:
            in_step = False
        elif in_step:
            if "*NODE FILE" in line:
                has_node_file = True
            if "*EL FILE" in line:
                has_el_file = True

    if has_node_file and has_el_file:
        return

    for i in range(len(lines) - 1, -1, -1):
        if lines[i].upper().strip().startswith("*END") and "STEP" in lines[i].upper():
            additions: list[str] = []
            if not has_node_file:
                additions.extend(["*NODE FILE", "U"])
            if not has_el_file:
                additions.extend(["*EL FILE", "S"])

            for j, line in enumerate(additions):
                lines.insert(i + j, line)

            inp_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
            break


def _extract_lines(text: str, markers: tuple[str, ...]) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if any(marker in line for marker in markers)
    ]
