"""赏舞（sd-2-c）开放 API 薄客户端。

生图 / 生视频分开：各自从 AI Key 配置页读取默认 image / video 凭证与模型名。
画幅为协议侧常量；上游状态由 Beat 短轮询，禁止本客户端内长 sleep。
"""

from __future__ import annotations

import logging
from typing import Any, Literal

import httpx

from packages.domain.errors import ValidationAppError
from packages.governance.model_service import load_runtime_model

logger = logging.getLogger(__name__)

# 协议侧默认（与具体模型无关；模型名由 AI Key 配置决定）
_REQUEST_TIMEOUT = 60.0
_IMAGE_RESOLUTION = "2k"
_IMAGE_CHARACTER_SIZE = "3:4"
_IMAGE_BACKGROUND_SIZE = "16:9"
_VIDEO_DURATION = -1
_VIDEO_RESOLUTION = "480p"
_VIDEO_RATIO = "adaptive"

ProviderTaskState = Literal["running", "succeeded", "failed"]

ShangwuKind = Literal["image", "video"]


class ShangwuClient:
    provider = "shangwu"

    def __init__(
        self,
        *,
        kind: ShangwuKind,
        base_url: str,
        api_key: str,
        model_name: str,
    ) -> None:
        self.kind = kind
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model_name = model_name

    def require_ready(self) -> None:
        if not self._base_url:
            raise ValidationAppError(
                f"赏舞{self.kind} 缺少 base_url：请到「AI Key 配置」补全"
            )
        if not self._api_key.strip():
            raise ValidationAppError(
                f"赏舞{self.kind} 缺少 API Key：请到「AI Key 配置」补全"
            )
        if not (self.model_name or "").strip():
            raise ValidationAppError(
                f"赏舞{self.kind} 缺少模型名：请到「AI Key 配置」补全"
            )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require_ready()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if files is None:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                json=json_body if files is None else None,
                files=files,
            )
        if resp.status_code >= 400:
            detail = resp.text[:800]
            raise ValidationAppError(
                f"赏舞 API {method} {path} 失败 HTTP {resp.status_code}: {detail}"
            )
        if not resp.content:
            return {}
        data = resp.json()
        if not isinstance(data, dict):
            return {"data": data}
        return data

    async def get_balance(self) -> dict[str, Any]:
        return await self._request("GET", "/api/account/balance")

    async def create_image_task(
        self,
        *,
        prompt: str,
        size: str,
        resolution: str | None = None,
        n: int = 1,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        if self.kind != "image":
            raise ValidationAppError("当前客户端不是生图配置，请使用 image 类型密钥")
        body: dict[str, Any] = {
            "prompt": prompt,
            "image_model": self.model_name,
            "size": size,
            "resolution": resolution or _IMAGE_RESOLUTION,
            "n": n,
        }
        if negative_prompt:
            body["negative_prompt"] = negative_prompt
        return await self._request("POST", "/api/generation/image-tasks", json_body=body)

    async def create_video_task(
        self,
        *,
        content: list[dict[str, Any]],
        duration: int | None = None,
        resolution: str | None = None,
        ratio: str | None = None,
    ) -> dict[str, Any]:
        if self.kind != "video":
            raise ValidationAppError("当前客户端不是生视频配置，请使用 video 类型密钥")
        body: dict[str, Any] = {
            "content": content,
            "duration": _VIDEO_DURATION if duration is None else duration,
            "resolution": resolution or _VIDEO_RESOLUTION,
            "ratio": ratio or _VIDEO_RATIO,
        }
        return await self._request("POST", "/api/generation/tasks", json_body=body)

    async def get_task(self, task_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/api/generation/tasks/{task_id}")

    async def upload_media(
        self, *, filename: str, data: bytes, content_type: str | None = None
    ) -> dict[str, Any]:
        files = {
            "file": (
                filename,
                data,
                content_type or "application/octet-stream",
            )
        }
        return await self._request("POST", "/api/generation/upload", files=files)

    async def preflight(self) -> dict[str, Any]:
        balance = await self.get_balance()
        raw = balance.get("balance")
        if raw is None and isinstance(balance.get("data"), dict):
            raw = balance["data"].get("balance")
        if raw is None:
            raw = balance.get("credits", balance.get("remaining"))
        try:
            credits = float(raw) if raw is not None else None
        except (TypeError, ValueError):
            credits = None
        if credits is not None and credits <= 0:
            raise ValidationAppError(f"赏舞余额不足：{credits}")
        return {"balance": balance, "credits": credits}


def image_size_for_target(target_type: str) -> str:
    if target_type == "character":
        return _IMAGE_CHARACTER_SIZE
    return _IMAGE_BACKGROUND_SIZE


def default_video_duration() -> int:
    return _VIDEO_DURATION


def default_video_resolution() -> str:
    return _VIDEO_RESOLUTION


def default_video_ratio() -> str:
    return _VIDEO_RATIO


def classify_provider_status(payload: dict[str, Any]) -> ProviderTaskState:
    status = (payload.get("status") or "").lower()
    if status == "succeeded":
        return "succeeded"
    if status == "failed":
        return "failed"
    return "running"


def provider_error_message(payload: dict[str, Any]) -> str:
    return str(
        payload.get("error_message") or payload.get("error") or "赏舞任务失败"
    )


def extract_image_result_url(payload: dict[str, Any]) -> str | None:
    urls = payload.get("result_image_urls") or payload.get("image_urls") or []
    if isinstance(urls, str):
        urls = [urls]
    if not urls:
        return None
    return str(urls[0])


def extract_video_result_url(payload: dict[str, Any]) -> str | None:
    result_url = (
        payload.get("stored_video_url")
        or payload.get("video_url")
        or (payload.get("result") or {}).get("video_url")
    )
    return str(result_url) if result_url else None


async def get_image_client(tenant_id: str) -> ShangwuClient:
    """仅赏舞；多 provider 请用 media_client.get_image_client。"""
    creds = await load_runtime_model(tenant_id, "image")
    provider = (creds.get("provider") or "shangwu").strip() or "shangwu"
    if provider != "shangwu":
        raise ValidationAppError(
            f"当前默认生图为 {provider}，请使用 media_client.get_image_client"
        )
    return ShangwuClient(
        kind="image",
        base_url=creds["base_url"],
        api_key=creds["api_key"],
        model_name=creds["model_name"],
    )


async def get_video_client(tenant_id: str) -> ShangwuClient:
    """仅赏舞；多 provider 请用 media_client.get_video_client。"""
    creds = await load_runtime_model(tenant_id, "video")
    provider = (creds.get("provider") or "shangwu").strip() or "shangwu"
    if provider != "shangwu":
        raise ValidationAppError(
            f"当前默认生视频为 {provider}，请使用 media_client.get_video_client"
        )
    return ShangwuClient(
        kind="video",
        base_url=creds["base_url"],
        api_key=creds["api_key"],
        model_name=creds["model_name"],
    )
