"""FastAPI 入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.exception_handlers import register_exception_handlers
from app.middleware import RequestIdMiddleware
from app.routers import apps, auth, chat, health, index, models, script_biz
from packages.infra.config import get_settings
from packages.infra.redis_client import close_redis


@asynccontextmanager
async def lifespan(_: FastAPI):
    # 启动时强制加载配置；缺失必填项会直接失败
    get_settings()
    from packages.agent_apps.registry import register_builtin_apps
    from packages.governance.chat_service import ensure_chat_schema
    from packages.infra.db import get_session_factory

    # 剧本业务表由 Alembic 管理，不再在启动时 ensure
    async with get_session_factory()() as session:
        await ensure_chat_schema(session)
    register_builtin_apps()
    yield
    await close_redis()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Enterprise AI Platform API",
        version="0.1.0",
        lifespan=lifespan,
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

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(models.router, prefix="/api/v1")
    app.include_router(index.router, prefix="/api/v1")
    app.include_router(apps.router, prefix="/api/v1")
    app.include_router(chat.router, prefix="/api/v1")
    app.include_router(script_biz.router, prefix="/api/v1")
    return app


app = create_app()
