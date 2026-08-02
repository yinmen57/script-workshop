"""火山方舟 Seedance 生视频客户端（创建任务 + 单次查询）。"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from packages.domain.errors import ValidationAppError

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 60.0
_DEFAULT_DURATION = 5
_DEFAULT_RESOLUTION = "480p"
_DEFAULT_RATIO = "adaptive"
PROVIDER = "volcengine_ark"

ProviderTaskState = Literal["running", "succeeded", "failed"]


class ArkVideoClient:
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
                "方舟生视频缺少 base_url：请到「AI Key 配置」补全"
            )
        if not self._api_key.strip():
            raise ValidationAppError(
                "方舟生视频缺少 API Key：请到「AI Key 配置」补全"
            )
        if not (self.model_name or "").strip():
            raise ValidationAppError(
                "方舟生视频缺少模型名：请到「AI Key 配置」补全"
            )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def preflight(self) -> dict[str, Any]:
        self.require_ready()
        return {"credits": None, "provider": self.provider}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require_ready()
        url = f"{self.base_url}{path}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.request(
                method, url, headers=headers, json=json_body
            )
        if resp.status_code >= 400:
            raise ValidationAppError(
                f"方舟视频 API {method} {path} 失败 HTTP {resp.status_code}: "
                f"{resp.text[:800]}"
            )
        if not resp.content:
            return {}
        data = resp.json()
        if not isinstance(data, dict):
            return {"data": data}
        return data

    async def create_video_task(
        self,
        *,
        content: list[dict[str, Any]],
        duration: int | None = None,
        resolution: str | None = None,
        ratio: str | None = None,
    ) -> dict[str, Any]:
        dur = _DEFAULT_DURATION if duration is None else int(duration)
        if dur <= 0:
            dur = _DEFAULT_DURATION
        body: dict[str, Any] = {
            "model": self.model_name,
            "content": content,
            "duration": dur,
            "resolution": resolution or _DEFAULT_RESOLUTION,
            "ratio": ratio or _DEFAULT_RATIO,
            "watermark": False,
        }
        return await self._request(
            "POST", "/contents/generations/tasks", json_body=body
        )

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request(
            "GET", f"/contents/generations/tasks/{task_id}"
        )


def classify_provider_status(payload: dict[str, Any]) -> ProviderTaskState:
    status = str(payload.get("status") or "").lower()
    if status in {"succeeded", "success", "completed"}:
        return "succeeded"
    if status in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    return "running"


def provider_error_message(payload: dict[str, Any]) -> str:
    err = payload.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or err.get("code") or err
        return str(msg)
    if err:
        return str(err)
    return str(payload.get("message") or "方舟视频任务失败")


def extract_video_result_url(payload: dict[str, Any]) -> str | None:
    content = payload.get("content")
    if isinstance(content, dict):
        url = content.get("video_url") or content.get("url")
        if url:
            return str(url)
    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "video_url":
                nested = item.get("video_url")
                if isinstance(nested, dict) and nested.get("url"):
                    return str(nested["url"])
                if isinstance(nested, str):
                    return nested
            if item.get("video_url"):
                return str(item["video_url"])
            if item.get("url") and str(item.get("type") or "").startswith("video"):
                return str(item["url"])
    for key in ("video_url", "stored_video_url", "result_url"):
        if payload.get(key):
            return str(payload[key])
    result = payload.get("result")
    if isinstance(result, dict) and result.get("video_url"):
        return str(result["video_url"])
    return None


def default_video_duration() -> int:
    return _DEFAULT_DURATION


def default_video_resolution() -> str:
    return _DEFAULT_RESOLUTION


def default_video_ratio() -> str:
    return _DEFAULT_RATIO
