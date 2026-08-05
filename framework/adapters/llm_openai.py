"""OpenAI 兼容 Chat Adapter。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx


class OpenAICompatibleChatAdapter:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_name: str,
        *,
        timeout_ms: int = 60000,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout = timeout_ms / 1000.0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def ping(self) -> dict:
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=self._headers())
            resp.raise_for_status()
            return {"ok": True, "status_code": resp.status_code}

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        thinking: bool = False,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        # 方舟 DeepSeek：业务 JSON 任务默认关思考，保证 content 稳定落盘
        thinking_type = "enabled" if thinking else "disabled"
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "thinking": {"type": thinking_type},
        }
        if tools:
            payload["tools"] = tools
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            data = resp.json()
        message = data["choices"][0]["message"]
        usage = data.get("usage") or {}
        return {
            "content": message.get("content"),
            "message": message,
            "model": data.get("model") or self.model_name,
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get("total_tokens", 0),
            },
        }

    async def stream_chat(
        self, messages: list[dict[str, Any]]
    ) -> AsyncIterator[dict[str, Any]]:
        """仅流式输出文本 delta；工具循环请用非流式 chat。"""
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", url, headers=self._headers(), json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data_str = line[5:].strip()
                    else:
                        continue
                    if data_str == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    delta = (
                        (chunk.get("choices") or [{}])[0].get("delta") or {}
                    ).get("content")
                    if delta:
                        yield {"type": "delta", "text": delta}
                    usage = chunk.get("usage")
                    if usage:
                        yield {
                            "type": "usage",
                            "usage": {
                                "prompt_tokens": usage.get("prompt_tokens", 0),
                                "completion_tokens": usage.get(
                                    "completion_tokens", 0
                                ),
                                "total_tokens": usage.get("total_tokens", 0),
                            },
                        }
