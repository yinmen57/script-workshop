# -*- coding: utf-8 -*-
"""测试用工具入口，供 tooling.resolve_entrypoint 动态加载。"""

from __future__ import annotations

from framework.core.tool_context import require_tenant_id


def echo_text(text: str) -> dict:
    """同步工具：回显文本并带上租户。"""
    return {"text": text, "tenant_id": require_tenant_id()}


async def echo_async(text: str, flag: bool = True) -> dict:
    """异步工具。"""
    return {"text": text, "flag": flag, "tenant_id": require_tenant_id()}


def boom(text: str = "") -> None:
    """故意抛错，验证 wrap 捕获。"""
    raise RuntimeError("tool exploded")
