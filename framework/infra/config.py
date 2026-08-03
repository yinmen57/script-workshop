"""应用配置：缺少必填项时启动失败。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 仓库根目录 .env（无论从 apps/api 还是根目录启动）
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT_ENV) if _ROOT_ENV.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    # 框架 API 宿主机端口（容器内仍用 8000）
    app_port: int = 8000
    # 业务 API 宿主机端口（compose 映射；本地 run_biz 直接监听）
    biz_app_port: int = 42868
    app_debug: bool = True
    # 管理端来源，逗号分隔；前后端分离时由 CORS 放行
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    jwt_secret: str = Field(..., min_length=8)
    jwt_expire_minutes: int = 120
    api_key_hash_salt: str = Field(..., min_length=8)
    secret_encrypt_key: str = Field(..., min_length=8)

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = Field(...)
    mysql_password: str = Field(...)
    mysql_database: str = "ai_platform"

    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    qdrant_host: str = "127.0.0.1"
    qdrant_port: int = 6333
    qdrant_api_key: str = ""

    # 阿里云 OSS（官方 oss2 SDK）
    oss_enabled: bool = True
    oss_endpoint: str = Field(..., min_length=1)
    oss_bucket: str = Field(..., min_length=1)
    oss_access_key_id: str = Field(..., min_length=1)
    oss_access_key_secret: str = Field(..., min_length=1)
    # 公开访问前缀，如 https://bucket.oss-cn-hangzhou.aliyuncs.com/
    oss_public_base_url: str = ""
    # 未显式配置时从 endpoint 推导（oss-cn-hangzhou.aliyuncs.com -> cn-hangzhou）
    oss_region: str = ""
    # 浏览器直传 STS（未配 Role ARN 时不做 STS）
    oss_sts_role_arn: str = ""
    oss_sts_endpoint: str = "sts.cn-hangzhou.aliyuncs.com"
    oss_sts_duration_seconds: int = 900

    # 阿里云短信（验证码登录等）
    sms_enabled: bool = False
    sms_access_key_id: str = ""
    sms_access_key_secret: str = ""
    sms_sign_name: str = ""
    sms_login_template_code: str = ""
    sms_endpoint: str = "dysmsapi.aliyuncs.com"
    sms_code_expire_seconds: int = 300
    sms_resend_seconds: int = 60
    sms_max_attempts: int = 5

    # 作业总线：Celery + RabbitMQ
    celery_broker_url: str = Field(
        ...,
        min_length=1,
        description="如 amqp://guest:guest@127.0.0.1:5672//",
    )
    celery_result_backend: str = ""
    celery_task_default_queue: str = "sync"
    celery_task_acks_late: bool = True
    celery_worker_prefetch_multiplier: int = 1
    # 生成槽位（Beat）
    gen_max_inflight_per_tenant: int = 3
    gen_submit_batch: int = 20
    gen_poll_batch: int = 50

    @field_validator("oss_endpoint", "oss_sts_endpoint", "oss_public_base_url", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def oss_endpoint_url(self) -> str:
        """oss2 Endpoint，补全 https://。"""
        ep = self.oss_endpoint.rstrip("/")
        if ep.startswith("http://") or ep.startswith("https://"):
            return ep
        return f"https://{ep}"

    @property
    def oss_region_name(self) -> str:
        if self.oss_region:
            return self.oss_region
        # oss-cn-hangzhou.aliyuncs.com / https://oss-cn-hangzhou.aliyuncs.com
        host = self.oss_endpoint_url.removeprefix("https://").removeprefix("http://")
        if host.startswith("oss-") and ".aliyuncs.com" in host:
            return host[len("oss-") : host.index(".aliyuncs.com")]
        raise ValueError("OSS_REGION 未配置且无法从 OSS_ENDPOINT 推导")

    @property
    def oss_public_base(self) -> str:
        base = self.oss_public_base_url.rstrip("/")
        if base:
            return base
        return f"https://{self.oss_bucket}.{self.oss_endpoint_url.removeprefix('https://').removeprefix('http://')}"

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return (
                f"redis://:{self.redis_password}@{self.redis_host}:"
                f"{self.redis_port}/{self.redis_db}"
            )
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
