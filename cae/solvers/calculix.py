# CalculiX 实现
"""
CalculiX 求解器实现
支持 Abaqus 兼容的 .inp 格式，输出 .frd（结果）和 .dat（数据）文件。

二进制查找优先级：
  1. ~/.local/share/cae-cli/solvers/calculix/ccx  （cae install 安装的）
  2. 系统 PATH 中的 ccx / ccx_2.21 等
  3. MSYS2/MinGW 常见路径中的 ccx
  4. WSL 中的 ccx（如果可用）
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from .base import BaseSolver, SolveResult
from ..config import settings

# CalculiX 输出中标志错误的关键词
_ERROR_MARKERS = ("*ERROR", "Error in ", "error in ", "FATAL", "fatal error")
# 标志警告的关键词
_WARN_MARKERS = ("*WARNING", "Warning", "warning:")

# 系统 PATH 中常见的 CalculiX 可执行文件名
_CCX_NAMES = ["ccx", "ccx_2.21", "ccx_2.20", "ccx_2.19", "ccx_2.18", "CalculiX"]

# MSYS2/MinGW 常见安装路径
_MSYS2_PATHS = [
    Path("D:/Apps/tools/msys/ucrt64/bin/ccx.exe"),
    Path("D:/Apps/tools/msys/mingw64/bin/ccx.exe"),
    Path("C:/msys64/ucrt64/bin/ccx.exe"),
    Path("C:/msys64/mingw64/bin/ccx.exe"),
    Path("C:/msys2/ucrt64/bin/ccx.exe"),
    Path("C:/msys2/mingw64/bin/ccx.exe"),
    # 项目目录下的 ccx
    Path("D:/CAE-CLI/cae-cli/cxx.exe/ccx.exe"),
]


class CalculixSolver(BaseSolver):
    """
    CalculiX FEA 求解器封装。

    CalculiX 命令行用法：
        ccx -i <job_name>
    其中 <job_name> 是不含 .inp 后缀的文件名。
    求解器在当前工作目录下生成同名的 .frd / .dat / .cvg / .sta 文件。
    """

    name = "calculix"
    description = "CalculiX — 开源 FEA 求解器，兼容 Abaqus .inp 格式"

    # ------------------------------------------------------------------ #
    # 二进制查找
    # ------------------------------------------------------------------ #

    @functools.lru_cache(maxsize=1)
    def _find_binary(self) -> Optional[Path]:
        # 1. cae install 安装的捆绑二进制（~/.cae-cli/solvers/calculix/bin/）
        for candidate in [
            settings.solvers_dir / "calculix" / "bin" / "ccx",
            settings.solvers_dir / "calculix" / "bin" / "ccx.exe",  # Windows
            settings.solvers_dir / "calculix" / "ccx",
            settings.solvers_dir / "calculix" / "ccx.exe",  # 兼容旧版本
        ]:
            if candidate.is_file():
                return candidate

        # 1.5. 项目本地的 ccx.exe（独立运行版本，带 DLL）
        local_ccx = Path("D:/CAE-CLI/cae-cli/cxx.exe/ccx.exe")
        if local_ccx.is_file():
            return local_ccx.resolve()

        # 2. 项目目录下的 ccx
        for candidate in _MSYS2_PATHS:
            if candidate.exists():
                return candidate.resolve()

        # 3. 系统 PATH
        for name in _CCX_NAMES:
            found = shutil.which(name)
            if found:
                return Path(found)

        # 4. WSL 中的 ccx
        wsl_ccx = self._find_wsl_ccx()
        if wsl_ccx:
            return wsl_ccx

        return None

    def _find_wsl_ccx(self) -> Optional[Path]:
        """检测 WSL 中是否安装了 ccx"""
        try:
            result = subprocess.run(
                ["wsl", "-e", "which", "ccx"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # 返回特殊标记表示使用 WSL
                return Path("WSL:ccx")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def _is_wsl(self, binary: Path) -> bool:
        """检查是否使用 WSL"""
        return str(binary).startswith("WSL:")

    # ------------------------------------------------------------------ #
    # BaseSolver 接口实现
    # ------------------------------------------------------------------ #

    def check_installation(self) -> bool:
        return self._find_binary() is not None

    def get_version(self) -> Optional[str]:
        binary = self._find_binary()
        if not binary:
            return None
        try:
            # ccx 无参数运行时会打印版本到 stderr 然后以非零退出
            proc = subprocess.run(
                [str(binary)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = proc.stdout + proc.stderr
            for line in output.splitlines():
                low = line.lower()
                if "calculix" in low and (
                    "version" in low or "." in line
                ):
                    return line.strip()
            return "unknown"
        except (subprocess.TimeoutExpired, OSError):
            return None

    def supported_formats(self) -> list[str]:
        return [".inp"]

    def _add_msys2_path(self) -> None:
        """添加 MSYS2 bin 目录到 PATH（ccx.exe 需要这些 DLL）"""
        import os

        # 1. 检查 cae install 安装的目录 (~/.cae-cli/solvers/calculix/bin/)
        install_bin_dir = settings.solvers_dir / "calculix" / "bin"
        if install_bin_dir.exists():
            current_path = os.environ.get("PATH", "")
            if str(install_bin_dir) not in current_path:
                os.environ["PATH"] = str(install_bin_dir) + os.pathsep + current_path
            return

        # 2. 检查项目自带的 ccx.exe 目录
        local_ccx_dir = Path("D:/CAE-CLI/cae-cli/cxx.exe")
        local_dll_dir = local_ccx_dir / "dlls"

        if local_dll_dir.exists():
            # 使用本地 DLL 目录
            current_path = os.environ.get("PATH", "")
            if str(local_dll_dir) not in current_path:
                os.environ["PATH"] = str(local_dll_dir) + os.pathsep + current_path
            return

        # 3. 回退到系统 MSYS2
        msys2_bin = Path("D:/Apps/tools/msys/ucrt64/bin")
        if msys2_bin.exists():
            current_path = os.environ.get("PATH", "")
            if str(msys2_bin) not in current_path:
                os.environ["PATH"] = str(msys2_bin) + os.pathsep + current_path
        else:
            # 尝试其他常见路径
            for alt_path in ["C:/msys64/ucrt64/bin", "C:/msys2/ucrt64/bin"]:
                if Path(alt_path).exists():
                    current_path = os.environ.get("PATH", "")
                    if alt_path not in current_path:
                        os.environ["PATH"] = alt_path + os.pathsep + current_path
                    break

    def _get_env(self) -> dict:
        """获取环境变量（包含 MSYS2 路径）"""
        import os
        self._add_msys2_path()
        return os.environ.copy()

    def _ensure_frd_output(self, inp_file: Path) -> None:
        """
        cae-cli 专属：强制在 *STEP ... *END STEP 内部插入输出块。

        *NODE FILE 和 *EL FILE 是 step 关键字，必须放在 *STEP 内部
        才能让 CalculiX 将位移/应力结果写入 .frd 文件。

        官方关键规则（摘自 CalculiX 手册）：
        - *NODE FILE：输出节点位移到 .frd
        - *EL FILE：输出单元应力到 .frd
        - 这两个关键字必须放在 *STEP ... *END STEP 内部！
        """
        text = inp_file.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        upper_lines = [l.upper().strip() for l in lines]

        # 检查是否已有 *NODE FILE 和 *EL FILE（在 *STEP 内部）
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
            return  # 已有正确的输出请求

        # 从后往前找最后一个 *END STEP，在它前面插入
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

    def solve(
        self,
        inp_file: Path,
        output_dir: Path,
        *,
        timeout: int = 3600,
        **kwargs,
    ) -> SolveResult:
        """
        调用 CalculiX 执行静力/热力/动力学仿真。

        CalculiX 要求：
        - 以 output_dir 为 CWD 运行（输出文件落地在此）
        - 需要把 .inp 文件复制/硬链接到 output_dir
        """
        # 添加 MSYS2 路径
        self._add_msys2_path()

        # --- 前置检查 ---
        binary = self._find_binary()
        if not binary:
            return self._error_result(
                output_dir,
                "找不到 CalculiX 可执行文件。\n"
                "请运行 `cae install` 安装，或手动安装后确保 `ccx` 在 PATH 中。",
            )

        ok, msg = self.validate_input(inp_file)
        if not ok:
            return self._error_result(output_dir, msg)

        # --- 准备工作目录 ---
        output_dir = output_dir.resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        job_name = inp_file.stem
        inp_dest = output_dir / inp_file.name

        # 仅当源文件和目标不同时才复制
        if inp_dest.resolve() != inp_file.resolve():
            shutil.copy2(inp_file, inp_dest)

        # --- 检查并添加 FRD 输出请求（*NODE FILE / *EL FILE）---
        self._ensure_frd_output(inp_dest)

        # --- 运行 CalculiX ---
        start = time.monotonic()
        is_wsl = self._is_wsl(binary)

        try:
            # 获取包含 MSYS2 路径的环境变量
            env = self._get_env()

            if is_wsl:
                # 使用 WSL 运行
                # 需要将路径转换为 WSL 路径格式
                wsl_input = inp_dest.as_posix().replace("D:", "/mnt/d")
                wsl_output = output_dir.as_posix().replace("D:", "/mnt/d")
                cmd = ["wsl", "-e", "bash", "-c", f"cd {wsl_output} && ccx -i {job_name}"]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env,
                )
            else:
                # 检查 ccx 安装位置
                # 1. cae install 安装的目录 (~/.cae-cli/solvers/calculix/bin/)
                install_bin_dir = (settings.solvers_dir / "calculix" / "bin").resolve()

                # 2. 项目本地的 ccx.exe 目录
                local_ccx_dir = Path("D:/CAE-CLI/cae-cli/cxx.exe").resolve()
                local_dll_dir = local_ccx_dir / "dlls"

                # 判断使用哪种运行模式
                use_install_dir = install_bin_dir.exists() and binary.resolve().parent == install_bin_dir
                use_local_dll = local_dll_dir.exists() and binary.resolve() == local_ccx_dir / "ccx.exe"

                if use_install_dir:
                    # 从安装目录运行 - DLL 就在 bin 目录中
                    cmd = [str(binary), "-i", job_name]
                    proc = subprocess.run(
                        cmd,
                        cwd=str(output_dir),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env,
                    )
                elif use_local_dll:
                    # 使用本地 DLL 目录作为工作目录
                    # 需要把输入文件复制到 dlls 目录
                    inp_in_dlls = local_dll_dir / inp_file.name
                    if inp_dest.resolve() != inp_in_dlls.resolve():
                        shutil.copy2(inp_dest, inp_in_dlls)

                    # 确保 DLL 目录在 PATH 中（使用绝对路径）
                    env_copy = env.copy()
                    dll_dir_str = str(local_dll_dir)
                    if dll_dir_str not in env_copy.get("PATH", ""):
                        env_copy["PATH"] = dll_dir_str + os.pathsep + env_copy.get("PATH", "")

                    # 使用绝对路径运行 ccx
                    cmd = [str(local_ccx_dir / "ccx.exe"), "-i", job_name]
                    proc = subprocess.run(
                        cmd,
                        cwd=str(local_dll_dir),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env_copy,
                    )
                    # 将输出文件从 dll 目录复制到 output_dir
                    for f in local_dll_dir.iterdir():
                        if f.suffix in (".frd", ".dat", ".sta", ".cvg") and f.stem == job_name:
                            shutil.copy2(f, output_dir / f.name)
                    # 清理 dlls 目录中的输入文件
                    if inp_in_dlls.exists():
                        inp_in_dlls.unlink()
                else:
                    # 直接运行（系统 MSYS2 或其他）
                    cmd = [str(binary), "-i", job_name]
                    proc = subprocess.run(
                        cmd,
                        cwd=str(output_dir),
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=env,
                    )
        except subprocess.TimeoutExpired:
            return self._error_result(
                output_dir,
                f"求解超时（超过 {timeout}s）。可用 --timeout 参数调大限制。",
                duration=time.monotonic() - start,
            )
        except OSError as exc:
            return self._error_result(
                output_dir,
                f"无法启动求解器: {exc}",
                duration=time.monotonic() - start,
            )

        duration = time.monotonic() - start

        # --- 解析输出 ---
        combined = proc.stdout + proc.stderr
        errors = self._extract_lines(combined, _ERROR_MARKERS)
        warnings = self._extract_lines(combined, _WARN_MARKERS)

        # 收集输出文件（排除复制进来的 .inp）
        output_files = sorted(
            f for f in output_dir.iterdir()
            if f.is_file() and f.name != inp_file.name
        )

        # 成功判定：returncode=0 且无 *ERROR 且生成了 .frd
        has_frd = any(f.suffix == ".frd" for f in output_files)
        success = proc.returncode == 0 and not errors and has_frd

        error_message: Optional[str] = None
        if errors:
            error_message = "\n".join(errors[:3])  # 最多显示前三条
        elif proc.returncode != 0 and not has_frd:
            error_message = f"求解器退出码: {proc.returncode}，未生成结果文件。"

        return SolveResult(
            success=success,
            output_dir=output_dir,
            output_files=output_files,
            stdout=proc.stdout,
            stderr=proc.stderr,
            returncode=proc.returncode,
            duration_seconds=duration,
            error_message=error_message,
            warnings=warnings[:10],  # 最多保留 10 条警告
        )

    # ------------------------------------------------------------------ #
    # 私有工具
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_lines(text: str, markers: tuple[str, ...]) -> list[str]:
        """从输出文本中提取包含特定标记的行。"""
        return [
            line.strip()
            for line in text.splitlines()
            if any(m in line for m in markers)
        ]

    @staticmethod
    def _error_result(
        output_dir: Path,
        message: str,
        duration: float = 0.0,
    ) -> SolveResult:
        return SolveResult(
            success=False,
            output_dir=output_dir,
            output_files=[],
            stdout="",
            stderr="",
            returncode=-1,
            duration_seconds=duration,
            error_message=message,
        )
