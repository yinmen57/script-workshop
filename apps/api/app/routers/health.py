"""健康检查。"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas import HealthResponse, ReadyResponse
from framework.infra.db import ping_mysql
from framework.infra.oss import ping_oss
from framework.infra.qdrant_client import ping_qdrant
from framework.infra.redis_client import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready() -> ReadyResponse:
    dependencies: dict[str, str] = {}

    async def check(name: str, fn) -> None:
        try:
            result = fn()
            if hasattr(result, "__await__"):
                await result
            dependencies[name] = "up"
        except Exception:
            dependencies[name] = "down"

    await check("mysql", ping_mysql)
    await check("redis", ping_redis)
    await check("qdrant", ping_qdrant)
    await check("oss", ping_oss)

    ready_flag = all(v == "up" for v in dependencies.values())
    return ReadyResponse(ready=ready_flag, dependencies=dependencies)
