"""生图 / 生视频运行时客户端：按 AI Key 的 provider 分流。"""

from __future__ import annotations

from typing import Any, Literal

from business.adapters import ark_image_client, ark_video_client
from business.adapters.ark_image_client import ArkImageClient
from business.adapters.ark_video_client import ArkVideoClient
from business.adapters.sd_client import (
    ShangwuClient,
    classify_provider_status as _shangwu_classify,
    default_video_duration as _shangwu_video_duration,
    default_video_ratio as _shangwu_video_ratio,
    default_video_resolution as _shangwu_video_resolution,
    extract_image_result_url as _shangwu_image_url,
    extract_video_result_url as _shangwu_video_url,
    image_size_for_target,
    provider_error_message as _shangwu_error,
)
from framework.domain.errors import ValidationAppError
from framework.governance.model_service import load_runtime_model

PROVIDER_SHANGWU = "shangwu"
PROVIDER_ARK = "volcengine_ark"
_MEDIA_PROVIDERS = frozenset({PROVIDER_SHANGWU, PROVIDER_ARK})

ProviderTaskState = Literal["running", "succeeded", "failed"]
ImageClient = ShangwuClient | ArkImageClient
VideoClient = ShangwuClient | ArkVideoClient


def require_media_provider(provider: str, *, kind: str) -> str:
    p = (provider or "").strip() or PROVIDER_SHANGWU
    if p not in _MEDIA_PROVIDERS:
        raise ValidationAppError(
            f"不支持的{kind} provider「{p}」，可选：shangwu / volcengine_ark"
        )
    return p


async def get_image_client(tenant_id: str) -> ImageClient:
    creds = await load_runtime_model(tenant_id, "image")
    provider = require_media_provider(creds.get("provider") or "", kind="生图")
    if provider == PROVIDER_ARK:
        return ArkImageClient(
            base_url=creds["base_url"],
            api_key=creds["api_key"],
            model_name=creds["model_name"],
        )
    return ShangwuClient(
        kind="image",
        base_url=creds["base_url"],
        api_key=creds["api_key"],
        model_name=creds["model_name"],
    )


async def get_video_client(tenant_id: str) -> VideoClient:
    creds = await load_runtime_model(tenant_id, "video")
    provider = require_media_provider(creds.get("provider") or "", kind="生视频")
    if provider == PROVIDER_ARK:
        return ArkVideoClient(
            base_url=creds["base_url"],
            api_key=creds["api_key"],
            model_name=creds["model_name"],
        )
    return ShangwuClient(
        kind="video",
        base_url=creds["base_url"],
        api_key=creds["api_key"],
        model_name=creds["model_name"],
    )


def client_provider(client: Any) -> str:
    return str(getattr(client, "provider", None) or PROVIDER_SHANGWU)


def is_sync_image_provider(provider: str) -> bool:
    return provider == PROVIDER_ARK


def classify_provider_status(
    payload: dict[str, Any], *, provider: str | None = None
) -> ProviderTaskState:
    p = (provider or "").strip()
    if p == PROVIDER_ARK:
        return ark_video_client.classify_provider_status(payload)
    # 赏舞；同步方舟生图也会带 status=succeeded
    status = str(payload.get("status") or "").lower()
    if status in {"succeeded", "success", "completed"}:
        return "succeeded"
    if status in {"failed", "error", "cancelled", "canceled"}:
        return "failed"
    if p == PROVIDER_SHANGWU or not p:
        return _shangwu_classify(payload)
    return "running"


def provider_error_message(
    payload: dict[str, Any], *, provider: str | None = None
) -> str:
    p = (provider or "").strip()
    if p == PROVIDER_ARK:
        return ark_video_client.provider_error_message(payload)
    return _shangwu_error(payload)


def extract_image_result_url(
    payload: dict[str, Any], *, provider: str | None = None
) -> str | None:
    p = (provider or "").strip()
    if p == PROVIDER_ARK:
        return ark_image_client.extract_image_result_url(payload)
    url = _shangwu_image_url(payload)
    if url:
        return url
    # 容错：若配置错标但响应是方舟形态
    return ark_image_client.extract_image_result_url(payload)


def extract_video_result_url(
    payload: dict[str, Any], *, provider: str | None = None
) -> str | None:
    p = (provider or "").strip()
    if p == PROVIDER_ARK:
        return ark_video_client.extract_video_result_url(payload)
    url = _shangwu_video_url(payload)
    if url:
        return url
    return ark_video_client.extract_video_result_url(payload)


def default_video_duration(*, provider: str | None = None) -> int:
    if (provider or "").strip() == PROVIDER_ARK:
        return ark_video_client.default_video_duration()
    return _shangwu_video_duration()


def default_video_resolution(*, provider: str | None = None) -> str:
    if (provider or "").strip() == PROVIDER_ARK:
        return ark_video_client.default_video_resolution()
    return _shangwu_video_resolution()


def default_video_ratio(*, provider: str | None = None) -> str:
    if (provider or "").strip() == PROVIDER_ARK:
        return ark_video_client.default_video_ratio()
    return _shangwu_video_ratio()


__all__ = [
    "PROVIDER_ARK",
    "PROVIDER_SHANGWU",
    "ImageClient",
    "VideoClient",
    "client_provider",
    "classify_provider_status",
    "default_video_duration",
    "default_video_ratio",
    "default_video_resolution",
    "extract_image_result_url",
    "extract_video_result_url",
    "get_image_client",
    "get_video_client",
    "image_size_for_target",
    "is_sync_image_provider",
    "provider_error_message",
    "require_media_provider",
]
