"""Celery 应用：作业总线唯一入口。"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from packages.infra.config import get_settings

settings = get_settings()

celery_app = Celery("ai_platform")
celery_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend or None,
    task_default_queue=settings.celery_task_default_queue,
    task_acks_late=settings.celery_task_acks_late,
    worker_prefetch_multiplier=settings.celery_worker_prefetch_multiplier,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_queues=(
        Queue("sync"),
        Queue("gen.submit"),
        Queue("gen.finalize"),
    ),
    task_routes={
        "sync.*": {"queue": "sync"},
        "gen.submit_one": {"queue": "gen.submit"},
        "gen.finalize_one": {"queue": "gen.finalize"},
        "gen.dispatch_pending": {"queue": "sync"},
        "gen.poll_waiting": {"queue": "sync"},
        "gen.reconcile": {"queue": "sync"},
    },
    beat_schedule={
        "gen-dispatch-pending": {
            "task": "gen.dispatch_pending",
            "schedule": 10.0,
        },
        "gen-poll-waiting": {
            "task": "gen.poll_waiting",
            "schedule": 30.0,
        },
        "gen-reconcile": {
            "task": "gen.reconcile",
            "schedule": 300.0,
        },
    },
    imports=(
        "packages.infra.jobs.sync_tasks",
        "packages.infra.jobs.gen_tasks",
    ),
)
