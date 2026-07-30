"""赏舞（sd-2-c）开放 API 薄客户端。

鉴权：Authorization Bearer SD_API_KEY。
不直连方舟；剧本 Chat 仍走本平台 LLM 配置。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from packages.domain.errors import ValidationAppError
from packages.infra.config import Settings, get_settings

logger = logging.getLogger(__name__)


class ShangwuClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def require_enabled(self) -> None:
        if not self.settings.sd_enabled:
            raise ValidationAppError("赏舞未启用：请设置 SD_ENABLED=true")
        if not self.settings.sd_base_url.strip():
            raise ValidationAppError("缺少 SD_BASE_URL")
        if not self.settings.sd_api_key.strip():
            raise ValidationAppError("缺少 SD_API_KEY")

    @property
    def base_url(self) -> str:
        return self.settings.sd_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.sd_api_key}",
            "Content-Type": "application/json",
        }

    def _timeout(self) -> float:
        return float(self.settings.sd_request_timeout_seconds)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.require_enabled()
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.settings.sd_api_key}"}
        if files is None:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(timeout=self._timeout()) as client:
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
        """连通性自检 / 提交前余额预检。"""
        return await self._request("GET", "/api/account/balance")

    async def create_image_task(
        self,
        *,
        prompt: str,
        size: str,
        resolution: str | None = None,
        n: int = 1,
        image_model: str | None = None,
        negative_prompt: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "prompt": prompt,
            "image_model": image_model or self.settings.sd_image_model,
            "size": size,
            "resolution": (resolution or self.settings.sd_resolution_norm),
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
        body: dict[str, Any] = {
            "content": content,
            "duration": (
                self.settings.sd_video_duration if duration is None else duration
            ),
            "resolution": resolution or self.settings.sd_video_resolution,
            "ratio": ratio or self.settings.sd_video_ratio,
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

    async def poll_task(
        self,
        task_id: str,
        *,
        interval_sec: float,
        timeout_sec: float,
    ) -> dict[str, Any]:
        """轮询至 succeeded / failed，或超时。"""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_sec
        last: dict[str, Any] = {}
        while True:
            last = await self.get_task(task_id)
            status = (last.get("status") or "").lower()
            if status == "succeeded":
                return last
            if status == "failed":
                err = last.get("error_message") or last.get("error") or "赏舞任务失败"
                raise ValidationAppError(str(err))
            if loop.time() >= deadline:
                raise ValidationAppError(
                    f"赏舞任务轮询超时 task_id={task_id} last_status={status}"
                )
            await asyncio.sleep(interval_sec)

    async def preflight(self) -> dict[str, Any]:
        """提交前预检：余额 + 开关。余额不足（<=0）直接拒绝。"""
        balance = await self.get_balance()
        # 兼容常见字段：balance / credits / remaining / data.balance
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


def get_sd_client() -> ShangwuClient:
    return ShangwuClient()
