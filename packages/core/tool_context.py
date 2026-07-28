"""工具调用上下文：由 agent_runtime 注入，供 apps-space 工具读取租户。"""

from __future__ import annotations

from contextvars import ContextVar

current_tenant_id: ContextVar[str | None] = ContextVar("current_tenant_id", default=None)


def require_tenant_id() -> str:
    tenant_id = current_tenant_id.get()
    if not tenant_id:
        raise RuntimeError("工具上下文缺少 tenant_id，无法调用业务服务")
    return tenant_id
