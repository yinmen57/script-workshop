"""作业投递封装：业务只走这里，不直接碰 Celery。"""

from __future__ import annotations

from framework.infra.jobs.enqueue import enqueue_gen_finalize, enqueue_gen_submit, enqueue_sync_job

__all__ = [
    "enqueue_sync_job",
    "enqueue_gen_submit",
    "enqueue_gen_finalize",
]
