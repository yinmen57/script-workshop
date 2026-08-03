"""业务 API 入口：仅挂载 /script-biz（剧本工坊领域 REST）。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.factory import create_base_app, mount_api_prefix
from app.routers import health
from app.routers.business import script_biz
from framework.infra.config import get_settings
from framework.infra.redis_client import close_redis


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = create_base_app(
        title="Script Workshop Business API",
        lifespan=lifespan,
    )
    mount_api_prefix(app, health.router, script_biz.router)
    return app


app = create_app()
