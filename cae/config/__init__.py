# 配置设置
"""
cae-cli 全局配置
使用 platformdirs 实现跨平台路径管理：
  - Linux/Mac:  ~/.config/cae-cli/  and  ~/.local/share/cae-cli/
  - Windows:    %APPDATA%/cae-cli/  and  %LOCALAPPDATA%/cae-cli/
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

APP_NAME = "cae-cli"
APP_AUTHOR = "cae-cli"


class Settings:
    """运行时配置管理器，支持读写 JSON 配置文件。"""

    def __init__(self) -> None:
        self.config_dir: Path = Path(user_config_dir(APP_NAME, APP_AUTHOR))
        self.data_dir: Path = Path(user_data_dir(APP_NAME, APP_AUTHOR))

        # 子目录
        self.solvers_dir: Path = self.data_dir / "solvers"
        self.models_dir: Path = self.data_dir / "models"
        self.cache_dir: Path = self.data_dir / "cache"

        self.config_file: Path = self.config_dir / "config.json"

        # 确保目录存在
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.solvers_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)

        self._data: dict[str, Any] = self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    def _load(self) -> dict[str, Any]:
        if self.config_file.exists():
            try:
                return json.loads(self.config_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def save(self) -> None:
        self.config_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------ #
    # 访问器
    # ------------------------------------------------------------------ #

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    # ------------------------------------------------------------------ #
    # 常用配置项
    # ------------------------------------------------------------------ #

    @property
    def default_solver(self) -> str:
        return self._data.get("default_solver", "calculix")

    @default_solver.setter
    def default_solver(self, value: str) -> None:
        self.set("default_solver", value)

    @property
    def default_output_dir(self) -> Path:
        raw = self._data.get("default_output_dir", "results")
        return Path(raw)

    @property
    def active_model(self) -> str | None:
        return self._data.get("active_model")

    @active_model.setter
    def active_model(self, value: str) -> None:
        self.set("active_model", value)

    @property
    def solver_path(self) -> str | None:
        """CalculiX 求解器路径"""
        return self._data.get("solver_path")

    @solver_path.setter
    def solver_path(self, value: str) -> None:
        self.set("solver_path", value)

    # ------------------------------------------------------------------ #
    # 工作目录配置
    # ------------------------------------------------------------------ #

    @property
    def workspace_path(self) -> Path | None:
        """工作目录路径"""
        raw = self._data.get("workspace_path")
        return Path(raw) if raw else None

    @workspace_path.setter
    def workspace_path(self, value: Path) -> None:
        self.set("workspace_path", str(value))

    @property
    def workspace_output_dir(self) -> Path | None:
        """工作目录下的 output 子目录"""
        ws = self.workspace_path
        return ws / "output" if ws else None

    @property
    def workspace_solvers_dir(self) -> Path | None:
        """工作目录下的 solvers 子目录"""
        ws = self.workspace_path
        return ws / "solvers" if ws else None

    @property
    def workspace_solver_path(self) -> Path | None:
        """工作目录下的求解器路径：workspace/solvers/ccx"""
        solvers = self.workspace_solvers_dir
        return solvers / "ccx" if solvers else None

    def setup_workspace(self, workspace_path: Path) -> None:
        """
        设置工作目录，自动创建子目录结构并保存配置。

        工作目录/
        ├── output/       # 所有输出文件
        └── solvers/      # 求解器自动安装到这里
        """
        workspace_path = workspace_path.resolve()

        # 创建子目录
        output_dir = workspace_path / "output"
        solvers_dir = workspace_path / "solvers"

        output_dir.mkdir(parents=True, exist_ok=True)
        solvers_dir.mkdir(parents=True, exist_ok=True)

        # 保存配置
        self.workspace_path = workspace_path
        self.set("default_output_dir", str(output_dir))
        self.solver_path = str(solvers_dir / "ccx")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Settings(config_dir={self.config_dir}, "
            f"data_dir={self.data_dir}, "
            f"default_solver={self.default_solver!r})"
        )


# 全局单例
settings = Settings()
