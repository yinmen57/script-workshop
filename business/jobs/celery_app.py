"""业务 Worker / Beat 入口：框架壳 + 业务队列与任务注册。

docker-compose / 命令行：
  celery -A business.jobs.celery_app worker ...
  celery -A business.jobs.celery_app beat ...
"""

from __future__ import annotations

from business.jobs.register import apply_business_celery_config
from framework.infra.celery_app import celery_app

apply_business_celery_config(celery_app)

# Celery -A 默认查找 app
app = celery_app

__all__ = ["app", "celery_app"]
