# -*- coding: utf-8 -*-
"""governance.security：密码、JWT、API Key 哈希。"""

from __future__ import annotations

import pytest

from framework.domain.errors import UnauthorizedError
from framework.governance import security


@pytest.mark.usefixtures("settings_env")
def test_password_hash_roundtrip() -> None:
    hashed = security.hash_password("Secret@123")
    assert security.verify_password("Secret@123", hashed)
    assert not security.verify_password("wrong", hashed)


@pytest.mark.usefixtures("settings_env")
def test_access_token_roundtrip() -> None:
    token = security.create_access_token(
        user_id="u1",
        tenant_id="t1",
        permissions=["app:read"],
        expires_minutes=5,
    )
    payload = security.decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["tenant_id"] == "t1"
    assert payload["type"] == "access"
    assert payload["permissions"] == ["app:read"]


@pytest.mark.usefixtures("settings_env")
def test_refresh_token_has_refresh_type() -> None:
    token = security.create_refresh_token(user_id="u1", tenant_id="t1")
    payload = security.decode_token(token)
    assert payload["type"] == "refresh"


@pytest.mark.usefixtures("settings_env")
def test_decode_invalid_token() -> None:
    with pytest.raises(UnauthorizedError):
        security.decode_token("not.a.jwt")


@pytest.mark.usefixtures("settings_env")
def test_hash_api_key_stable() -> None:
    a = security.hash_api_key("sk_test")
    b = security.hash_api_key("sk_test")
    assert a == b
    assert len(a) == 64
    assert a != security.hash_api_key("sk_other")
