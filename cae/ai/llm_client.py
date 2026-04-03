# llm_client.py
"""
LLMClient — llama-cpp-python 接口封装

支持两种模式：
  1. Server 模式：启动 llama-server HTTP 服务（需要较大内存）
  2. Direct 模式：直接调用 llama_cpp.Llama（内存高效，推荐 8GB 以下机器）

默认使用 Direct 模式。
"""
from __future__ import annotations

import socket
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

import requests

from cae.config import settings

# 默认端口
DEFAULT_PORT = 8080


@dataclass
class LLMConfig:
    """LLM 运行配置。"""
    model_name: Optional[str] = None  # 模型名称（相对于 models_dir）
    model_path: Optional[Path] = None  # 或完整模型路径（优先使用）
    port: int = DEFAULT_PORT
    context_size: int = 2048  # 降低默认以节省内存
    n_gpu_layers: int = 0  # CPU 模式
    n_batch: int = 512  # 批处理大小
    timeout: int = 30
    use_server: bool = False  # 默认使用 direct 模式
    use_ollama: bool = False  # 使用 Ollama 后端
    provider: str = "ollama"  # "ollama" | "deepseek"
    api_key: Optional[str] = None  # DeepSeek API key


@dataclass
class LLMClient:
    """
    llama-cpp-python 封装。

    提供 complete() 和 complete_streaming() 两个核心接口。
    """
    config: Optional[LLMConfig] = None
    _llm: Optional[object] = field(default=None, repr=False)
    _base_url: str = field(init=False)

    def __post_init__(self) -> None:
        if self.config is None:
            self.config = LLMConfig()
        self._base_url = f"http://127.0.0.1:{self.config.port}"
        self._ollama_url = "http://localhost:11434/api/generate"  # Ollama API

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #

    def is_running(self) -> bool:
        """检测服务是否已运行（端口可用）。"""
        return self._check_port(self.config.port)

    def _get_model_path(self) -> Path:
        """解析模型路径。"""
        if self.config.model_path:
            return Path(self.config.model_path)

        model_name = self.config.model_name or settings.active_model
        if not model_name:
            raise RuntimeError(
                "未设置 AI 模型。请先运行 `cae install --model <name>` 安装并激活模型，"
                "或设置 settings.active_model。"
            )

        # 优先从 models_dir 查找，否则当作完整路径
        if Path(model_name).exists():
            return Path(model_name)
        return settings.models_dir / model_name

    def start_server(self, timeout: int = 30) -> bool:
        """
        启动 llama-server 或加载 direct 模型。

        Returns:
            True 启动成功
            False 启动失败
        """
        model_path = self._get_model_path()
        if not model_path.exists():
            raise FileNotFoundError(
                f"模型文件不存在: {model_path}\n"
                f"请运行 `cae install --model <name>` 下载模型。"
            )

        if self.config.use_server:
            return self._start_llama_server(model_path, timeout)
        else:
            return self._load_direct_model(model_path)

    def _load_direct_model(self, model_path: Path) -> bool:
        """Direct 模式：直接加载模型。"""
        try:
            from llama_cpp import Llama

            self._llm = Llama(
                model_path=str(model_path),
                n_ctx=self.config.context_size,
                n_gpu_layers=self.config.n_gpu_layers,
                n_batch=self.config.n_batch,
                verbose=False,
            )
            return True
        except ImportError:
            raise RuntimeError(
                "llama-cpp-python 未安装。请运行：\n"
                "  pip install llama-cpp-python"
            )
        except Exception as exc:
            raise RuntimeError(f"模型加载失败: {exc}")

    def _start_llama_server(self, model_path: Path, timeout: int) -> bool:
        """Server 模式：启动 HTTP 服务。"""
        if self._check_port(self.config.port):
            return True  # 已有服务

        python_exe = self._find_python_with_llama()
        port = self._base_url.split(":")[2]

        cmd = [
            python_exe, "-m", "llama_cpp.server",
            "--model", str(model_path),
            "--host", "127.0.0.1",
            "--port", port,
            "--n_ctx", str(self.config.context_size),
            "--n_gpu_layers", str(self.config.n_gpu_layers),
            "--n_batch", str(self.config.n_batch),
        ]

        try:
            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=self._get_env(),
            )
        except FileNotFoundError:
            raise RuntimeError(
                "未找到 llama-server。请确保 llama-cpp-python 已安装。"
            )

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self._check_port(self.config.port):
                return True
            if self._process.poll() is not None:
                stderr = self._process.stderr.read() if self._process.stderr else ""
                raise RuntimeError(f"llama-server 启动失败:\n{stderr}")
            time.sleep(1)

        self.stop_server()
        raise TimeoutError(f"llama-server 启动超时（{timeout}s）")

    def stop_server(self) -> None:
        """停止服务/释放模型。"""
        if self._llm:
            try:
                self._llm.close()
            except Exception:
                pass
            self._llm = None

        if hasattr(self, '_process') and self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None

    # ------------------------------------------------------------------ #
    # 对话补全
    # ------------------------------------------------------------------ #

    def complete(
        self,
        prompt: str,
        *,
        stream: bool = False,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        stop: Optional[list[str]] = None,
    ) -> str:
        """
        发送补全请求。

        Returns:
            完整生成的文本
        """
        if self.config.use_ollama or self.config.provider == "ollama":
            return self._complete_ollama(prompt, max_tokens, temperature)
        if self.config.provider == "deepseek":
            return self._complete_deepseek(prompt, max_tokens, temperature)
        if self._llm:
            return self._complete_direct(prompt, max_tokens, temperature, stop)
        return self._complete_server(prompt, max_tokens, temperature, stop, stream=False)

    def _complete_direct(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[list[str]],
    ) -> str:
        """Direct 模式补全。"""
        result = self._llm.create_completion(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop or [],
            stream=False,
        )
        return result["choices"][0]["text"]

    def _complete_server(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        stop: Optional[list[str]],
        stream: bool,
    ) -> str:
        """Server 模式补全。"""
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": stop or [],
            "stream": stream,
        }

        resp = requests.post(
            f"{self._base_url}/completion",
            json=payload,
            timeout=max_tokens * 2,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("content", "")

    def _complete_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """Ollama 后端补全。"""
        model_name = self.config.model_name or "deepseek-r1:1.5b"
        payload = {
            "model": model_name,
            "prompt": prompt,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature,
            },
            "stream": False,
        }

        resp = requests.post(self._ollama_url, json=payload, timeout=max_tokens * 3)
        resp.raise_for_status()
        data = resp.json()
        # DeepSeek-R1 使用 thinking 字段存储推理过程
        thinking = data.get("thinking", "")
        response = data.get("response", "")
        if thinking and not response:
            return thinking
        return response

    def _complete_deepseek(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        """DeepSeek API 后端补全。"""
        from .deepseek_client import DeepSeekClient

        ds_client = DeepSeekClient(
            model=self.config.model_name or "deepseek-reasoner",
            api_key=self.config.api_key,
        )
        return ds_client.complete(prompt)

    def complete_streaming(self, prompt: str, **kwargs) -> Iterator[str]:
        """
        流式补全，yield 每个 token。

        Yields:
            逐 token 生成的文本片段
        """
        max_tokens = kwargs.get("max_tokens", 2048)
        temperature = kwargs.get("temperature", 0.7)
        stop = kwargs.get("stop", [])

        if self.config.use_ollama or self.config.provider == "ollama":
            # Ollama 非流式（简化处理）
            result = self._complete_ollama(prompt, max_tokens, temperature)
            yield result
            return

        if self.config.provider == "deepseek":
            # DeepSeek 非流式（简化处理）
            result = self._complete_deepseek(prompt, max_tokens, temperature)
            yield result
            return

        if self._llm:
            return self._stream_direct(prompt, max_tokens, temperature, stop)

        return self._stream_server(prompt, max_tokens, temperature, stop)

    def _stream_direct(self, prompt: str, max_tokens: int, temperature: float, stop: list[str]) -> Iterator[str]:
        """Direct 模式流式补全。"""
        result = self._llm.create_completion(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=stop,
            stream=True,
        )
        for item in result:
            if "choices" in item and item["choices"]:
                token = item["choices"][0].get("text", "")
                if token:
                    yield token

    def _stream_server(self, prompt: str, max_tokens: int, temperature: float, stop: list[str]) -> Iterator[str]:
        """Server 模式流式补全。"""
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": stop,
            "stream": True,
        }

        resp = requests.post(
            f"{self._base_url}/completion",
            json=payload,
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            if line.startswith(b"data: "):
                line = line[6:]
            if line.strip() == b"[DONE]":
                break
            import json
            try:
                data = json.loads(line)
                token = data.get("content", "")
                if token:
                    yield token
            except json.JSONDecodeError:
                continue

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #

    @staticmethod
    def _find_python_with_llama() -> str:
        """查找含有 llama-cpp-python 的 Python 解释器路径。"""
        import sys

        try:
            import llama_cpp
            return sys.executable
        except ImportError:
            pass

        # 搜索系统中可能的 Python 安装路径
        import shutil
        possible_pythons = set()

        # 从 PATH 中查找 python
        for name in ["python", "python3", "python.exe", "python3.exe"]:
            found = shutil.which(name)
            if found:
                possible_pythons.add(found)

        # 添加常见 Python 安装路径
        import os
        common_paths = [
            "C:/Users/" + os.environ.get("USERNAME", "user") + "/AppData/Local/Programs/Python",
            "C:/Python310",
            "C:/Python39",
            "C:/Python311",
            "C:/Python312",
            "C:/Program Files/Python310",
            "C:/Program Files/Python39",
        ]
        for base in common_paths:
            if os.path.isdir(base):
                for subdir in os.listdir(base) if os.path.isdir(base) else []:
                    py_path = os.path.join(base, subdir, "python.exe")
                    if os.path.isfile(py_path):
                        possible_pythons.add(py_path)

        for py in possible_pythons:
            try:
                result = subprocess.run(
                    [py, "-c", "import llama_cpp"],
                    capture_output=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return py
            except (subprocess.TimeoutExpired, OSError):
                continue

        return sys.executable

    @staticmethod
    def _get_env() -> dict:
        """获取环境变量（UTF-8 编码）。"""
        import os
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        return env

    @staticmethod
    def _check_port(port: int) -> bool:
        """检测端口是否已被占用。"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect(("127.0.0.1", port))
            return True
        except (socket.error, OSError):
            return False
        finally:
            sock.close()

    def __del__(self) -> None:
        """确保资源被释放。"""
        self.stop_server()
