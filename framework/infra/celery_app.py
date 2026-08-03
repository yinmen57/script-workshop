"""Celery 应用壳：仅 broker / 序列化等通用配置，不含业务队列与任务。"""

from __future__ import annotations

from celery import Celery

from framework.infra.config import get_settings

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
)
