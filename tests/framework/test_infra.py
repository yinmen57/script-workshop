# -*- coding: utf-8 -*-
"""infra：配置派生、加解密、OSS key、enqueue、async_bridge。"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError


@pytest.mark.usefixtures("settings_env")
def test_settings_derived_fields() -> None:
    from framework.infra.config import get_settings

    settings = get_settings()
    assert "mysql+aiomysql://test_user:test_password@127.0.0.1:3306/test_db" in (
        settings.mysql_dsn
    )
    assert settings.redis_url == "redis://127.0.0.1:6379/0"
    assert settings.oss_endpoint_url == "https://oss-cn-hangzhou.aliyuncs.com"
    assert settings.oss_region_name == "cn-hangzhou"
    assert settings.oss_public_base.startswith("https://test-bucket.")


def test_settings_rejects_short_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    """环境变量覆盖 .env 时，过短 JWT_SECRET 应校验失败。"""
    from framework.infra.config import get_settings

    monkeypatch.setenv("JWT_SECRET", "short")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        get_settings()
    get_settings.cache_clear()


@pytest.mark.usefixtures("settings_env")
def test_crypto_roundtrip() -> None:
    from framework.infra.crypto import decrypt_secret, encrypt_secret

    cipher = encrypt_secret("sk-secret")
    assert cipher != "sk-secret"
    assert decrypt_secret(cipher) == "sk-secret"


@pytest.mark.usefixtures("settings_env")
def test_crypto_bad_cipher() -> None:
    from cryptography.fernet import InvalidToken

    from framework.infra.crypto import decrypt_secret

    with pytest.raises(InvalidToken):
        decrypt_secret("not-a-valid-token")


def test_build_object_key() -> None:
    from framework.infra.oss import build_object_key

    key = build_object_key("t1", "kb1", "d1", r"..\a\b\file.png")
    assert key == "t1/kb1/d1/file.png"


@pytest.mark.usefixtures("settings_env")
def test_public_url() -> None:
    from framework.infra.oss import public_url

    url = public_url("/path/to.bin")
    assert url.endswith("/path/to.bin")


@pytest.mark.usefixtures("settings_env")
def test_enqueue_task_names_and_queues() -> None:
    # celery_app 在 import 时读 Settings；fixture 已注入 env
    from framework.infra import celery_app as celery_mod
    from framework.infra.jobs import enqueue

    with patch.object(celery_mod.celery_app, "send_task") as send:
        enqueue.enqueue_sync_job("job-1")
        enqueue.enqueue_gen_submit("gen-1")
        enqueue.enqueue_gen_finalize("gen-2")
    assert send.call_args_list[0].args[0] == "sync.run_job_run"
    assert send.call_args_list[0].kwargs["queue"] == "sync"
    assert send.call_args_list[1].args[0] == "gen.submit_one"
    assert send.call_args_list[1].kwargs["queue"] == "gen.submit"
    assert send.call_args_list[2].args[0] == "gen.finalize_one"
    assert send.call_args_list[2].kwargs["queue"] == "gen.finalize"


def test_run_async_disposes() -> None:
    from framework.infra.async_bridge import run_async

    async def _work() -> str:
        return "ok"

    with (
        patch("framework.infra.db.dispose_engine", new_callable=AsyncMock) as dispose,
        patch("framework.infra.redis_client.close_redis", new_callable=AsyncMock) as close,
    ):
        assert run_async(_work()) == "ok"
        dispose.assert_awaited_once()
        close.assert_awaited_once()
