"""
DeepSeek API 客户端。

使用方式：
    client = DeepSeekClient(api_key="sk-xxxx")
    response = client.complete("你好")
"""
from __future__ import annotations

import re
from typing import Optional

import requests

API_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-reasoner"


class DeepSeekClient:
    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        timeout: float = 120.0,
    ):
        """
        Args:
            model: DeepSeek 模型名，默认 deepseek-reasoner
            api_key: API key
            timeout: 请求超时（秒）
        """
        self.model = model
        if not api_key:
            raise ValueError("DeepSeek API key 未设置，请在调用时传入 api_key 参数。")
        self.api_key = api_key
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        """
        发送对话请求，返回纯文本响应（非流式）。

        Args:
            prompt: 对话 prompt

        Returns:
            模型生成的文本（已过滤思考过程）
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        resp = requests.post(API_URL, json=payload, headers=headers, timeout=self.timeout)
        resp.raise_for_status()

        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return self._filter_thinking(content)

    @staticmethod
    def _filter_thinking(text: str) -> str:
        """过滤掉 DeepSeek R1 的思考过程（<think>...</think>）。"""
        return re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
