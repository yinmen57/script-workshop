"""阿里云 OSS：官方 SDK（oss2）上传与访问。"""

from __future__ import annotations

import oss2

from framework.infra.config import get_settings


def get_oss_bucket() -> oss2.Bucket:
    """按当前配置构造 Bucket（官方 Auth + Endpoint）。"""
    settings = get_settings()
    auth = oss2.Auth(settings.oss_access_key_id, settings.oss_access_key_secret)
    return oss2.Bucket(
        auth,
        settings.oss_endpoint_url,
        settings.oss_bucket,
        # 与控制台默认一致：https + 虚拟主机风格
        is_cname=False,
        connect_timeout=30,
    )


def build_object_key(tenant_id: str, kb_id: str, doc_id: str, filename: str) -> str:
    safe_name = filename.replace("\\", "/").split("/")[-1]
    return f"{tenant_id}/{kb_id}/{doc_id}/{safe_name}"


def public_url(object_key: str) -> str:
    """拼公开访问 URL（桶需已开公共读或走 CDN；私有桶请改用签名 URL）。"""
    settings = get_settings()
    return f"{settings.oss_public_base}/{object_key.lstrip('/')}"


def put_bytes(
    object_key: str,
    data: bytes,
    *,
    content_type: str | None = None,
) -> str:
    """官方 put_object 上传字节，返回公开 URL。"""
    headers = {}
    if content_type:
        headers["Content-Type"] = content_type
    bucket = get_oss_bucket()
    bucket.put_object(object_key, data, headers=headers or None)
    return public_url(object_key)


def ping_oss() -> bool:
    settings = get_settings()
    if not settings.oss_enabled:
        raise RuntimeError("OSS_ENABLED=false")
    bucket = get_oss_bucket()
    # 官方探活：读桶元信息
    bucket.get_bucket_info()
    return True
