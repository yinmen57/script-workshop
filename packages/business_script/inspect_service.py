"""只读巡检：给 tool-selector / 专业 Agent 提供决策所需的状态摘要。

不返回 source_text 等大字段；结果带 inspected_at，便于发现过期计划。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import (
    job_service,
    material_image_service,
    material_service,
    parse_service,
    project_service,
    shot_service,
    structure_service,
    video_prompt_service,
    video_segment_service,
)
from packages.domain.errors import ValidationAppError

SCOPES = frozenset(
    {"structure", "assets", "shots", "segments", "materials", "jobs", "progress"}
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _count_by_record(items: list[dict[str, Any]]) -> dict[str, int]:
    confirmed = sum(1 for i in items if (i.get("record_status") or "ai") == "confirmed")
    return {
        "total": len(items),
        "confirmed": confirmed,
        "ai": len(items) - confirmed,
    }


async def inspect(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    scope: str,
    narrative_space_id: str | None = None,
    video_segment_id: str | None = None,
    episode_id: str | None = None,
    job_status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """按 scope 返回项目状态摘要。"""
    if scope not in SCOPES:
        raise ValidationAppError(
            f"scope 必须是 {', '.join(sorted(SCOPES))} 之一",
            details={
                "code": "INSPECT_SCOPE_INVALID",
                "allowed": sorted(SCOPES),
            },
        )
    project = await project_service.require_project(session, tenant_id, project_id)
    limit = max(1, min(int(limit), 200))

    if scope == "structure":
        data = await _inspect_structure(
            session, tenant_id, project_id, episode_id=episode_id
        )
    elif scope == "assets":
        data = await _inspect_assets(session, tenant_id, project_id)
    elif scope == "shots":
        data = await _inspect_shots(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
            limit=limit,
        )
    elif scope == "segments":
        data = await _inspect_segments(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
            video_segment_id=video_segment_id,
            limit=limit,
        )
    elif scope == "materials":
        data = await _inspect_materials(session, tenant_id, project_id, limit=limit)
    elif scope == "jobs":
        data = await _inspect_jobs(
            session, tenant_id, project_id, status=job_status, limit=limit
        )
    else:
        data = await _inspect_progress(session, tenant_id, project_id)

    return {
        "scope": scope,
        "project_id": project_id,
        "project_name": project.get("name") or "",
        "has_style_bible": bool(project.get("style_bible")),
        "inspected_at": _now_iso(),
        **data,
    }


async def _inspect_structure(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    episode_id: str | None,
) -> dict[str, Any]:
    structure = await structure_service.list_structure(session, tenant_id, project_id)
    episodes_out: list[dict[str, Any]] = []
    for ep in structure.get("items") or []:
        if episode_id and ep["id"] != episode_id:
            continue
        spaces = []
        for ns in ep.get("narrative_spaces") or []:
            spaces.append(
                {
                    "id": ns["id"],
                    "ordinal": ns["ordinal"],
                    "title": ns.get("title") or "",
                    "time_place": ns.get("time_place") or "",
                    "beat_type": ns.get("beat_type") or "",
                    "mood": ns.get("mood") or "",
                    "segment_source": ns.get("segment_source") or "",
                    "status": ns.get("status"),
                    "record_status": ns.get("record_status"),
                    "estimated_duration_sec": ns.get("estimated_duration_sec"),
                }
            )
        episodes_out.append(
            {
                "id": ep["id"],
                "ordinal": ep["ordinal"],
                "title": ep.get("title") or "",
                "status": ep.get("status"),
                "record_status": ep.get("record_status"),
                "narrative_space_count": len(spaces),
                "narrative_spaces": spaces,
            }
        )
    space_total = sum(e["narrative_space_count"] for e in episodes_out)
    return {
        "episode_count": len(episodes_out),
        "narrative_space_count": space_total,
        "episodes": episodes_out,
        "summary": {
            "episodes": len(episodes_out),
            "narrative_spaces": space_total,
        },
    }


async def _inspect_assets(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict[str, Any]:
    assets = await parse_service.get_assets(session, tenant_id, project_id)
    characters = [
        {
            "id": c["id"],
            "name": c.get("name") or "",
            "character_key": c.get("character_key") or "",
            "status": c.get("status"),
            "record_status": c.get("record_status"),
        }
        for c in assets.get("characters") or []
    ]
    props = [
        {
            "id": p["id"],
            "prop_name": p.get("prop_name") or "",
            "prop_type": p.get("prop_type") or "",
            "scope": p.get("scope") or "",
            "owner_character_id": p.get("owner_character_id"),
            "owner_name": p.get("owner_name") or "",
            "status": p.get("status"),
            "record_status": p.get("record_status"),
        }
        for p in assets.get("props") or []
    ]
    scene_rows = (
        await session.execute(
            text(
                """
                SELECT id, name, canonical_key, record_status
                FROM scene_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY created_at ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    scenes = [
        {
            "id": r["id"],
            "name": r.get("name") or "",
            "canonical_key": r.get("canonical_key") or "",
            "record_status": r.get("record_status") or "ai",
        }
        for r in scene_rows
    ]
    return {
        "characters": characters,
        "props": props,
        "scene_spaces": scenes,
        "summary": {
            "characters": _count_by_record(characters),
            "props": _count_by_record(props),
            "scene_spaces": _count_by_record(scenes),
            "has_document": bool(assets.get("document")),
        },
    }


async def _inspect_shots(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None,
    limit: int,
) -> dict[str, Any]:
    bundle = await shot_service.list_shots(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )
    items = []
    for s in (bundle.get("items") or [])[:limit]:
        items.append(
            {
                "id": s["id"],
                "narrative_space_id": s["narrative_space_id"],
                "ordinal": s.get("ordinal"),
                "beat": (s.get("beat") or "")[:120],
                "duration_sec": s.get("duration_sec"),
                "status": s.get("status"),
                "record_status": s.get("record_status"),
                "character_count": len(s.get("character_ids") or []),
                "prop_count": len(s.get("prop_ids") or []),
            }
        )
    return {
        "items": items,
        "summary": _count_by_record(items),
        "narrative_space_id": narrative_space_id,
        "truncated": len(bundle.get("items") or []) > limit,
    }


async def _inspect_segments(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None,
    video_segment_id: str | None,
    limit: int,
) -> dict[str, Any]:
    if video_segment_id:
        seg = await video_segment_service.require_segment(
            session, tenant_id, video_segment_id
        )
        if seg["project_id"] != project_id:
            raise ValidationAppError(
                "视频片段不属于该项目",
                details={
                    "code": "SEGMENT_PROJECT_MISMATCH",
                    "target": {"type": "video_segment", "id": video_segment_id},
                },
            )
        public = video_segment_service._segment_public(seg)
        shot_ids = public.get("shot_ids") or []
        return {
            "items": [
                {
                    "id": public["id"],
                    "narrative_space_id": public["narrative_space_id"],
                    "ordinal": public["ordinal"],
                    "title": public.get("title") or "",
                    "summary": (public.get("summary") or "")[:200],
                    "shot_count": len(shot_ids),
                    "shot_ids": shot_ids,
                    "duration_sec": public.get("duration_sec"),
                    "status": public.get("status"),
                    "record_status": public.get("record_status"),
                }
            ],
            "summary": _count_by_record([public]),
            "narrative_space_id": public["narrative_space_id"],
            "video_segment_id": video_segment_id,
            "truncated": False,
        }

    bundle = await video_segment_service.list_segments(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )
    items = []
    for s in (bundle.get("items") or [])[:limit]:
        shot_ids = s.get("shot_ids") or []
        items.append(
            {
                "id": s["id"],
                "narrative_space_id": s["narrative_space_id"],
                "ordinal": s.get("ordinal"),
                "title": s.get("title") or "",
                "summary": (s.get("summary") or "")[:200],
                "shot_count": len(shot_ids),
                "shot_ids": shot_ids,
                "duration_sec": s.get("duration_sec"),
                "status": s.get("status"),
                "record_status": s.get("record_status"),
            }
        )
    return {
        "items": items,
        "summary": _count_by_record(items),
        "narrative_space_id": narrative_space_id,
        "truncated": len(bundle.get("items") or []) > limit,
    }


async def _inspect_materials(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    limit: int,
) -> dict[str, Any]:
    prompts = await material_service.list_material_prompts(
        session, tenant_id, project_id
    )
    prompt_items = []
    for p in (prompts.get("items") or [])[:limit]:
        prompt_items.append(
            {
                "id": p["id"],
                "target_type": p.get("target_type"),
                "target_id": p.get("target_id"),
                "version": p.get("version"),
                "status": p.get("status"),
                "record_status": p.get("record_status"),
                "has_prompt_text": bool((p.get("prompt_text") or "").strip()),
            }
        )
    images = await material_image_service.list_images(
        session, tenant_id, project_id
    )
    image_items = []
    for img in (images.get("items") or [])[:limit]:
        image_items.append(
            {
                "id": img["id"],
                "source_kind": img.get("source_kind"),
                "source_id": img.get("source_id"),
                "label": img.get("label") or "",
                "origin": img.get("origin") or "",
                "record_status": img.get("record_status") or "ai",
            }
        )
    video_prompts = await video_prompt_service.list_video_prompts(
        session, tenant_id, project_id
    )
    vp_items = []
    for vp in (video_prompts.get("items") or [])[:limit]:
        vp_items.append(
            {
                "id": vp["id"],
                "video_segment_id": vp.get("video_segment_id"),
                "narrative_space_id": vp.get("narrative_space_id"),
                "version": vp.get("version"),
                "duration_sec": vp.get("duration_sec"),
                "status": vp.get("status"),
                "record_status": vp.get("record_status"),
                "has_prompt_text": bool((vp.get("prompt_text") or "").strip()),
            }
        )
    return {
        "material_prompts": prompt_items,
        "material_images": image_items,
        "video_prompts": vp_items,
        "summary": {
            "material_prompts": _count_by_record(prompt_items),
            "material_images": {"total": len(image_items)},
            "video_prompts": _count_by_record(vp_items),
        },
    }


async def _inspect_jobs(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    status: str | None,
    limit: int,
) -> dict[str, Any]:
    bundle = await job_service.list_jobs(
        session, tenant_id, project_id, status=status, limit=limit
    )
    items = []
    for job in bundle.get("items") or []:
        items.append(job_service.job_recovery_view(job))
    active = [j for j in items if j.get("status") in job_service.ACTIVE_STATUSES]
    failed = [j for j in items if j.get("status") == "failed"]
    return {
        "items": items,
        "summary": {
            "total": len(items),
            "active": len(active),
            "failed": len(failed),
            "done": sum(1 for j in items if j.get("status") == "done"),
        },
    }


async def _inspect_progress(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict[str, Any]:
    """一页总览：链路各阶段是否就绪，供选择 Agent 快速决策。"""
    project = await project_service.require_project(session, tenant_id, project_id)
    doc = await project_service.latest_document(session, tenant_id, project_id)
    structure = await _inspect_structure(
        session, tenant_id, project_id, episode_id=None
    )
    assets = await _inspect_assets(session, tenant_id, project_id)
    shots = await _inspect_shots(
        session, tenant_id, project_id, narrative_space_id=None, limit=1
    )
    segments = await _inspect_segments(
        session,
        tenant_id,
        project_id,
        narrative_space_id=None,
        video_segment_id=None,
        limit=1,
    )
    materials = await _inspect_materials(session, tenant_id, project_id, limit=1)
    jobs = await job_service.list_jobs(
        session, tenant_id, project_id, status=None, limit=20
    )
    active_jobs = [
        job_service.job_recovery_view(j)
        for j in (jobs.get("items") or [])
        if j.get("status") in job_service.ACTIVE_STATUSES
    ]

    # 用计数 SQL 补全 shots/segments 总量（上面 limit=1 只为摘要）
    shot_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c,
                       SUM(CASE WHEN record_status = 'confirmed' THEN 1 ELSE 0 END) AS conf
                FROM shot_plan
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    seg_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c,
                       SUM(CASE WHEN record_status = 'confirmed' THEN 1 ELSE 0 END) AS conf
                FROM video_segment
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()

    stages = {
        "has_document": bool(doc),
        "has_style_bible": bool(project.get("style_bible")),
        "has_assets": (assets["summary"]["characters"]["total"] > 0),
        "has_structure": structure["episode_count"] > 0,
        "has_shots": int(shot_count["c"] or 0) > 0,
        "has_segments": int(seg_count["c"] or 0) > 0,
        "has_material_prompts": materials["summary"]["material_prompts"]["total"] > 0,
        "has_video_prompts": materials["summary"]["video_prompts"]["total"] > 0,
        "has_active_jobs": len(active_jobs) > 0,
    }
    next_hints: list[str] = []
    if not stages["has_document"]:
        next_hints.append("upload_script")
    elif not stages["has_style_bible"]:
        next_hints.append("parse-script")
    elif not stages["has_structure"]:
        next_hints.append("parse-structure")
    elif structure["narrative_space_count"] == 0:
        next_hints.append("segment-narrative")
    elif not stages["has_shots"]:
        next_hints.append("plan-shots")
    elif not stages["has_segments"]:
        next_hints.append("plan-video-segments")
    elif not stages["has_video_prompts"]:
        next_hints.append("generate-video-prompts")
    else:
        next_hints.append("render-video")

    return {
        "stages": stages,
        "counts": {
            "episodes": structure["episode_count"],
            "narrative_spaces": structure["narrative_space_count"],
            "characters": assets["summary"]["characters"],
            "props": assets["summary"]["props"],
            "shots": {
                "total": int(shot_count["c"] or 0),
                "confirmed": int(shot_count["conf"] or 0),
            },
            "segments": {
                "total": int(seg_count["c"] or 0),
                "confirmed": int(seg_count["conf"] or 0),
            },
            "material_prompts": materials["summary"]["material_prompts"],
            "video_prompts": materials["summary"]["video_prompts"],
        },
        "active_jobs": active_jobs,
        "suggested_next_tools": next_hints,
        # 保留少量明细供选择 Agent 定位
        "sample_shots_present": shots["summary"]["total"] > 0,
        "sample_segments_present": segments["summary"]["total"] > 0,
    }
