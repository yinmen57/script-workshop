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
    app_port: int = 8000
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

    queue_backend: str = "redis_stream"
    queue_stream_key: str = "ai_platform:ingest"
    # 剧本业务作业 Stream（第三段 Worker 消费）
    script_job_stream_key: str = "ai_platform:script_jobs"
    script_job_group: str = "script-workers"
    script_job_consumer_prefix: str = "worker"

    xinference_base_url: str = "http://127.0.0.1:9997"
    xinference_embedding_model_uid: str = "bge-m3"
    xinference_rerank_model_uid: str = "bge-reranker-v2-m3"

    # 默认 Chat LLM（火山方舟 OpenAI 兼容）；app.yaml model.primary=default 时直读
    llm_base_url: str = Field(..., min_length=1)
    llm_model: str = Field(..., min_length=1)
    llm_api_key: str = Field(..., min_length=1)
    llm_timeout: int = 60
    # 多 Agent 应用总空间：一级目录对应一个应用空间
    agent_workspace_root: str = "apps-space"

    # 赏舞（sd-2-c）开放 API：生图 / 生视频
    sd_enabled: bool = False
    sd_base_url: str = ""
    sd_api_key: str = ""
    sd_image_model: str = "doubao-seedream-5-0-260128"
    sd_video_model: str = "doubao-seedance-2-0-260128"
    sd_resolution: str = "2K"
    sd_character_size: str = "3:4"
    sd_three_view_size: str = "16:9"
    sd_character_view_size: str = "21:9"
    sd_background_size: str = "16:9"
    sd_request_timeout_seconds: int = 60
    sd_poll_interval_seconds: int = 3
    sd_poll_timeout_seconds: int = 300
    sd_video_duration: int = -1
    sd_video_resolution: str = "480p"
    sd_video_ratio: str = "adaptive"
    sd_video_poll_interval_seconds: int = 5
    sd_video_poll_timeout_seconds: int = 600
    sd_portrait_poll_interval_seconds: int = 5
    sd_portrait_poll_timeout_seconds: int = 300
    sd_portrait_wait_on_submit: bool = True

    @field_validator("oss_endpoint", "oss_sts_endpoint", "oss_public_base_url", "sd_base_url", mode="before")
    @classmethod
    def strip_str(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @property
    def sd_resolution_norm(self) -> str:
        """生图分辨率规范为小写（2k / 3k）。"""
        return (self.sd_resolution or "2k").strip().lower()

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
