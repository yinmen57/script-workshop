"""按 kind 执行剧本作业（Worker 与本地调试共用）。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import (
    job_service,
    material_service,
    narrative_segment_service,
    parse_service,
    project_service,
    render_service,
    script_index_service,
    shot_service,
    structure_service,
    video_prompt_service,
    video_segment_service,
)
from packages.domain.errors import ValidationAppError

logger = logging.getLogger(__name__)


async def execute_job(session: AsyncSession, job: dict[str, Any]) -> dict[str, Any]:
    """执行已 mark_running 的作业，返回 result 摘要。"""
    kind = job["kind"]
    tenant_id = job["tenant_id"]
    project_id = job["project_id"]
    payload = job.get("payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    if await job_service.is_cancel_requested(session, job["id"]):
        raise ValidationAppError("作业已取消")

    await job_service.mark_progress(session, job["id"], 20)

    if kind == job_service.KIND_PARSE:
        result = await parse_service.parse_project(
            session,
            tenant_id,
            project_id,
            script_text=payload.get("script_text") or payload.get("raw_text"),
            title=payload.get("title"),
        )
        return {
            "characters": len(result.get("characters") or []),
            "props": len(result.get("props") or []),
            "structure_episodes": (result.get("structure") or {}).get("total"),
        }

    if kind == job_service.KIND_STRUCTURE:
        script_text = await _resolve_script_text(
            session, tenant_id, project_id, payload
        )
        result = await structure_service.parse_and_sync_structure(
            session, tenant_id, project_id, script_text
        )
        await session.commit()
        return result.get("parsed") or {}

    if kind == job_service.KIND_SEGMENT:
        script_text = await _resolve_script_text(
            session, tenant_id, project_id, payload
        )
        result = await narrative_segment_service.segment_and_sync(
            session, tenant_id, project_id, script_text
        )
        return result.get("parsed") or {}

    if kind == job_service.KIND_INDEX_NARRATIVE:
        return await script_index_service.index_project_narrative(
            session, tenant_id, project_id
        )

    if kind == job_service.KIND_MATERIAL:
        result = await material_service.generate_material_prompts(
            session, tenant_id, project_id
        )
        return {
            "total": result.get("total"),
            "skipped_confirmed": result.get("skipped_confirmed"),
        }

    if kind == job_service.KIND_PLAN_SHOTS:
        space_id = payload.get("narrative_space_id")
        if space_id:
            result = await shot_service.plan_shots_for_space(
                session, tenant_id, space_id
            )
            return {
                "narrative_space_id": result.get("narrative_space_id"),
                "total": result.get("total"),
            }
        result = await shot_service.plan_shots_for_project(
            session, tenant_id, project_id
        )
        return {
            "space_count": result.get("space_count"),
            "total": result.get("total"),
        }

    if kind == job_service.KIND_VIDEO_SEGMENTS:
        space_id = payload.get("narrative_space_id")
        if space_id:
            result = await video_segment_service.plan_segments_for_space(
                session, tenant_id, space_id
            )
            return {
                "narrative_space_id": result.get("narrative_space_id"),
                "total": result.get("total"),
            }
        result = await video_segment_service.plan_segments_for_project(
            session, tenant_id, project_id
        )
        return {
            "space_count": result.get("space_count"),
            "total": result.get("total"),
        }

    if kind == job_service.KIND_VIDEO_PROMPTS:
        segment_id = payload.get("video_segment_id")
        if segment_id:
            result = await video_prompt_service.generate_for_segment(
                session, tenant_id, segment_id
            )
            return {
                "video_segment_id": result.get("video_segment_id"),
                "total": result.get("total"),
            }
        space_id = payload.get("narrative_space_id")
        if space_id:
            result = await video_prompt_service.generate_for_space(
                session, tenant_id, space_id
            )
            return {
                "narrative_space_id": result.get("narrative_space_id"),
                "total": result.get("total"),
            }
        result = await video_prompt_service.generate_for_project(
            session, tenant_id, project_id
        )
        return {
            "segment_count": result.get("segment_count"),
            "total": result.get("total"),
        }

    if kind == job_service.KIND_RENDER_IMAGE:
        prompt_id = payload.get("material_prompt_id") or ""
        if not prompt_id:
            raise ValidationAppError("缺少 material_prompt_id")
        result = await render_service.render_material_image(
            session, tenant_id, prompt_id
        )
        image = result.get("image") or {}
        return {
            "material_prompt_id": prompt_id,
            "image_id": image.get("id"),
            "url": image.get("url"),
            "provider_task_id": result.get("provider_task_id"),
        }

    if kind == job_service.KIND_RENDER_VIDEO:
        prompt_id = payload.get("video_prompt_id") or ""
        if not prompt_id:
            raise ValidationAppError("缺少 video_prompt_id")
        result = await render_service.render_video(session, tenant_id, prompt_id)
        vj = result.get("video_job") or {}
        return {
            "video_prompt_id": prompt_id,
            "video_job_id": vj.get("id"),
            "status": vj.get("status"),
            "oss_uri": vj.get("oss_uri"),
        }

    raise ValidationAppError(f"未知作业类型：{kind}")


async def _resolve_script_text(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    payload: dict[str, Any],
) -> str:
    script_text = (payload.get("script_text") or payload.get("raw_text") or "").strip()
    if script_text:
        return script_text
    doc = await project_service.latest_document(session, tenant_id, project_id)
    if doc is None:
        raise ValidationAppError("项目尚无剧本文档")
    return doc["raw_text"]


async def process_job_message(job_id: str) -> None:
    """Worker 入口：加载作业 → 执行 → 回写状态。"""
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        mapped = (
            await session.execute(
                text("SELECT * FROM job_run WHERE id = :id"),
                {"id": job_id},
            )
        ).mappings().first()
        if mapped is None:
            logger.warning("job %s not found, skip", job_id)
            return

    async with factory() as session:
        running = await job_service.mark_running(session, job_id)
        if running is None:
            return
        if running["status"] in job_service.TERMINAL_STATUSES:
            return
        try:
            result = await execute_job(session, running)
            await job_service.mark_done(session, job_id, result)
            logger.info("job %s done kind=%s", job_id, running["kind"])
        except Exception as exc:  # noqa: BLE001 — Worker 边界，必须落 failed
            logger.exception("job %s failed", job_id)
            msg = getattr(exc, "message", None) or str(exc)
            await job_service.mark_failed(session, job_id, msg)
