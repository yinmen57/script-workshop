"""统一投递。"""

from __future__ import annotations

from framework.infra.celery_app import celery_app


def enqueue_sync_job(job_run_id: str) -> None:
    celery_app.send_task("sync.run_job_run", args=[job_run_id], queue="sync")


def enqueue_gen_submit(generation_task_id: str) -> None:
    celery_app.send_task(
        "gen.submit_one", args=[generation_task_id], queue="gen.submit"
    )


def enqueue_gen_finalize(generation_task_id: str) -> None:
    celery_app.send_task(
        "gen.finalize_one", args=[generation_task_id], queue="gen.finalize"
    )
