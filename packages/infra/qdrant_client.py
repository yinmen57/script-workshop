"""Qdrant 客户端。"""

from __future__ import annotations

from qdrant_client import QdrantClient

from packages.infra.config import get_settings

_client: QdrantClient | None = None


def get_qdrant() -> QdrantClient:
    global _client
    if _client is None:
        settings = get_settings()
        kwargs: dict = {
            "host": settings.qdrant_host,
            "port": settings.qdrant_port,
        }
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        _client = QdrantClient(**kwargs)
    return _client


def ping_qdrant() -> bool:
    client = get_qdrant()
    client.get_collections()
    return True
