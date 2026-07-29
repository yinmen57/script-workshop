"""定版废稿历史：确认 / 修改前快照，供反悔写回。

AI 重跑删除的 ai 记录不进历史（见 06 §5）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.ids import new_id


async def next_revision_no(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: str,
) -> int:
    value = (
        await session.execute(
            text(
                """
                SELECT COALESCE(MAX(revision_no), 0) AS m
                FROM record_revision
                WHERE target_type = :target_type AND target_id = :target_id
                """
            ),
            {"target_type": target_type, "target_id": target_id},
        )
    ).mappings().first()["m"]
    return int(value) + 1


async def save_revision(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    target_type: str,
    target_id: str,
    snapshot: dict[str, Any],
    change_reason: str,
    created_by: str | None = None,
) -> dict[str, Any]:
    """写入一条废稿快照，不 commit。"""
    rev_no = await next_revision_no(
        session, target_type=target_type, target_id=target_id
    )
    rev_id = new_id("srev")
    await session.execute(
        text(
            """
            INSERT INTO record_revision
              (id, tenant_id, project_id, target_type, target_id,
               revision_no, snapshot, change_reason, created_by)
            VALUES
              (:id, :tenant_id, :project_id, :target_type, :target_id,
               :revision_no, CAST(:snapshot AS JSON), :change_reason, :created_by)
            """
        ),
        {
            "id": rev_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "target_type": target_type,
            "target_id": target_id,
            "revision_no": rev_no,
            "snapshot": json.dumps(snapshot, ensure_ascii=False),
            "change_reason": change_reason,
            "created_by": created_by,
        },
    )
    return {
        "id": rev_id,
        "revision_no": rev_no,
        "change_reason": change_reason,
    }


async def list_revisions(
    session: AsyncSession,
    *,
    tenant_id: str,
    target_type: str,
    target_id: str,
) -> dict:
    rows = (
        await session.execute(
            text(
                """
                SELECT id, target_type, target_id, revision_no, snapshot,
                       change_reason, created_by, created_at
                FROM record_revision
                WHERE tenant_id = :tenant_id
                  AND target_type = :target_type
                  AND target_id = :target_id
                ORDER BY revision_no DESC
                """
            ),
            {
                "tenant_id": tenant_id,
                "target_type": target_type,
                "target_id": target_id,
            },
        )
    ).mappings().all()
    items = []
    for r in rows:
        snap = r["snapshot"]
        if isinstance(snap, str):
            snap = json.loads(snap)
        items.append(
            {
                "id": r["id"],
                "target_type": r["target_type"],
                "target_id": r["target_id"],
                "revision_no": int(r["revision_no"]),
                "snapshot": snap,
                "change_reason": r["change_reason"],
                "created_by": r.get("created_by"),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
            }
        )
    return {"items": items, "total": len(items)}
