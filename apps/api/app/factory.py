"""FastAPI 应用工厂：框架 API / 业务 API 共用中间件与异常处理。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.exception_handlers import register_exception_handlers
from app.middleware import RequestIdMiddleware
from framework.infra.config import get_settings
from framework.infra.redis_client import close_redis


Lifespan = Callable[[FastAPI], AsyncIterator[None]]


def create_base_app(
    *,
    title: str,
    version: str = "0.1.0",
    lifespan: Lifespan | None = None,
) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def _default_lifespan(_: FastAPI):
        get_settings()
        yield
        await close_redis()

    app = FastAPI(
        title=title,
        version=version,
        lifespan=lifespan or _default_lifespan,
        debug=settings.app_debug,
    )
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)
    return app


def mount_api_prefix(app: FastAPI, *routers: Any) -> None:
    for router in routers:
        app.include_router(router, prefix="/api/v1")
