"""把业务队列、路由、Beat、任务模块挂到框架 Celery 壳上。"""

from __future__ import annotations

from celery import Celery
from kombu import Queue

from framework.infra.celery_app import celery_app as _default_app

_APPLIED = False


def apply_business_celery_config(app: Celery | None = None) -> Celery:
    """幂等：Worker / Beat 入口调用一次即可。"""
    global _APPLIED
    target = app or _default_app
    if _APPLIED and target is _default_app:
        return target

    target.conf.update(
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
            "business.jobs.sync_tasks",
            "business.jobs.gen_tasks",
        ),
    )
    if target is _default_app:
        _APPLIED = True
    return target
