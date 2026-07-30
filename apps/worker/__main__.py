"""剧本业务作业 Worker：消费 Redis Stream 并执行 job_dispatch。

启动：
  python -m apps.worker
容器：
  command: ["python", "-m", "apps.worker"]
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal

from packages.business_script.job_dispatch import process_job_message
from packages.infra.config import get_settings
from packages.infra.queue_stream import ack_script_job, ensure_script_job_group, read_script_jobs
from packages.infra.redis_client import close_redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [script-worker] %(message)s",
)
logger = logging.getLogger("script-worker")

_stop = asyncio.Event()


def _request_stop(*_args: object) -> None:
    _stop.set()


async def run_forever() -> None:
    settings = get_settings()
    consumer = (
        f"{settings.script_job_consumer_prefix}-"
        f"{os.environ.get('HOSTNAME', 'local')}-"
        f"{os.getpid()}"
    )
    await ensure_script_job_group()
    logger.info(
        "listening stream=%s group=%s consumer=%s",
        settings.script_job_stream_key,
        settings.script_job_group,
        consumer,
    )
    while not _stop.is_set():
        try:
            batch = await read_script_jobs(
                consumer_name=consumer, count=1, block_ms=5000
            )
        except Exception:  # noqa: BLE001
            logger.exception("xreadgroup failed")
            await asyncio.sleep(2)
            continue
        if not batch:
            continue
        for entry_id, fields in batch:
            job_id = fields.get("job_id") or ""
            if not job_id:
                logger.warning("skip message without job_id: %s", fields)
                await ack_script_job(entry_id)
                continue
            try:
                await process_job_message(job_id)
            except Exception:  # noqa: BLE001
                logger.exception("process job %s crashed", job_id)
            finally:
                await ack_script_job(entry_id)


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            # Windows 不支持 add_signal_handler
            signal.signal(sig, lambda *_: _request_stop())
    try:
        loop.run_until_complete(run_forever())
    finally:
        loop.run_until_complete(close_redis())
        loop.close()


if __name__ == "__main__":
    main()
