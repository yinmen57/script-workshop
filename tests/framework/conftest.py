# -*- coding: utf-8 -*-
"""框架测试公共夹具：隔离 Settings，清空 Agent 注册表。"""

from __future__ import annotations

import pytest


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入最小必填环境变量，并清空 get_settings 缓存。"""
    env = {
        "JWT_SECRET": "test-jwt-secret-key",
        "API_KEY_HASH_SALT": "test-api-key-salt",
        "SECRET_ENCRYPT_KEY": "test-secret-encrypt-key",
        "MYSQL_USER": "test_user",
        "MYSQL_PASSWORD": "test_password",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "test_db",
        "OSS_ENDPOINT": "oss-cn-hangzhou.aliyuncs.com",
        "OSS_BUCKET": "test-bucket",
        "OSS_ACCESS_KEY_ID": "test-ak",
        "OSS_ACCESS_KEY_SECRET": "test-sk",
        # 清空公开前缀，强制走 bucket+endpoint 推导，避免本地 .env 串扰
        "OSS_PUBLIC_BASE_URL": "",
        "OSS_REGION": "",
        "CELERY_BROKER_URL": "amqp://guest:guest@127.0.0.1:5672//",
        "APP_ENV": "test",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from framework.infra.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_agent_registry() -> None:
    """每个用例前后清空注册表，避免串扰。"""
    from framework.agent_apps.registry import clear_apps

    clear_apps()
    yield
    clear_apps()
