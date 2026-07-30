"""Redis 客户端。"""

from __future__ import annotations

from redis.asyncio import Redis

from packages.infra.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        # socket_timeout=None：允许 XREADGROUP 等阻塞命令超过默认读超时
        _redis = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=None,
        )
    return _redis


async def ping_redis() -> bool:
    client = get_redis()
    return bool(await client.ping())


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
