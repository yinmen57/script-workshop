"""写工具执行前的前置条件校验。

router / 专业 Agent 的结论只能视为建议；本模块在投递 job / 执行写操作前重新查库裁决。
失败时抛出带 code / next_action 的 ValidationAppError。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import job_service, project_service
from framework.domain.errors import ValidationAppError


def _fail(
    code: str,
    message: str,
    *,
    target: dict[str, Any] | None = None,
    next_action: str | None = None,
    retryable: bool = False,
) -> None:
    raise ValidationAppError(
        message,
        details={
            "code": code,
            "message": message,
            "target": target or {},
            "next_action": next_action,
            "retryable": retryable,
        },
    )


async def assert_project_ready(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict[str, Any]:
    return await project_service.require_project(session, tenant_id, project_id)


async def assert_no_active_job(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    dedupe_key: str,
) -> None:
    active = await job_service.find_active(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        dedupe_key=dedupe_key,
    )
    if active:
        _fail(
            "JOB_ALREADY_RUNNING",
            f"同类任务已在运行：{active.get('label') or active['id']}",
            target={"type": "job_run", "id": active["id"]},
            next_action="inspect",
            retryable=True,
        )


async def assert_can_plan_shots(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
) -> None:
    project = await assert_project_ready(session, tenant_id, project_id)
    if not project.get("style_bible"):
        _fail(
            "STYLE_BIBLE_REQUIRED",
            "项目尚未解析，缺少 style_bible",
            target={"type": "project", "id": project_id},
            next_action="parse-script",
        )
    if narrative_space_id:
        await _require_space(session, tenant_id, project_id, narrative_space_id)
    else:
        count = await _count(
            session,
            """
            SELECT COUNT(1) AS c FROM narrative_space
            WHERE project_id = :project_id AND tenant_id = :tenant_id
            """,
            {"project_id": project_id, "tenant_id": tenant_id},
        )
        if count == 0:
            _fail(
                "NARRATIVE_SPACE_REQUIRED",
                "项目尚无叙事空间，请先规则粗切或语义切分",
                target={"type": "project", "id": project_id},
                next_action="segment-narrative",
            )


async def assert_can_plan_segments(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
) -> None:
    await assert_project_ready(session, tenant_id, project_id)
    if narrative_space_id:
        await _require_space(session, tenant_id, project_id, narrative_space_id)
        shot_count = await _count(
            session,
            """
            SELECT COUNT(1) AS c FROM shot_plan
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
            """,
            {"ns_id": narrative_space_id, "tenant_id": tenant_id},
        )
        if shot_count == 0:
            _fail(
                "VIDEO_SEGMENT_SHOTS_REQUIRED",
                "该叙事空间尚无分镜，不能编组视频片段",
                target={"type": "narrative_space", "id": narrative_space_id},
                next_action="plan-shots",
            )
        confirmed = await _count(
            session,
            """
            SELECT COUNT(1) AS c FROM video_segment
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'confirmed'
            """,
            {"ns_id": narrative_space_id, "tenant_id": tenant_id},
        )
        if confirmed > 0:
            _fail(
                "VIDEO_SEGMENT_CONFIRMED",
                "该叙事空间已有确认视频片段，请先反悔后再重新划分",
                target={"type": "narrative_space", "id": narrative_space_id},
                next_action="revert",
            )
        return

    shot_count = await _count(
        session,
        """
        SELECT COUNT(1) AS c FROM shot_plan
        WHERE project_id = :project_id AND tenant_id = :tenant_id
        """,
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    if shot_count == 0:
        _fail(
            "VIDEO_SEGMENT_SHOTS_REQUIRED",
            "项目尚无分镜，不能编组视频片段",
            target={"type": "project", "id": project_id},
            next_action="plan-shots",
        )


async def assert_can_generate_video_prompts(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    video_segment_id: str | None = None,
    narrative_space_id: str | None = None,
) -> None:
    project = await assert_project_ready(session, tenant_id, project_id)
    if not project.get("style_bible"):
        _fail(
            "STYLE_BIBLE_REQUIRED",
            "项目尚未解析，缺少 style_bible",
            target={"type": "project", "id": project_id},
            next_action="parse-script",
        )
    if video_segment_id:
        seg = await _require_segment(session, tenant_id, project_id, video_segment_id)
        confirmed = await _count(
            session,
            """
            SELECT COUNT(1) AS c FROM video_prompt
            WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
              AND record_status = 'confirmed'
            """,
            {"seg_id": video_segment_id, "tenant_id": tenant_id},
        )
        if confirmed > 0:
            _fail(
                "VIDEO_PROMPT_CONFIRMED",
                "该视频片段已有确认成片提示词，请先反悔后再重生成",
                target={"type": "video_segment", "id": video_segment_id},
                next_action="revert",
            )
        shot_ids = seg.get("shot_ids")
        if isinstance(shot_ids, str):
            import json

            shot_ids = json.loads(shot_ids)
        if not shot_ids:
            _fail(
                "VIDEO_PROMPT_SHOTS_REQUIRED",
                "该视频片段未关联分镜，请先重新划分片段",
                target={"type": "video_segment", "id": video_segment_id},
                next_action="plan-video-segments",
            )
        return

    if narrative_space_id:
        await _require_space(session, tenant_id, project_id, narrative_space_id)
        seg_count = await _count(
            session,
            """
            SELECT COUNT(1) AS c FROM video_segment
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
            """,
            {"ns_id": narrative_space_id, "tenant_id": tenant_id},
        )
        if seg_count == 0:
            _fail(
                "VIDEO_SEGMENT_REQUIRED",
                "该叙事空间尚无视频片段，请先编组片段",
                target={"type": "narrative_space", "id": narrative_space_id},
                next_action="plan-video-segments",
            )
        return

    seg_count = await _count(
        session,
        """
        SELECT COUNT(1) AS c FROM video_segment
        WHERE project_id = :project_id AND tenant_id = :tenant_id
        """,
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    if seg_count == 0:
        _fail(
            "VIDEO_SEGMENT_REQUIRED",
            "项目尚无视频片段，请先编组片段",
            target={"type": "project", "id": project_id},
            next_action="plan-video-segments",
        )


async def assert_can_render_video(
    session: AsyncSession, tenant_id: str, video_prompt_id: str
) -> str:
    """返回 project_id。"""
    row = (
        await session.execute(
            text(
                """
                SELECT id, project_id, record_status
                FROM video_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": video_prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        _fail(
            "VIDEO_PROMPT_NOT_FOUND",
            "成片提示词不存在",
            target={"type": "video_prompt", "id": video_prompt_id},
            next_action="generate-video-prompts",
        )
    if (row["record_status"] or "ai") != "confirmed":
        _fail(
            "VIDEO_PROMPT_NOT_CONFIRMED",
            "成片提示词尚未确认，不能生成视频",
            target={"type": "video_prompt", "id": video_prompt_id},
            next_action="confirm",
        )
    return row["project_id"]


async def assert_can_render_material_image(
    session: AsyncSession, tenant_id: str, material_prompt_id: str
) -> str:
    row = (
        await session.execute(
            text(
                """
                SELECT id, project_id, record_status
                FROM material_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": material_prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        _fail(
            "MATERIAL_PROMPT_NOT_FOUND",
            "物料提示词不存在",
            target={"type": "material_prompt", "id": material_prompt_id},
            next_action="generate-material-prompts",
        )
    if (row["record_status"] or "ai") != "confirmed":
        _fail(
            "MATERIAL_PROMPT_NOT_CONFIRMED",
            "物料提示词尚未确认，不能生图",
            target={"type": "material_prompt", "id": material_prompt_id},
            next_action="confirm",
        )
    return row["project_id"]


async def assert_can_parse(
    session: AsyncSession, tenant_id: str, project_id: str
) -> None:
    await assert_project_ready(session, tenant_id, project_id)
    doc = await project_service.latest_document(session, tenant_id, project_id)
    if doc is None:
        _fail(
            "SCRIPT_DOCUMENT_REQUIRED",
            "项目尚无剧本文档，请先上传剧本",
            target={"type": "project", "id": project_id},
            next_action="ask",
        )


async def assert_can_index_narrative(
    session: AsyncSession, tenant_id: str, project_id: str
) -> None:
    """项目知识库索引前置：叙事空间 / 人物 / 场景至少一类。"""
    await assert_project_ready(session, tenant_id, project_id)
    space_count = await _count(
        session,
        """
        SELECT COUNT(1) AS c FROM narrative_space
        WHERE project_id = :project_id AND tenant_id = :tenant_id
        """,
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    char_count = await _count(
        session,
        """
        SELECT COUNT(1) AS c FROM character_asset
        WHERE project_id = :project_id AND tenant_id = :tenant_id
        """,
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    scene_count = await _count(
        session,
        """
        SELECT COUNT(1) AS c FROM scene_space
        WHERE project_id = :project_id AND tenant_id = :tenant_id
        """,
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    if space_count + char_count + scene_count == 0:
        _fail(
            "INDEXABLE_CONTENT_REQUIRED",
            "项目无可索引内容（需叙事空间、人物或场景）",
            target={"type": "project", "id": project_id},
            next_action="parse-structure",
        )


async def _require_space(
    session: AsyncSession, tenant_id: str, project_id: str, space_id: str
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
        _fail(
            "NARRATIVE_SPACE_NOT_FOUND",
            "叙事空间不存在",
            target={"type": "narrative_space", "id": space_id},
            next_action="inspect",
        )
    if row["project_id"] != project_id:
        _fail(
            "NARRATIVE_SPACE_PROJECT_MISMATCH",
            "叙事空间不属于该项目",
            target={"type": "narrative_space", "id": space_id},
            next_action="inspect",
        )
    return dict(row)


async def _require_segment(
    session: AsyncSession, tenant_id: str, project_id: str, segment_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_segment
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        _fail(
            "VIDEO_SEGMENT_NOT_FOUND",
            "视频片段不存在",
            target={"type": "video_segment", "id": segment_id},
            next_action="plan-video-segments",
        )
    if row["project_id"] != project_id:
        _fail(
            "VIDEO_SEGMENT_PROJECT_MISMATCH",
            "视频片段不属于该项目",
            target={"type": "video_segment", "id": segment_id},
            next_action="inspect",
        )
    return dict(row)


async def _count(
    session: AsyncSession, sql: str, params: dict[str, Any]
) -> int:
    row = (await session.execute(text(sql), params)).mappings().first()
    return int((row or {}).get("c") or 0)
