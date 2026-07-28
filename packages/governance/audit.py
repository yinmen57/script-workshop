"""审计写入。"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def write_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor: str,
    action: str,
    request_id: str | None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip: str | None = None,
    payload: dict | None = None,
) -> None:
    import json

    await session.execute(
        text(
            """
            INSERT INTO audit_log
              (tenant_id, actor, action, resource_type, resource_id, request_id, ip, payload)
            VALUES
              (:tenant_id, :actor, :action, :resource_type, :resource_id, :request_id, :ip, :payload)
            """
        ),
        {
            "tenant_id": tenant_id,
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "request_id": request_id,
            "ip": ip,
            "payload": json.dumps(payload or {}, ensure_ascii=False),
        },
    )
    await session.commit()
