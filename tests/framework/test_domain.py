# -*- coding: utf-8 -*-
"""domain：错误码、ID、权限、AuthContext。"""

from __future__ import annotations

import re

import pytest

from framework.domain.context import AuthContext
from framework.domain.errors import (
    AppError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationAppError,
)
from framework.domain.ids import new_id
from framework.domain.permissions import (
    APP_READ,
    APP_WRITE,
    AUDIT_READ,
    KB_READ,
    KB_WRITE,
    MODEL_READ,
    MODEL_WRITE,
    P0_PERMISSIONS,
)


def test_app_error_defaults() -> None:
    err = AppError("X", "msg")
    assert err.code == "X"
    assert err.message == "msg"
    assert err.status_code == 400
    assert err.details == {}


def test_error_subclasses_status() -> None:
    assert UnauthorizedError().status_code == 401
    assert ForbiddenError().status_code == 403
    assert NotFoundError().status_code == 404
    assert ValidationAppError("bad").status_code == 422
    assert ValidationAppError("bad", details={"f": 1}).details == {"f": 1}


def test_new_id_format_and_unique() -> None:
    a = new_id("usr")
    b = new_id("usr")
    assert re.fullmatch(r"usr_[0-9a-f]{16}", a)
    assert a != b


def test_p0_permissions_complete() -> None:
    expected = {
        MODEL_READ,
        MODEL_WRITE,
        KB_READ,
        KB_WRITE,
        APP_READ,
        APP_WRITE,
        AUDIT_READ,
    }
    assert P0_PERMISSIONS == expected


def test_auth_context_require() -> None:
    ctx = AuthContext(tenant_id="t1", actor="u1", permissions=[APP_READ])
    ctx.require(APP_READ)
    with pytest.raises(ForbiddenError):
        ctx.require(APP_WRITE)
