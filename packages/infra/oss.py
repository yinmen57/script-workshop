"""阿里云 OSS（S3 兼容）。文档路径：tenant_id/kb_id/doc_id/..."""

from __future__ import annotations

import boto3
from botocore.client import Config

from packages.infra.config import get_settings


def get_s3_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.oss_endpoint_url,
        aws_access_key_id=settings.oss_access_key_id,
        aws_secret_access_key=settings.oss_access_key_secret,
        region_name=settings.oss_region_name,
        # 阿里云 OSS 要求 virtual hosted style
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "virtual"},
        ),
    )


def build_object_key(tenant_id: str, kb_id: str, doc_id: str, filename: str) -> str:
    safe_name = filename.replace("\\", "/").split("/")[-1]
    return f"{tenant_id}/{kb_id}/{doc_id}/{safe_name}"


def public_url(object_key: str) -> str:
    """拼公开访问 URL（桶需已开公共读或走 CDN；私有桶请改用签名 URL）。"""
    settings = get_settings()
    return f"{settings.oss_public_base}/{object_key.lstrip('/')}"


def ping_oss() -> bool:
    settings = get_settings()
    if not settings.oss_enabled:
        raise RuntimeError("OSS_ENABLED=false")
    client = get_s3_client()
    client.head_bucket(Bucket=settings.oss_bucket)
    return True
