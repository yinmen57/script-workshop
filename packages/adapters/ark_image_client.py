"""火山方舟 Seedream 生图客户端（同步 HTTP，无上游任务轮询）。"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

import httpx

from packages.domain.errors import ValidationAppError

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 120.0
_DEFAULT_SIZE = "2K"
PROVIDER = "volcengine_ark"


class ArkImageClient:
    provider = PROVIDER

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model_name: str,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model_name = model_name

    def require_ready(self) -> None:
        if not self._base_url:
            raise ValidationAppError(
                "方舟生图缺少 base_url：请到「AI Key 配置」补全"
            )
        if not self._api_key.strip():
            raise ValidationAppError(
                "方舟生图缺少 API Key：请到「AI Key 配置」补全"
            )
        if not (self.model_name or "").strip():
            raise ValidationAppError(
                "方舟生图缺少模型名：请到「AI Key 配置」补全"
            )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def preflight(self) -> dict[str, Any]:
        self.require_ready()
        return {"credits": None, "provider": self.provider}

    async def create_image_task(
        self,
        *,
        prompt: str,
        size: str | None = None,
        resolution: str | None = None,
        n: int = 1,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        """同步生图：一次请求返回结果 URL。"""
        del n, negative_prompt  # 方舟 P0 不传这些字段
        self.require_ready()
        ark_size = _normalize_size(size, resolution)
        body: dict[str, Any] = {
            "model": self.model_name,
            "prompt": prompt,
            "size": ark_size,
            "response_format": "url",
            "watermark": False,
            "stream": False,
            "sequential_image_generation": "disabled",
        }
        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise ValidationAppError(
                f"方舟生图失败 HTTP {resp.status_code}: {resp.text[:800]}"
            )
        data = resp.json()
        if not isinstance(data, dict):
            raise ValidationAppError(f"方舟生图响应异常: {data!r}")
        result_url = extract_image_result_url(data)
        if not result_url:
            raise ValidationAppError(f"方舟生图未返回图片 URL: {data}")
        # 合成 task id，供 generation_task / finalize 关联
        task_id = f"ark-sync-{uuid4().hex}"
        return {
            "id": task_id,
            "status": "succeeded",
            "data": data.get("data") or [{"url": result_url}],
            "model": data.get("model") or self.model_name,
            "usage": data.get("usage"),
            "sync": True,
        }

    async def get_task(self, task_id: str) -> dict[str, Any]:
        raise ValidationAppError(
            f"方舟生图为同步接口，无任务查询（task_id={task_id}）"
        )


def _normalize_size(size: str | None, resolution: str | None) -> str:
    """赏舞画幅（3:4）与方舟 size（2K / 宽x高）不同，P0 默认 2K。"""
    for raw in (resolution, size):
        if not raw:
            continue
        text = str(raw).strip()
        upper = text.upper()
        if upper in {"2K", "3K", "4K"}:
            return upper
        lower = text.lower()
        if "x" in lower:
            parts = lower.split("x", 1)
            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                return text
    return _DEFAULT_SIZE


def extract_image_result_url(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
        if isinstance(first, str):
            return first
    if payload.get("url"):
        return str(payload["url"])
    return None
