"""Redis Stream 薄封装：剧本作业投递与消费。"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from redis.exceptions import ResponseError

from packages.infra.config import get_settings
from packages.infra.redis_client import get_redis

logger = logging.getLogger(__name__)


async def ensure_script_job_group() -> None:
    """创建消费组（已存在则忽略）。"""
    settings = get_settings()
    client = get_redis()
    try:
        await client.xgroup_create(
            name=settings.script_job_stream_key,
            groupname=settings.script_job_group,
            id="0",
            mkstream=True,
        )
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def enqueue_script_job(fields: dict[str, Any]) -> str:
    """写入一条作业消息，返回 stream entry id。"""
    settings = get_settings()
    client = get_redis()
    payload = {k: "" if v is None else str(v) for k, v in fields.items()}
    entry_id = await client.xadd(settings.script_job_stream_key, payload)
    return str(entry_id)


async def read_script_jobs(
    *,
    consumer_name: str,
    count: int = 1,
    block_ms: int = 5000,
) -> list[tuple[str, dict[str, str]]]:
    """从消费组读取消息，返回 [(entry_id, fields), ...]。"""
    settings = get_settings()
    client = get_redis()
    await ensure_script_job_group()
    rows = await client.xreadgroup(
        groupname=settings.script_job_group,
        consumername=consumer_name,
        streams={settings.script_job_stream_key: ">"},
        count=count,
        block=block_ms,
    )
    if not rows:
        return []
    out: list[tuple[str, dict[str, str]]] = []
    for _stream, messages in rows:
        for entry_id, data in messages:
            out.append((str(entry_id), dict(data)))
    return out


async def ack_script_job(entry_id: str) -> None:
    settings = get_settings()
    client = get_redis()
    await client.xack(
        settings.script_job_stream_key,
        settings.script_job_group,
        entry_id,
    )


async def iter_script_jobs(
    *,
    consumer_name: str,
    count: int = 1,
    block_ms: int = 5000,
) -> AsyncIterator[tuple[str, dict[str, str]]]:
    while True:
        batch = await read_script_jobs(
            consumer_name=consumer_name, count=count, block_ms=block_ms
        )
        if not batch:
            continue
        for item in batch:
            yield item
