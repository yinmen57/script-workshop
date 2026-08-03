"""业务 Celery 任务：短作业 sync + 长耗时生成 submit/finalize/Beat。"""

from business.jobs.register import apply_business_celery_config

__all__ = ["apply_business_celery_config"]
