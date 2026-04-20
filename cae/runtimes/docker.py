from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


@dataclass(frozen=True)
class _DockerCommand:
    prefix: list[str]
    use_wsl_paths: bool = False


@dataclass(frozen=True)
class ContainerRunResult:
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float
    command: list[str]


@dataclass(frozen=True)
class DockerRuntimeInfo:
    available: bool
    version: Optional[str]
    backend: Optional[str]
    command: list[str]
    use_wsl_paths: bool
    error: Optional[str] = None


class DockerRuntime:
    """Run solver containers through Docker, including Docker installed inside WSL."""

    def __init__(
        self,
        command_prefix: Optional[Sequence[str]] = None,
        *,
        use_wsl_paths: Optional[bool] = None,
    ) -> None:
        self._command_prefix = list(command_prefix) if command_prefix else None
        self._use_wsl_paths = use_wsl_paths

    def available(self) -> bool:
        return self._detect_command() is not None

    def inspect(self) -> DockerRuntimeInfo:
        docker = self._detect_command()
        if docker is None:
            return DockerRuntimeInfo(
                available=False,
                version=None,
                backend=None,
                command=[],
                use_wsl_paths=False,
                error=(
                    "Docker CLI is not available. On Windows with Docker inside WSL, "
                    "verify that `wsl -e docker version` works."
                ),
            )

        proc = self._run_probe(docker.prefix + ["version", "--format", "{{.Server.Version}}"])
        version = proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None
        return DockerRuntimeInfo(
            available=proc.returncode == 0 and version is not None,
            version=version,
            backend="wsl" if docker.use_wsl_paths else "native",
            command=docker.prefix,
            use_wsl_paths=docker.use_wsl_paths,
            error=None if proc.returncode == 0 else (proc.stderr.strip() or "docker probe failed"),
        )

    def version(self) -> Optional[str]:
        return self.inspect().version

    def run(
        self,
        *,
        image: str,
        workdir: Path,
        command: Sequence[str],
        timeout: int,
        container_workdir: str = "/work",
        cpus: Optional[str] = None,
        memory: Optional[str] = None,
        network: str = "none",
    ) -> ContainerRunResult:
        if not image.strip():
            return ContainerRunResult(
                stdout="",
                stderr="docker image must not be empty",
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )

        docker = self._detect_command()
        if docker is None:
            return ContainerRunResult(
                stdout="",
                stderr=(
                    "Docker CLI is not available. On Windows with Docker inside WSL, "
                    "verify that `wsl -e docker version` works."
                ),
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )

        host_workdir = self._host_path_for_docker(workdir, use_wsl_paths=docker.use_wsl_paths)
        docker_cmd = [
            *docker.prefix,
            "run",
            "--rm",
            "--network",
            network,
            "-v",
            f"{host_workdir}:{container_workdir}",
            "-w",
            container_workdir,
        ]
        if cpus:
            docker_cmd.extend(["--cpus", cpus])
        if memory:
            docker_cmd.extend(["--memory", memory])
        docker_cmd.extend([image, *command])

        return self._run_docker_command(docker_cmd, timeout=timeout)

    def pull_image(
        self,
        image: str,
        *,
        timeout: int = 3600,
        use_default_config: bool = False,
    ) -> ContainerRunResult:
        if not image.strip():
            return ContainerRunResult(
                stdout="",
                stderr="docker image must not be empty",
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )
        docker = self._detect_command()
        if docker is None:
            return ContainerRunResult(
                stdout="",
                stderr=(
                    "Docker CLI is not available. On Windows with Docker inside WSL, "
                    "verify that `wsl -e docker version` works."
                ),
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )
        return self._pull_image_with_command(
            docker,
            image,
            timeout=timeout,
            use_default_config=use_default_config,
        )

    def image_exists(self, image: str) -> bool:
        if not image.strip():
            return False
        result = self.command(["image", "inspect", image], timeout=30)
        return result.returncode == 0

    def list_images(self) -> list[str]:
        result = self.command(
            ["image", "ls", "--format", "{{.Repository}}:{{.Tag}}"],
            timeout=30,
        )
        if result.returncode != 0:
            return []
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and line.strip() != "<none>:<none>"
        ]

    def build_image(
        self,
        *,
        context_dir: Path,
        tag: str,
        dockerfile: Optional[Path] = None,
        build_args: Optional[dict[str, str]] = None,
        timeout: int = 3600,
        pull: bool = False,
    ) -> ContainerRunResult:
        if not tag.strip():
            return ContainerRunResult(
                stdout="",
                stderr="docker image tag must not be empty",
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )

        docker = self._detect_command()
        if docker is None:
            return ContainerRunResult(
                stdout="",
                stderr=(
                    "Docker CLI is not available. On Windows with Docker inside WSL, "
                    "verify that `wsl -e docker version` works."
                ),
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )

        context = self._host_path_for_docker(context_dir, use_wsl_paths=docker.use_wsl_paths)
        build_args_list = ["build", "--pull=false" if not pull else "--pull=true", "-t", tag]
        if dockerfile is not None:
            build_args_list.extend(
                [
                    "-f",
                    self._host_path_for_docker(dockerfile, use_wsl_paths=docker.use_wsl_paths),
                ]
            )
        for key, value in (build_args or {}).items():
            build_args_list.extend(["--build-arg", f"{key}={value}"])
        build_args_list.append(context)

        if docker.use_wsl_paths and docker.prefix[:2] == ["wsl", "-e"] and docker.prefix[-1] == "docker":
            script = (
                "mkdir -p /tmp/cae-cli-docker && "
                f"DOCKER_CONFIG=/tmp/cae-cli-docker docker {shlex.join(build_args_list)}"
            )
            return self._run_docker_command([*docker.prefix[:-1], "sh", "-lc", script], timeout=timeout)

        return self._run_docker_command([*docker.prefix, *build_args_list], timeout=timeout)

    def command(self, args: Sequence[str], *, timeout: int = 3600) -> ContainerRunResult:
        docker = self._detect_command()
        if docker is None:
            return ContainerRunResult(
                stdout="",
                stderr=(
                    "Docker CLI is not available. On Windows with Docker inside WSL, "
                    "verify that `wsl -e docker version` works."
                ),
                returncode=-1,
                duration_seconds=0.0,
                command=[],
            )
        return self._run_docker_command([*docker.prefix, *args], timeout=timeout)

    @staticmethod
    def _run_docker_command(docker_cmd: list[str], *, timeout: int) -> ContainerRunResult:
        start = time.monotonic()
        try:
            proc = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return ContainerRunResult(
                stdout=_clean_process_text(proc.stdout),
                stderr=_clean_process_text(proc.stderr),
                returncode=proc.returncode,
                duration_seconds=time.monotonic() - start,
                command=docker_cmd,
            )
        except subprocess.TimeoutExpired as exc:
            return ContainerRunResult(
                stdout=_clean_process_text(exc.stdout),
                stderr=f"Docker run timed out after {timeout}s",
                returncode=-1,
                duration_seconds=time.monotonic() - start,
                command=docker_cmd,
            )
        except OSError as exc:
            return ContainerRunResult(
                stdout="",
                stderr=str(exc),
                returncode=-1,
                duration_seconds=time.monotonic() - start,
                command=docker_cmd,
            )

    def _detect_command(self) -> Optional[_DockerCommand]:
        if self._command_prefix:
            use_wsl = self._use_wsl_paths
            if use_wsl is None:
                lowered = [part.lower() for part in self._command_prefix[:3]]
                use_wsl = "wsl" in lowered[0]
            return _DockerCommand(self._command_prefix, bool(use_wsl))

        native = _DockerCommand(["docker"], use_wsl_paths=False)
        if shutil.which("docker") and self._probe_ok(native):
            return native

        wsl_name = "wsl.exe" if os.name == "nt" else "wsl"
        if shutil.which(wsl_name) or shutil.which("wsl"):
            wsl = _DockerCommand(["wsl", "-e", "docker"], use_wsl_paths=True)
            if self._probe_ok(wsl):
                return wsl
        return None

    def _pull_image_with_command(
        self,
        docker: _DockerCommand,
        image: str,
        *,
        timeout: int,
        use_default_config: bool,
    ) -> ContainerRunResult:
        if (
            not use_default_config
            and docker.use_wsl_paths
            and docker.prefix[:2] == ["wsl", "-e"]
            and docker.prefix[-1] == "docker"
        ):
            # Public pulls should not be blocked by a broken Windows Desktop credential helper
            # referenced from WSL ~/.docker/config.json.
            script = (
                "mkdir -p /tmp/cae-cli-docker && "
                f"DOCKER_CONFIG=/tmp/cae-cli-docker docker pull {shlex.quote(image)}"
            )
            return self._run_docker_command([*docker.prefix[:-1], "sh", "-lc", script], timeout=timeout)
        return self._run_docker_command([*docker.prefix, "pull", image], timeout=timeout)

    def _probe_ok(self, docker: _DockerCommand) -> bool:
        proc = self._run_probe(docker.prefix + ["version", "--format", "{{.Server.Version}}"])
        return proc.returncode == 0 and bool(proc.stdout.strip())

    @staticmethod
    def _run_probe(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                list(command),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return subprocess.CompletedProcess(list(command), returncode=1, stdout="", stderr="")

    @classmethod
    def _host_path_for_docker(cls, path: Path, *, use_wsl_paths: bool) -> str:
        resolved = path.resolve()
        if use_wsl_paths:
            return cls.windows_path_to_wsl(resolved)
        return str(resolved)

    @staticmethod
    def windows_path_to_wsl(path: Path) -> str:
        raw = str(path.resolve())
        if len(raw) >= 2 and raw[1] == ":":
            drive = raw[0].lower()
            rest = raw[2:].replace("\\", "/").lstrip("/")
            return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
        return raw.replace("\\", "/")


def _clean_process_text(text: str | bytes | None) -> str:
    if text is None:
        return ""
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="replace")
    return text.replace("\x00", "")
