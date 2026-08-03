"""框架 API 入口：应用空间、调试对话、向量索引、AI Key、鉴权。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.factory import create_base_app, mount_api_prefix
from app.routers import apps, auth, chat, health, index, models
from framework.infra.config import get_settings
from framework.infra.redis_client import close_redis


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_settings()
    from business.apps import register_business_apps
    from framework.governance.chat_service import ensure_chat_schema
    from framework.infra.db import get_session_factory

    async with get_session_factory()() as session:
        await ensure_chat_schema(session)
    # Agent 应用插件注入框架注册表（供 /apps 与 /chat）
    register_business_apps()
    yield
    await close_redis()


def create_app() -> FastAPI:
    app = create_base_app(
        title="Agent Framework API",
        lifespan=lifespan,
    )
    mount_api_prefix(
        app,
        health.router,
        auth.router,
        models.router,
        index.router,
        apps.router,
        chat.router,
    )
    return app


app = create_app()
