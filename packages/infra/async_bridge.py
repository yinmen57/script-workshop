"""在同步 Celery Worker 中跑异步协程。"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """每次新建事件循环；结束后释放 async 引擎，避免跨 loop 复用连接池。"""

    async def _runner() -> T:
        from packages.infra.db import dispose_engine
        from packages.infra.redis_client import close_redis

        try:
            return await coro
        finally:
            await dispose_engine()
            await close_redis()

    return asyncio.run(_runner())
