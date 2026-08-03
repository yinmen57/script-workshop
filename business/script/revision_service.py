"""定版废稿历史：确认 / 修改前快照，供反悔写回。

AI 重跑删除的 ai 记录不进历史（见 06 §5）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from framework.domain.ids import new_id


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


# 反悔可写回的字段（按 target_type）
_REVERT_FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "narrative_space": (
        "narrative_space",
        ("title", "summary", "time_place", "source_text", "estimated_duration_sec", "ordinal"),
    ),
    "shot_plan": (
        "shot_plan",
        ("scene_text", "beat", "character_ids", "prop_ids", "camera", "duration_sec", "ordinal"),
    ),
    "video_prompt": (
        "video_prompt",
        ("prompt_text", "negative_prompt", "ref_image_ids", "duration_sec"),
    ),
    "material_prompt": (
        "material_prompt",
        ("prompt_text", "negative_prompt", "style_ref"),
    ),
}


async def revert_to_revision(
    session: AsyncSession,
    *,
    tenant_id: str,
    revision_id: str,
    created_by: str | None = None,
) -> dict:
    """把历史 revision 写回主记录；写回前先快照当前内容。"""
    from framework.domain.errors import NotFoundError, ValidationAppError

    rev = (
        await session.execute(
            text(
                """
                SELECT * FROM record_revision
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": revision_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if rev is None:
        raise NotFoundError("revision not found")

    target_type = rev["target_type"]
    target_id = rev["target_id"]
    if target_type not in _REVERT_FIELDS:
        raise ValidationAppError(f"不支持反悔的类型：{target_type}")

    table, fields = _REVERT_FIELDS[target_type]
    current = (
        await session.execute(
            text(
                f"""
                SELECT * FROM {table}
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": target_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if current is None:
        raise NotFoundError(f"{target_type} not found")

    snap = rev["snapshot"]
    if isinstance(snap, str):
        snap = json.loads(snap)
    if not isinstance(snap, dict):
        raise ValidationAppError("revision snapshot 无效")

    # 写回前保留当前态
    current_snap = {k: current.get(k) for k in fields if k in current.keys()}
    current_snap["record_status"] = current.get("record_status")
    current_snap["status"] = current.get("status")
    await save_revision(
        session,
        tenant_id=tenant_id,
        project_id=rev["project_id"],
        target_type=target_type,
        target_id=target_id,
        snapshot=current_snap,
        change_reason="revert",
        created_by=created_by,
    )

    updates: dict[str, Any] = {}
    json_fields = {
        "character_ids",
        "prop_ids",
        "camera",
        "ref_image_ids",
        "style_ref",
    }
    for key in fields:
        if key not in snap:
            continue
        val = snap[key]
        if key in json_fields and val is not None and not isinstance(val, str):
            updates[key] = json.dumps(val, ensure_ascii=False)
        else:
            updates[key] = val
    if not updates:
        raise ValidationAppError("快照无可写回字段")

    set_parts: list[str] = []
    params: dict[str, Any] = {"id": target_id, "tenant_id": tenant_id}
    for key, val in updates.items():
        if key in json_fields and isinstance(val, str):
            set_parts.append(f"{key} = CAST(:{key} AS JSON)")
        else:
            set_parts.append(f"{key} = :{key}")
        params[key] = val
    # 反悔后保持 confirmed（已定版内容的回退）
    set_parts.append("record_status = 'confirmed'")
    if "status" in current.keys():
        set_parts.append("status = 'confirmed'")

    await session.execute(
        text(
            f"""
            UPDATE {table}
            SET {', '.join(set_parts)}
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        params,
    )
    await session.commit()
    refreshed = (
        await session.execute(
            text(
                f"""
                SELECT * FROM {table}
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": target_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    return {
        "target_type": target_type,
        "target_id": target_id,
        "revision_id": revision_id,
        "record": dict(refreshed) if refreshed else None,
    }
