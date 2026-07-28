"""Redis 客户端。"""

from __future__ import annotations

from redis.asyncio import Redis

from packages.infra.config import get_settings

_redis: Redis | None = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        _redis = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def ping_redis() -> bool:
    client = get_redis()
    return bool(await client.ping())


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
