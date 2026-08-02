"""短业务作业：sync 队列。"""

from __future__ import annotations

import logging

from packages.infra.async_bridge import run_async
from packages.infra.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="sync.run_job_run", bind=True, acks_late=True)
def run_job_run(self, job_run_id: str) -> None:
    from packages.business_script.job_dispatch import process_job_message

    logger.info("sync.run_job_run start job_run_id=%s", job_run_id)
    run_async(process_job_message(job_run_id))
