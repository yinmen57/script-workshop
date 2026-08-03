"""分镜规划：挂 narrative_space，重跑只清 ai（D5）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import (
    consistency_context,
    knowledge_context,
    llm,
    parse_service,
    project_service,
    revision_service,
)
from framework.domain.errors import NotFoundError, ValidationAppError
from framework.domain.ids import new_id


def _shot_public(row: dict[str, Any]) -> dict[str, Any]:
    camera = row.get("camera")
    if isinstance(camera, str):
        camera = json.loads(camera)
    character_ids = row.get("character_ids")
    if isinstance(character_ids, str):
        character_ids = json.loads(character_ids)
    prop_ids = row.get("prop_ids")
    if isinstance(prop_ids, str):
        prop_ids = json.loads(prop_ids)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "narrative_space_id": row["narrative_space_id"],
        "ordinal": int(row["ordinal"]),
        "scene_text": row.get("scene_text") or "",
        "beat": row.get("beat") or "",
        "character_ids": character_ids or [],
        "prop_ids": prop_ids or [],
        "camera": camera,
        "duration_sec": float(row["duration_sec"])
        if row.get("duration_sec") is not None
        else None,
        "status": row["status"],
        "record_status": row.get("record_status") or "ai",
    }


async def _require_space(
    session: AsyncSession, tenant_id: str, space_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM narrative_space
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("narrative space not found")
    return dict(row)


async def list_shots(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    if narrative_space_id:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM shot_plan
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND narrative_space_id = :narrative_space_id
                    ORDER BY ordinal ASC
                    """
                ),
                {
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "narrative_space_id": narrative_space_id,
                },
            )
        ).mappings().all()
    else:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM shot_plan
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                    ORDER BY narrative_space_id, ordinal ASC
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    items = [_shot_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def plan_shots_for_project(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """为项目下尚未有 confirmed 分镜的叙事空间规划分镜。"""
    await project_service.require_project(session, tenant_id, project_id)
    spaces = (
        await session.execute(
            text(
                """
                SELECT ns.*
                FROM narrative_space ns
                WHERE ns.project_id = :project_id AND ns.tenant_id = :tenant_id
                  AND NOT EXISTS (
                    SELECT 1 FROM shot_plan sp
                    WHERE sp.narrative_space_id = ns.id
                      AND sp.tenant_id = :tenant_id
                      AND sp.record_status = 'confirmed'
                  )
                ORDER BY ns.episode_id, ns.ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    results: list[dict[str, Any]] = []
    for space in spaces:
        results.append(
            await plan_shots_for_space(session, tenant_id, space["id"], commit=False)
        )
    await session.commit()
    total_shots = sum(int(r.get("total") or 0) for r in results)
    return {
        "spaces": results,
        "space_count": len(results),
        "total": total_shots,
    }


async def plan_shots_for_space(
    session: AsyncSession,
    tenant_id: str,
    narrative_space_id: str,
    *,
    commit: bool = True,
) -> dict:
    space = await _require_space(session, tenant_id, narrative_space_id)
    project_id = space["project_id"]
    project = await project_service.require_project(session, tenant_id, project_id)

    confirmed_exists = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM shot_plan
                WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
                  AND record_status = 'confirmed'
                """
            ),
            {"ns_id": narrative_space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]
    if int(confirmed_exists or 0) > 0:
        raise ValidationAppError(
            "该叙事空间已有确认分镜，请先反悔或手工清理后再重规划"
        )

    pack = await consistency_context.assemble_pack(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
        include_craft=False,
    )
    style_bible = pack["style_bible"]
    characters = pack["characters"]
    props = pack["props"]
    if not characters and not props:
        raise ValidationAppError("项目无人物或道具资产，无法规划分镜")

    # 只清本空间的 ai 分镜
    await session.execute(
        text(
            """
            DELETE FROM shot_plan
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": narrative_space_id, "tenant_id": tenant_id},
    )

    craft = await knowledge_context.assemble_shot_knowledge(tenant_id=tenant_id)
    system_prompt = llm.load_prompt("shot-planner/system.md")
    if craft:
        system_prompt = (
            system_prompt
            + "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n"
            + craft
        )
    # 工作台事实优先于工艺规范
    system_prompt = (
        system_prompt + "\n\n" + pack["prompt_block"]
        + "\n\n只输出 JSON，不要 markdown 说明。"
    )

    template = llm.load_prompt("shot-planner/plan-shots.md")
    scene_payload = {
        "id": space["id"],
        "title": space.get("title") or "",
        "summary": space.get("summary") or "",
        "time_place": space.get("time_place") or "",
        "estimated_duration_sec": space.get("estimated_duration_sec"),
        "source_text": (space.get("source_text") or "")[:6000],
        "scene_space": pack.get("scene_space"),
    }
    user_prompt = llm.render_prompt(
        template,
        style_bible=style_bible,
        scene=scene_payload,
        character_assets=characters,
        prop_assets=props,
    )
    parsed = await llm.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    shots = parsed.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValidationAppError("分镜规划结果为空")

    char_by_key = {c["character_key"]: c["id"] for c in characters}
    prop_by_key = {p["prop_key"]: p["id"] for p in props}

    created: list[dict[str, Any]] = []
    for i, item in enumerate(shots, start=1):
        if not isinstance(item, dict):
            continue
        ordinal = int(item.get("ordinal") or i)
        beat = (item.get("beat") or "").strip()
        scene_text = (item.get("scene_text") or beat).strip()
        camera_raw = item.get("camera")
        if isinstance(camera_raw, dict):
            camera = camera_raw
        elif isinstance(camera_raw, str) and camera_raw.strip():
            camera = {"description": camera_raw.strip()}
        else:
            camera = {}
        char_keys = item.get("character_keys") or []
        prop_keys = item.get("prop_keys") or []
        character_ids = [
            char_by_key[k]
            for k in char_keys
            if isinstance(k, str) and k in char_by_key
        ]
        prop_ids = [
            prop_by_key[k]
            for k in prop_keys
            if isinstance(k, str) and k in prop_by_key
        ]
        duration = item.get("duration_sec")
        try:
            duration_sec = float(duration) if duration is not None else None
        except (TypeError, ValueError):
            duration_sec = None

        shot_id = new_id("sshot")
        await session.execute(
            text(
                """
                INSERT INTO shot_plan
                  (id, tenant_id, project_id, narrative_space_id, ordinal,
                   scene_text, beat, character_ids, prop_ids, camera,
                   duration_sec, status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :narrative_space_id, :ordinal,
                   :scene_text, :beat, CAST(:character_ids AS JSON),
                   CAST(:prop_ids AS JSON), CAST(:camera AS JSON),
                   :duration_sec, 'draft', 'ai')
                """
            ),
            {
                "id": shot_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "narrative_space_id": narrative_space_id,
                "ordinal": ordinal,
                "scene_text": scene_text,
                "beat": beat,
                "character_ids": json.dumps(character_ids, ensure_ascii=False),
                "prop_ids": json.dumps(prop_ids, ensure_ascii=False),
                "camera": json.dumps(camera, ensure_ascii=False),
                "duration_sec": duration_sec,
            },
        )
        created.append(
            {
                "id": shot_id,
                "ordinal": ordinal,
                "beat": beat,
                "duration_sec": duration_sec,
            }
        )

    if commit:
        await session.commit()
    return {
        "narrative_space_id": narrative_space_id,
        "items": created,
        "total": len(created),
    }


async def confirm_shot(
    session: AsyncSession,
    tenant_id: str,
    shot_id: str,
    *,
    created_by: str | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM shot_plan
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": shot_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("shot not found")
    public = _shot_public(dict(row))
    if (row.get("record_status") or "ai") != "confirmed":
        await revision_service.save_revision(
            session,
            tenant_id=tenant_id,
            project_id=row["project_id"],
            target_type="shot_plan",
            target_id=shot_id,
            snapshot=public,
            change_reason="pin",
            created_by=created_by,
        )
    await session.execute(
        text(
            """
            UPDATE shot_plan
            SET record_status = 'confirmed', status = 'confirmed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": shot_id, "tenant_id": tenant_id},
    )
    await session.commit()
    refreshed = (
        await session.execute(
            text(
                """
                SELECT * FROM shot_plan
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": shot_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    return _shot_public(dict(refreshed))
