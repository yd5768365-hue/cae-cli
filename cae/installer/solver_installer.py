# -*- coding: utf-8 -*-
"""
CalculiX 求解器安装器

从 GitHub Release 下载并安装 CalculiX
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.request import urlretrieve
from urllib.error import URLError

# GitHub Release 地址
REPO_OWNER = "yd5768365-hue"
REPO_NAME = "cae-cli"
RELEASE_VERSION = "ccx"


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    method: str = ""
    install_dir: Optional[Path] = None
    error_message: Optional[str] = None


def get_platform() -> str:
    """获取当前平台"""
    system = platform.system().lower()
    if system == "windows":
        return "windows"
    elif system == "linux":
        return "linux"
    elif system == "darwin":
        return "macos"
    return "unknown"


def get_archive_name(platform_name: str) -> str:
    """获取对应平台的压缩包名称"""
    names = {
        "windows": "calculix_2.23_4win.zip",
        "linux": "ccx_linux.tar.gz",
        "macos": "ccx_macos.tar.gz",
    }
    return names.get(platform_name, "calculix_2.23_4win.zip")


class SolverInstaller:
    """CalculiX 求解器安装器"""

    def __init__(self, install_dir: Optional[Path] = None):
        self.platform = get_platform()
        self.archive_name = get_archive_name(self.platform)

        # 自定义安装目录或默认 ~/.cae-cli/solvers/calculix/
        self._custom_dir = install_dir
        self.cae_home = Path.home() / ".cae-cli"
        self._default_solvers_dir = self.cae_home / "solvers" / "calculix"
        self._default_bin_dir = self._default_solvers_dir / "bin"

        # 项目内置求解器目录（用于分发）
        # 从配置读取，如果未设置则使用默认值
        project_root = Path(__file__).parent.parent.parent
        builtin_paths_raw = self._data.get("builtin_solver_paths", "")
        if builtin_paths_raw:
            # 从配置读取的路径列表（逗号分隔）
            self._builtin_dirs = [Path(p.strip()) for p in builtin_paths_raw.split(",") if p.strip()]
        else:
            # 默认内置路径
            self._builtin_dirs = [
                project_root / "cxx.exe",  # cae-cli/cxx.exe/
                project_root / "release" / "ccx",  # cae-cli/release/ccx/
            ]

    @property
    def bin_dir(self) -> Path:
        """获取 bin 目录"""
        if self._custom_dir:
            return self._custom_dir / "bin" if self._custom_dir.name != "bin" else self._custom_dir
        return self._default_bin_dir

    @property
    def solvers_dir(self) -> Path:
        """获取 solvers 目录"""
        if self._custom_dir:
            return self._custom_dir.parent if self._custom_dir.name == "bin" else self._custom_dir
        return self._default_solvers_dir

    def is_installed(self, custom_path: Optional[Path] = None) -> bool:
        """检查是否已安装"""
        if custom_path:
            check_dir = custom_path / "bin" if custom_path.name != "bin" else custom_path
            if self.platform == "windows":
                return (check_dir / "ccx.exe").is_file()
            else:
                return (check_dir / "ccx").is_file()
        # 优先检查 ccx.exe（static 版本）
        if self.platform == "windows":
            return (self.bin_dir / "ccx.exe").is_file()
        else:
            return (self.bin_dir / "ccx").is_file()

    def get_install_dir(self) -> Path:
        """获取安装目录"""
        return self.bin_dir

    def _get_download_urls(self) -> list[str]:
        """获取下载链接列表（按优先级）"""
        base_urls = [
            f"https://ghproxy.net/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_VERSION}/{self.archive_name}",
            f"https://gh-proxy.com/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_VERSION}/{self.archive_name}",
            f"https://mirror.ghproxy.com/https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_VERSION}/{self.archive_name}",
            f"https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{RELEASE_VERSION}/{self.archive_name}",
        ]
        return base_urls

    def _get_cae_dir(self) -> Path:
        """获取 .cae-cli 目录"""
        return self.cae_home

    def install(
        self,
        progress_callback: Optional[callable] = None,
        local_archive: Optional[Path] = None,
        force: bool = False,
    ) -> InstallResult:
        """
        安装 CalculiX

        Args:
            progress_callback: 进度回调函数 (percent: float, message: str)
            local_archive: 本地压缩包路径（用于测试）
            force: 强制重新安装

        Returns:
            InstallResult
        """
        if self.is_installed() and not force:
            return InstallResult(success=True, method="already_installed")

        # 确保安装目录存在
        self.bin_dir.mkdir(parents=True, exist_ok=True)

        # 确定使用本地文件还是下载
        archive_path: Path
        if local_archive and local_archive.exists():
            archive_path = local_archive
            download_urls = None
        else:
            archive_path = self.cae_home / self.archive_name
            download_urls = self._get_download_urls()

        try:
            if download_urls:
                # 尝试多个镜像源
                download_success = False
                last_error = ""
                for url in download_urls:
                    if progress_callback:
                        progress_callback(0.02, f"尝试下载源: {url[:50]}...")

                    try:
                        self._download_file(url, archive_path, progress_callback)
                        download_success = True
                        break
                    except Exception as e:
                        last_error = str(e)
                        if progress_callback:
                            progress_callback(0.02, f"下载失败，尝试下一个源...")
                        continue

                if not download_success:
                    raise RuntimeError(f"所有下载源均失败: {last_error}")

            if progress_callback:
                progress_callback(0.65, "正在解压...")

            # 解压
            self._extract_archive(archive_path)

            if progress_callback:
                progress_callback(0.90, "正在清理...")

            # 清理压缩包
            if archive_path.exists():
                archive_path.unlink()

            # 验证安装
            if self.is_installed():
                if progress_callback:
                    progress_callback(1.0, "安装完成")
                method = "reinstalled_from_github" if force else "downloaded_from_github"
                return InstallResult(
                    success=True,
                    method=method,
                    install_dir=self.bin_dir,
                )
            else:
                return InstallResult(
                    success=False,
                    error_message="安装后验证失败",
                )

        except Exception as e:
            # 下载/解压失败时，尝试使用内置求解器
            if progress_callback:
                progress_callback(0.1, "下载失败，尝试使用内置求解器...")

            builtin_result = self.install_from_builtin(progress_callback)
            if builtin_result.success:
                builtin_result.method = "fallback_to_builtin"
                return builtin_result
            return InstallResult(
                success=False,
                error_message=str(e),
            )

    def _download_file(self, url: str, dest: Path, progress_callback: Optional[callable] = None) -> None:
        """下载文件，失败时抛出异常"""
        # 使用 curl 下载（更可靠）
        result = subprocess.run(
            ["curl", "-L", "-o", str(dest), url, "--progress-bar", "--connect-timeout", "30", "-m", "300"],
            capture_output=True,
            text=True,
            timeout=360,
        )
        if result.returncode != 0:
            raise RuntimeError(f"curl 下载失败: {result.stderr.strip()[:200]}")

    def _extract_archive(self, archive_path: Path) -> None:
        """解压压缩包"""
        if self.platform == "windows":
            # 解压 ZIP
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(self.solvers_dir)
        else:
            # 解压 tar.gz
            with tarfile.open(archive_path, "gz") as tf:
                tf.extractall(self.solvers_dir)

        # 检查解压后的目录结构
        # 预期: solvers/calculix/bin/ccx 或 solvers/calculix/bin/ccx.exe
        extracted_files = list(self.solvers_dir.rglob("ccx*"))
        if not extracted_files:
            raise RuntimeError("解压后未找到 ccx 可执行文件")

        # 优先使用 static 版本（无需额外 DLL）
        static_files = list(self.solvers_dir.rglob("ccx_static.exe"))
        if static_files:
            static_exe = static_files[0]
            dest = self.bin_dir / "ccx.exe"
            shutil.copy2(static_exe, dest)
        else:
            # 移动到 bin 目录（如果需要）
            for f in extracted_files:
                dest = self.bin_dir / f.name
                if f != dest:
                    shutil.move(str(f), str(dest))

        # 清理可能产生的空目录
        self._cleanup_empty_dirs(self.solvers_dir)

    def _cleanup_empty_dirs(self, root: Path) -> None:
        """清理空目录"""
        for dirpath in sorted(root.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                try:
                    dirpath.rmdir()
                except OSError:
                    pass

    def uninstall(self) -> bool:
        """卸载 CalculiX"""
        if not self.is_installed():
            return True

        try:
            # 删除 bin 目录
            if self.bin_dir.exists():
                shutil.rmtree(self.bin_dir)

            # 如果 solvers 目录为空，也删除
            solvers_root = self.solvers_dir.parent
            if solvers_root.exists() and not any(solvers_root.iterdir()):
                shutil.rmtree(solvers_root)

            return True
        except Exception:
            return False

    def _find_builtin_solver(self) -> Optional[Path]:
        """查找项目内置的求解器"""
        for directory in self._builtin_dirs:
            if not directory.exists():
                continue
            if self.platform == "windows":
                ccx_path = directory / "ccx.exe"
                if ccx_path.is_file():
                    return ccx_path
            else:
                ccx_path = directory / "ccx"
                if ccx_path.is_file():
                    return ccx_path
        return None

    def install_from_builtin(self, progress_callback: Optional[callable] = None) -> InstallResult:
        """从项目内置求解器安装（用于分发场景）"""
        if self.is_installed():
            return InstallResult(success=True, method="already_installed")

        builtin_path = self._find_builtin_solver()
        if not builtin_path:
            return InstallResult(
                success=False,
                error_message="未找到内置求解器，请先运行 'cae install' 安装"
            )

        try:
            self.bin_dir.mkdir(parents=True, exist_ok=True)

            if progress_callback:
                progress_callback(0.3, "正在复制求解器...")

            dest = self.bin_dir / builtin_path.name
            shutil.copy2(builtin_path, dest)

            # 如果有 DLL 目录，也复制
            dll_dir = builtin_path.parent / "dlls"
            if dll_dir.exists():
                dll_dest = self.bin_dir / "dlls"
                dll_dest.mkdir(parents=True, exist_ok=True)
                for dll in dll_dir.glob("*.dll"):
                    shutil.copy2(dll, dll_dest / dll.name)

            if progress_callback:
                progress_callback(0.9, "正在验证...")

            if self.is_installed():
                return InstallResult(
                    success=True,
                    method="builtin_copy",
                    install_dir=self.bin_dir,
                )
            return InstallResult(success=False, error_message="复制后验证失败")

        except Exception as e:
            return InstallResult(success=False, error_message=str(e))
