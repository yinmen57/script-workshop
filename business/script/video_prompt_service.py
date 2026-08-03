"""成片提示词：一视频片段一段（D1）。

输入聚合该片段包含的分镜 + 资产锚点，叙事空间只作上下文；重跑只清 ai。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import (
    consistency_context,
    knowledge_context,
    llm,
    project_service,
    revision_service,
    shot_service,
    video_segment_service,
)
from framework.domain.errors import NotFoundError, ValidationAppError
from framework.domain.ids import new_id


def _prompt_public(row: dict[str, Any]) -> dict[str, Any]:
    ref_ids = row.get("ref_image_ids")
    if isinstance(ref_ids, str):
        ref_ids = json.loads(ref_ids)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "video_segment_id": row["video_segment_id"],
        "narrative_space_id": row["narrative_space_id"],
        "prompt_text": row["prompt_text"],
        "negative_prompt": row.get("negative_prompt") or "",
        "ref_image_ids": ref_ids or [],
        "duration_sec": float(row["duration_sec"])
        if row.get("duration_sec") is not None
        else None,
        "version": int(row["version"]),
        "status": row["status"],
        "record_status": row.get("record_status") or "ai",
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
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


async def list_video_prompts(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
    video_segment_id: str | None = None,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    conditions = ["project_id = :project_id", "tenant_id = :tenant_id"]
    params: dict[str, Any] = {"project_id": project_id, "tenant_id": tenant_id}
    if video_segment_id:
        conditions.append("video_segment_id = :video_segment_id")
        params["video_segment_id"] = video_segment_id
    if narrative_space_id:
        conditions.append("narrative_space_id = :narrative_space_id")
        params["narrative_space_id"] = narrative_space_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT * FROM video_prompt
                WHERE {" AND ".join(conditions)}
                ORDER BY narrative_space_id, video_segment_id, version DESC
                """
            ),
            params,
        )
    ).mappings().all()
    items = [_prompt_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def generate_for_project(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """为尚未有 confirmed 成片提示词的视频片段生成。"""
    await project_service.require_project(session, tenant_id, project_id)
    segments = (
        await session.execute(
            text(
                """
                SELECT vs.id
                FROM video_segment vs
                WHERE vs.project_id = :project_id AND vs.tenant_id = :tenant_id
                  AND NOT EXISTS (
                    SELECT 1 FROM video_prompt vp
                    WHERE vp.video_segment_id = vs.id
                      AND vp.tenant_id = :tenant_id
                      AND vp.record_status = 'confirmed'
                  )
                ORDER BY vs.narrative_space_id, vs.ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    results: list[dict[str, Any]] = []
    for segment in segments:
        results.append(
            await generate_for_segment(
                session, tenant_id, segment["id"], commit=False
            )
        )
    await session.commit()
    return {
        "segments": results,
        "segment_count": len(results),
        "total": len(results),
    }


async def generate_for_space(
    session: AsyncSession,
    tenant_id: str,
    narrative_space_id: str,
    *,
    commit: bool = True,
) -> dict:
    """为一个叙事空间下的全部视频片段生成成片提示词。"""
    space = await _require_space(session, tenant_id, narrative_space_id)
    segments = (
        await video_segment_service.list_segments(
            session,
            tenant_id,
            space["project_id"],
            narrative_space_id=narrative_space_id,
        )
    )["items"]
    if not segments:
        raise ValidationAppError("该叙事空间尚未划分视频片段，请先划分片段")
    results: list[dict[str, Any]] = []
    for segment in segments:
        results.append(
            await generate_for_segment(
                session, tenant_id, segment["id"], commit=False
            )
        )
    if commit:
        await session.commit()
    return {
        "narrative_space_id": narrative_space_id,
        "segments": results,
        "total": len(results),
    }


async def generate_for_segment(
    session: AsyncSession,
    tenant_id: str,
    video_segment_id: str,
    *,
    commit: bool = True,
) -> dict:
    segment = await video_segment_service.require_segment(
        session, tenant_id, video_segment_id
    )
    narrative_space_id = segment["narrative_space_id"]
    space = await _require_space(session, tenant_id, narrative_space_id)
    project_id = segment["project_id"]
    await project_service.require_project(session, tenant_id, project_id)

    confirmed = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM video_prompt
                WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
                  AND record_status = 'confirmed'
                """
            ),
            {"seg_id": video_segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]
    if int(confirmed or 0) > 0:
        raise ValidationAppError(
            "该视频片段已有确认成片提示词，请先反悔后再重生成"
        )

    shot_ids = segment.get("shot_ids")
    if isinstance(shot_ids, str):
        shot_ids = json.loads(shot_ids)
    shot_ids = shot_ids or []
    space_shots = (
        await shot_service.list_shots(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
        )
    )["items"]
    shots = [s for s in space_shots if s["id"] in set(shot_ids)]
    if not shots:
        raise ValidationAppError("该视频片段未关联分镜，请先重新划分片段")

    used_char_ids: list[str] = []
    for s in shots:
        for cid in s.get("character_ids") or []:
            if cid and cid not in used_char_ids:
                used_char_ids.append(cid)
    pack = await consistency_context.assemble_pack(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
        character_ids=used_char_ids or None,
        include_craft=False,
    )
    style_bible = pack["style_bible"]

    await session.execute(
        text(
            """
            DELETE FROM video_prompt
            WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"seg_id": video_segment_id, "tenant_id": tenant_id},
    )

    craft = await knowledge_context.assemble_video_knowledge(tenant_id=tenant_id)
    system_prompt = llm.load_prompt("shot-planner/system.md")
    if craft:
        system_prompt = (
            system_prompt
            + "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n"
            + craft
        )
    system_prompt = (
        system_prompt + "\n\n" + pack["prompt_block"]
        + "\n\n只输出 JSON，不要 markdown 说明。"
    )

    template = llm.load_prompt("shot-planner/video-prompt.md")
    user_prompt = llm.render_prompt(
        template,
        style_bible=style_bible,
        narrative_space={
            "id": space["id"],
            "title": space.get("title") or "",
            "summary": space.get("summary") or "",
            "time_place": space.get("time_place") or "",
            "beat_type": space.get("beat_type") or "",
            "mood": space.get("mood") or "",
            "scene_space": pack.get("scene_space"),
        },
        video_segment={
            "id": segment["id"],
            "ordinal": int(segment["ordinal"]),
            "title": segment.get("title") or "",
            "summary": segment.get("summary") or "",
            "duration_sec": segment.get("duration_sec"),
            "source_text": (segment.get("source_text") or "")[:4000],
        },
        shots=shots,
        character_assets=pack["characters"],
        prop_assets=pack["props"],
        reference_images=pack.get("reference_images") or [],
    )
    parsed = await llm.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    prompt_text = (parsed.get("prompt_text") or "").strip()
    if not prompt_text:
        raise ValidationAppError("成片提示词结果为空")
    negative = (parsed.get("negative_prompt") or "").strip()
    duration = parsed.get("duration_sec")
    try:
        duration_sec = (
            float(duration) if duration is not None else segment.get("duration_sec")
        )
    except (TypeError, ValueError):
        duration_sec = segment.get("duration_sec")
    max_duration = video_segment_service.MAX_SEGMENT_DURATION_SEC
    if duration_sec is not None and duration_sec > max_duration:
        duration_sec = max_duration

    ref_ids = parsed.get("ref_image_ids") or parsed.get("reference_image_ids") or []
    if not isinstance(ref_ids, list):
        ref_ids = []

    version = (
        await session.execute(
            text(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM video_prompt
                WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
                """
            ),
            {"seg_id": video_segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["next_version"]

    prompt_id = new_id("svp")
    await session.execute(
        text(
            """
            INSERT INTO video_prompt
              (id, tenant_id, project_id, video_segment_id, narrative_space_id,
               prompt_text, negative_prompt, ref_image_ids, duration_sec, version,
               status, record_status)
            VALUES
              (:id, :tenant_id, :project_id, :video_segment_id, :narrative_space_id,
               :prompt_text, :negative_prompt, CAST(:ref_image_ids AS JSON),
               :duration_sec, :version, 'draft', 'ai')
            """
        ),
        {
            "id": prompt_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "video_segment_id": video_segment_id,
            "narrative_space_id": narrative_space_id,
            "prompt_text": prompt_text,
            "negative_prompt": negative,
            "ref_image_ids": json.dumps(ref_ids, ensure_ascii=False),
            "duration_sec": duration_sec,
            "version": int(version),
        },
    )
    if commit:
        await session.commit()
    row = (
        await session.execute(
            text("SELECT * FROM video_prompt WHERE id = :id"),
            {"id": prompt_id},
        )
    ).mappings().first()
    return {
        "video_segment_id": video_segment_id,
        "narrative_space_id": narrative_space_id,
        "item": _prompt_public(dict(row)),
        "total": 1,
    }


async def confirm_video_prompt(
    session: AsyncSession,
    tenant_id: str,
    prompt_id: str,
    *,
    created_by: str | None = None,
) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("video prompt not found")
    public = _prompt_public(dict(row))
    if (row.get("record_status") or "ai") != "confirmed":
        await revision_service.save_revision(
            session,
            tenant_id=tenant_id,
            project_id=row["project_id"],
            target_type="video_prompt",
            target_id=prompt_id,
            snapshot=public,
            change_reason="pin",
            created_by=created_by,
        )
    await session.execute(
        text(
            """
            UPDATE video_prompt
            SET record_status = 'confirmed', status = 'confirmed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": prompt_id, "tenant_id": tenant_id},
    )
    await session.commit()
    refreshed = (
        await session.execute(
            text(
                """
                SELECT * FROM video_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    return _prompt_public(dict(refreshed))
