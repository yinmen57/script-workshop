# -*- coding: utf-8 -*-
"""agent_apps.tooling：entrypoint、wrap、retrieve 白名单。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from framework.agent_apps.tooling import (
    build_business_tools,
    build_retrieve_tool,
    resolve_entrypoint,
    wrap_business_tool,
)
from tests.framework import _fake_tools


def test_resolve_entrypoint_ok() -> None:
    func = resolve_entrypoint("tests.framework._fake_tools:echo_text")
    assert func is _fake_tools.echo_text


@pytest.mark.parametrize(
    "bad",
    ["no_colon", ":only_func", "only_mod:", "tests.framework._fake_tools:missing"],
)
def test_resolve_entrypoint_invalid(bad: str) -> None:
    with pytest.raises((ValueError, AttributeError)):
        resolve_entrypoint(bad)


@pytest.mark.asyncio
async def test_wrap_business_tool_injects_tenant() -> None:
    tool = wrap_business_tool(
        tool_id="echo",
        func=_fake_tools.echo_text,
        description="echo",
        tenant_id="tenant-x",
    )
    raw = await tool.ainvoke({"text": "hi"})
    data = json.loads(raw)
    assert data == {"text": "hi", "tenant_id": "tenant-x"}


@pytest.mark.asyncio
async def test_wrap_business_tool_captures_error() -> None:
    tool = wrap_business_tool(
        tool_id="boom",
        func=_fake_tools.boom,
        description="boom",
        tenant_id="tenant-x",
    )
    raw = await tool.ainvoke({"text": "x"})
    data = json.loads(raw)
    assert "tool exploded" in data["error"]
    assert "traceback" in data


@pytest.mark.asyncio
async def test_build_business_tools_unknown() -> None:
    with pytest.raises(ValueError, match="未知工具"):
        build_business_tools(
            tool_ids=["nope"],
            tenant_id="t1",
            tool_catalog={},
        )


@pytest.mark.asyncio
async def test_build_business_tools_missing_entrypoint() -> None:
    with pytest.raises(ValueError, match="entrypoint"):
        build_business_tools(
            tool_ids=["echo"],
            tenant_id="t1",
            tool_catalog={"echo": {"description": "x"}},
        )


@pytest.mark.asyncio
async def test_build_business_tools_ok() -> None:
    tools = build_business_tools(
        tool_ids=["echo"],
        tenant_id="t1",
        tool_catalog={
            "echo": {
                "description": "echo",
                "entrypoint": "tests.framework._fake_tools:echo_async",
            }
        },
    )
    assert len(tools) == 1
    raw = await tools[0].ainvoke({"text": "async"})
    assert json.loads(raw)["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_retrieve_namespace_whitelist() -> None:
    tool = build_retrieve_tool(namespaces=["ns.a"], tenant_id="t1")
    denied = json.loads(await tool.ainvoke({"namespace": "ns.b", "query": "q"}))
    assert "不在允许范围" in denied["error"]

    fake_result: dict[str, Any] = {"items": [{"content": "hit"}]}
    with patch(
        "framework.governance.vector_namespace_service.search",
        new=AsyncMock(return_value=fake_result),
    ) as mocked:
        ok = json.loads(
            await tool.ainvoke({"namespace": "ns.a", "query": "问题", "top_k": 3})
        )
        assert ok == fake_result
        mocked.assert_awaited_once()
        kwargs = mocked.await_args.kwargs
        assert kwargs["tenant_id"] == "t1"
        assert kwargs["namespaces"] == ["ns.a"]
        assert kwargs["top_k"] == 3
