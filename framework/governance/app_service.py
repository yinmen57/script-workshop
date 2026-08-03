"""应用运行时视图：从代码注册表按 slug 组装。"""

from __future__ import annotations

from framework.agent_apps import registry


def get_app(tenant_id: str, slug: str) -> dict:
    """按 slug 取可运行应用（协调 Agent + 工具 + 模型逻辑名）。"""
    return registry.get_runtime_app(tenant_id, slug)
