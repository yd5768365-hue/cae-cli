"""
CalculiX 求解器单元测试
不需要真正安装 CalculiX — 通过 mock 隔离子进程调用。
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cae.solvers.base import BaseSolver, SolveResult
from cae.solvers.calculix import CalculixSolver
from cae.solvers.registry import get_solver, list_solvers


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

@pytest.fixture
def solver() -> CalculixSolver:
    return CalculixSolver()


@pytest.fixture
def sample_inp(tmp_path: Path) -> Path:
    """最小化有效 .inp 文件（不执行真实求解）。"""
    f = tmp_path / "test_job.inp"
    f.write_text("** dummy inp\n*Node\n1, 0, 0, 0\n")
    return f


@pytest.fixture
def fake_binary(tmp_path: Path) -> Path:
    """模拟 ccx 可执行文件（仅文件存在，不可真正运行）。"""
    b = tmp_path / "ccx"
    b.write_text("#!/bin/sh\necho fake ccx")
    b.chmod(0o755)
    return b


# ------------------------------------------------------------------ #
# CalculixSolver 基础属性
# ------------------------------------------------------------------ #

class TestCalculixSolverBasics:
    def test_name(self, solver: CalculixSolver) -> None:
        assert solver.name == "calculix"

    def test_supported_formats(self, solver: CalculixSolver) -> None:
        assert ".inp" in solver.supported_formats()

    def test_description_not_empty(self, solver: CalculixSolver) -> None:
        assert len(solver.description) > 0

    def test_is_base_solver(self, solver: CalculixSolver) -> None:
        assert isinstance(solver, BaseSolver)


# ------------------------------------------------------------------ #
# 安装状态检测
# ------------------------------------------------------------------ #

class TestInstallationCheck:
    def test_not_installed_when_no_binary(self, solver: CalculixSolver, tmp_path: Path) -> None:
        """找不到二进制文件时返回 False。"""
        with (
            patch("cae.solvers.calculix.settings") as mock_settings,
            patch.object(solver, "_find_wsl_ccx", return_value=None),
        ):
            mock_settings.solvers_dir = tmp_path / "empty"
            # Patch Path.is_file and Path.exists to return False for all paths
            def fake_is_file(self):
                return False
            def fake_exists(self):
                return False
            with (
                patch.object(Path, "is_file", fake_is_file),
                patch.object(Path, "exists", fake_exists),
                patch("cae.solvers.calculix.shutil.which", return_value=None),
            ):
                assert solver.check_installation() is False

    def test_installed_when_bundled_binary_exists(
        self, solver: CalculixSolver, fake_binary: Path, tmp_path: Path
    ) -> None:
        """捆绑路径下有文件时返回 True。"""
        calculix_dir = tmp_path / "calculix"
        calculix_dir.mkdir()
        ccx = calculix_dir / "ccx"
        ccx.write_text("")
        ccx.chmod(0o755)

        with patch("cae.solvers.calculix.settings") as mock_settings:
            mock_settings.solvers_dir = tmp_path
            assert solver.check_installation() is True

    def test_installed_when_system_binary_found(
        self, solver: CalculixSolver, tmp_path: Path
    ) -> None:
        """系统 PATH 中有 ccx 时返回 True。"""
        with (
            patch("cae.solvers.calculix.settings") as mock_settings,
            patch("cae.solvers.calculix.shutil.which", return_value="/usr/bin/ccx"),
        ):
            mock_settings.solvers_dir = tmp_path / "empty"
            assert solver.check_installation() is True


# ------------------------------------------------------------------ #
# 输入校验
# ------------------------------------------------------------------ #

class TestInputValidation:
    def test_rejects_nonexistent_file(
        self, solver: CalculixSolver, tmp_path: Path
    ) -> None:
        ok, msg = solver.validate_input(tmp_path / "ghost.inp")
        assert ok is False
        assert "不存在" in msg

    def test_rejects_wrong_extension(
        self, solver: CalculixSolver, tmp_path: Path
    ) -> None:
        f = tmp_path / "model.step"
        f.write_text("")
        ok, msg = solver.validate_input(f)
        assert ok is False
        assert "不支持" in msg or ".step" in msg

    def test_accepts_valid_inp(
        self, solver: CalculixSolver, sample_inp: Path
    ) -> None:
        ok, msg = solver.validate_input(sample_inp)
        assert ok is True
        assert msg == ""


# ------------------------------------------------------------------ #
# 求解流程（mock subprocess）
# ------------------------------------------------------------------ #

class TestSolveWithMock:
    def _make_proc(self, returncode=0, stdout="", stderr="") -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.stdout = stdout
        proc.stderr = stderr
        return proc

    def _mock_frd(self, output_dir: Path, job: str) -> Path:
        """在 output_dir 下创建假 .frd 文件，模拟求解器输出。"""
        frd = output_dir / f"{job}.frd"
        frd.write_text("** fake frd")
        return frd

    def test_successful_solve(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        output_dir.mkdir()

        proc = self._make_proc(stdout="Job finished\n")
        with (
            patch.object(solver, "_find_binary", return_value=Path("/usr/bin/ccx")),
            patch("subprocess.run", return_value=proc) as mock_run,
        ):
            # Pre-create .frd so solver thinks it succeeded
            self._mock_frd(output_dir, "test_job")
            result = solver.solve(sample_inp, output_dir)

        assert result.success is True
        assert result.returncode == 0
        assert result.error_message is None
        mock_run.assert_called_once()

    def test_failed_solve_with_error_marker(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        proc = self._make_proc(returncode=0, stdout="*ERROR in umatj\nsome detail\n")
        with (
            patch.object(solver, "_find_binary", return_value=Path("/usr/bin/ccx")),
            patch("subprocess.run", return_value=proc),
        ):
            result = solver.solve(sample_inp, output_dir)

        assert result.success is False
        assert result.error_message is not None
        assert "*ERROR" in result.error_message

    def test_failed_solve_nonzero_exit(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        proc = self._make_proc(returncode=1, stdout="Something went wrong")
        with (
            patch.object(solver, "_find_binary", return_value=Path("/usr/bin/ccx")),
            patch("subprocess.run", return_value=proc),
        ):
            result = solver.solve(sample_inp, output_dir)

        assert result.success is False
        assert result.returncode == 1

    def test_solve_timeout(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        with (
            patch.object(solver, "_find_binary", return_value=Path("/usr/bin/ccx")),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ccx", 1)),
        ):
            result = solver.solve(sample_inp, output_dir, timeout=1)

        assert result.success is False
        assert "超时" in (result.error_message or "")

    def test_no_binary_returns_error_result(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        with patch.object(solver, "_find_binary", return_value=None):
            result = solver.solve(sample_inp, tmp_path / "results")

        assert result.success is False
        assert "cae install" in (result.error_message or "")

    def test_warnings_collected(
        self, solver: CalculixSolver, sample_inp: Path, tmp_path: Path
    ) -> None:
        output_dir = tmp_path / "results"
        proc = self._make_proc(
            stdout="*WARNING: check mesh quality\n*WARNING: step not converged\n"
        )
        with (
            patch.object(solver, "_find_binary", return_value=Path("/usr/bin/ccx")),
            patch("subprocess.run", return_value=proc),
        ):
            result = solver.solve(sample_inp, output_dir)

        # warnings collected even if failed
        assert len(result.warnings) >= 2


# ------------------------------------------------------------------ #
# SolveResult 辅助属性
# ------------------------------------------------------------------ #

class TestSolveResult:
    def _make_result(self, files: list[str], tmp_path: Path) -> SolveResult:
        output_files = []
        for name in files:
            f = tmp_path / name
            f.write_text("")
            output_files.append(f)
        return SolveResult(
            success=True,
            output_dir=tmp_path,
            output_files=output_files,
            stdout="",
            stderr="",
            returncode=0,
            duration_seconds=12.5,
        )

    def test_frd_file_found(self, tmp_path: Path) -> None:
        r = self._make_result(["job.frd", "job.dat"], tmp_path)
        assert r.frd_file is not None
        assert r.frd_file.suffix == ".frd"

    def test_dat_file_found(self, tmp_path: Path) -> None:
        r = self._make_result(["job.frd", "job.dat"], tmp_path)
        assert r.dat_file is not None
        assert r.dat_file.suffix == ".dat"

    def test_no_frd_returns_none(self, tmp_path: Path) -> None:
        r = self._make_result(["job.dat"], tmp_path)
        assert r.frd_file is None

    @pytest.mark.parametrize("seconds, expected", [
        (0.5,  "0.5s"),
        (59.9, "59.9s"),
        (75.0, "1m 15s"),
    ])
    def test_duration_str(self, seconds: float, expected: str, tmp_path: Path) -> None:
        r = self._make_result([], tmp_path)
        r.duration_seconds = seconds
        assert r.duration_str == expected


# ------------------------------------------------------------------ #
# 注册表
# ------------------------------------------------------------------ #

class TestRegistry:
    def test_get_calculix(self) -> None:
        s = get_solver("calculix")
        assert isinstance(s, CalculixSolver)

    def test_get_case_insensitive(self) -> None:
        s = get_solver("CALCULIX")
        assert isinstance(s, CalculixSolver)

    def test_unknown_solver_raises(self) -> None:
        with pytest.raises(ValueError, match="未知求解器"):
            get_solver("unknown_solver_xyz")

    def test_list_solvers_returns_list(self) -> None:
        solvers = list_solvers()
        assert isinstance(solvers, list)
        assert len(solvers) >= 1
        assert all("name" in s for s in solvers)
        assert all("installed" in s for s in solvers)