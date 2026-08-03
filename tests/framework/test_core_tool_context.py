# -*- coding: utf-8 -*-
"""core：工具租户上下文。"""

from __future__ import annotations

import pytest

from framework.core.tool_context import current_tenant_id, require_tenant_id


def test_require_tenant_id_missing() -> None:
    token = current_tenant_id.set(None)
    try:
        with pytest.raises(RuntimeError, match="tenant_id"):
            require_tenant_id()
    finally:
        current_tenant_id.reset(token)


def test_require_tenant_id_ok() -> None:
    token = current_tenant_id.set("tenant-a")
    try:
        assert require_tenant_id() == "tenant-a"
    finally:
        current_tenant_id.reset(token)
