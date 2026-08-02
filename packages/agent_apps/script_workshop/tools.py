"""剧本工坊工具入口：投递作业并由 Worker 执行（与 /script-biz 共用）。

同进程内不走 HTTP 自调用；租户由 LangGraph 运行时注入 tool_context。
写工具提交前走 precondition_service 重新校验；读工具直接查库同步返回。
本文件位于 packages.agent_apps.script_workshop.tools。
"""

from __future__ import annotations

from typing import Any

from packages.business_script import (
    inspect_service,
    job_service,
    material_service,
    parse_service,
    precondition_service,
    revision_service,
    shot_service,
    structure_service,
    video_prompt_service,
    video_segment_service,
)
from packages.core.tool_context import require_tenant_id
from packages.domain.errors import ValidationAppError
from packages.infra.db import get_session_factory

_CONFIRM_TYPES = frozenset(
    {
        "character",
        "prop",
        "shot",
        "segment",
        "video_prompt",
        "material_prompt",
        "narrative_space",
    }
)


async def _submit_and_wait(
    *,
    project_id: str,
    kind: str,
    dedupe_key: str,
    label: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id = require_tenant_id()
    # 同 dedupe_key 活动任务由 submit_job 去重并返回，此处直接等待终态
    async with get_session_factory()() as session:
        job = await job_service.submit_job(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            kind=kind,
            dedupe_key=dedupe_key,
            label=label,
            payload=payload or {},
        )
    if job.get("deduped"):
        finished = await job_service.wait_until_terminal(
            tenant_id=tenant_id,
            job_id=job["id"],
        )
        return {
            "job_id": finished["id"],
            "status": finished["status"],
            "result": finished.get("result") or {},
            "deduped": True,
            "recovery": job_service.job_recovery_view(finished),
        }
    finished = await job_service.wait_until_terminal(
        tenant_id=tenant_id,
        job_id=job["id"],
    )
    return {
        "job_id": finished["id"],
        "status": finished["status"],
        "result": finished.get("result") or {},
        "deduped": False,
        "recovery": job_service.job_recovery_view(finished),
    }


async def inspect(
    project_id: str,
    scope: str,
    narrative_space_id: str | None = None,
    video_segment_id: str | None = None,
    episode_id: str | None = None,
    job_status: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """只读巡检项目状态；同步返回，不走 job 队列。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        return await inspect_service.inspect(
            session,
            tenant_id,
            project_id,
            scope=scope,
            narrative_space_id=narrative_space_id,
            video_segment_id=video_segment_id,
            episode_id=episode_id,
            job_status=job_status,
            limit=limit,
        )


async def parse_script(project_id: str, script_text: str | None = None) -> dict[str, Any]:
    """解析剧本并创建人物、归属道具；结构由规则切分。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        if not script_text:
            await precondition_service.assert_can_parse(
                session, tenant_id, project_id
            )
        else:
            await precondition_service.assert_project_ready(
                session, tenant_id, project_id
            )
    payload: dict[str, Any] = {}
    if script_text:
        payload["script_text"] = script_text
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_PARSE,
        dedupe_key=f"parse:{project_id}",
        label="解析剧本",
        payload=payload,
    )


async def parse_structure(
    project_id: str, script_text: str | None = None
) -> dict[str, Any]:
    """规则粗切集与叙事空间（不调 LLM）。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        if not script_text:
            await precondition_service.assert_can_parse(
                session, tenant_id, project_id
            )
        else:
            await precondition_service.assert_project_ready(
                session, tenant_id, project_id
            )
    payload: dict[str, Any] = {}
    if script_text:
        payload["script_text"] = script_text
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_STRUCTURE,
        dedupe_key=f"structure:{project_id}",
        label="规则粗切结构",
        payload=payload,
    )


async def segment_narrative(
    project_id: str, script_text: str | None = None
) -> dict[str, Any]:
    """按语义判定集内叙事空间边界并落库；缺省 script_text 时取项目最新剧本。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        if not script_text:
            await precondition_service.assert_can_parse(
                session, tenant_id, project_id
            )
        else:
            await precondition_service.assert_project_ready(
                session, tenant_id, project_id
            )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_SEGMENT,
        dedupe_key=f"narrative_segment:{project_id}",
        label="语义切分叙事空间",
        payload={"script_text": script_text} if script_text else {},
    )


async def index_narrative_knowledge(project_id: str) -> dict[str, Any]:
    """从工作台事实重建项目知识库检索副本（叙事空间 + 人物 + 场景）。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        await precondition_service.assert_can_index_narrative(
            session, tenant_id, project_id
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_INDEX_NARRATIVE,
        dedupe_key=f"index_narrative:{project_id}",
        label="索引项目知识库",
    )


async def generate_material_prompts(project_id: str) -> dict[str, Any]:
    """为人物和归属道具生成可编辑的物料提示词。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        project = await precondition_service.assert_project_ready(
            session, tenant_id, project_id
        )
        if not project.get("style_bible"):
            raise ValidationAppError(
                "项目尚未解析，缺少 style_bible",
                details={
                    "code": "STYLE_BIBLE_REQUIRED",
                    "next_action": "parse-script",
                    "retryable": False,
                },
            )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_MATERIAL,
        dedupe_key=f"material_prompts:{project_id}",
        label="生成物料提示词",
    )


async def plan_shots(
    project_id: str, narrative_space_id: str | None = None
) -> dict[str, Any]:
    """按叙事空间规划分镜；缺省 narrative_space_id 时规划项目下全部待规划空间。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        await precondition_service.assert_can_plan_shots(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
        )
    if narrative_space_id:
        return await _submit_and_wait(
            project_id=project_id,
            kind=job_service.KIND_PLAN_SHOTS,
            dedupe_key=f"plan_shots:{narrative_space_id}",
            label="规划分镜",
            payload={"narrative_space_id": narrative_space_id},
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_PLAN_SHOTS,
        dedupe_key=f"plan_shots:{project_id}",
        label="批量规划分镜",
    )


async def plan_video_segments(
    project_id: str, narrative_space_id: str | None = None
) -> dict[str, Any]:
    """把叙事空间的分镜按内容编成视频片段；缺省则处理项目下全部空间。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        await precondition_service.assert_can_plan_segments(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
        )
    if narrative_space_id:
        return await _submit_and_wait(
            project_id=project_id,
            kind=job_service.KIND_VIDEO_SEGMENTS,
            dedupe_key=f"video_segments:{narrative_space_id}",
            label="划分视频片段",
            payload={"narrative_space_id": narrative_space_id},
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_VIDEO_SEGMENTS,
        dedupe_key=f"video_segments:{project_id}",
        label="批量划分视频片段",
    )


async def generate_video_prompts(
    project_id: str,
    video_segment_id: str | None = None,
    narrative_space_id: str | None = None,
) -> dict[str, Any]:
    """按视频片段生成成片提示词；可指定片段或整个叙事空间，缺省则批量处理。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        await precondition_service.assert_can_generate_video_prompts(
            session,
            tenant_id,
            project_id,
            video_segment_id=video_segment_id,
            narrative_space_id=narrative_space_id,
        )
    if video_segment_id:
        return await _submit_and_wait(
            project_id=project_id,
            kind=job_service.KIND_VIDEO_PROMPTS,
            dedupe_key=f"video_prompts:{video_segment_id}",
            label="生成成片提示词",
            payload={"video_segment_id": video_segment_id},
        )
    if narrative_space_id:
        return await _submit_and_wait(
            project_id=project_id,
            kind=job_service.KIND_VIDEO_PROMPTS,
            dedupe_key=f"video_prompts:{narrative_space_id}",
            label="生成叙事空间全部成片提示词",
            payload={"narrative_space_id": narrative_space_id},
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_VIDEO_PROMPTS,
        dedupe_key=f"video_prompts:{project_id}",
        label="批量生成成片提示词",
    )


async def render_material_image(material_prompt_id: str) -> dict[str, Any]:
    """通过赏舞为已确认物料提示词生图。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        project_id = await precondition_service.assert_can_render_material_image(
            session, tenant_id, material_prompt_id
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_RENDER_IMAGE,
        dedupe_key=f"render_image:{material_prompt_id}",
        label="生成物料图",
        payload={"material_prompt_id": material_prompt_id},
    )


async def render_video(video_prompt_id: str) -> dict[str, Any]:
    """通过赏舞为已确认成片提示词生成视频。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        project_id = await precondition_service.assert_can_render_video(
            session, tenant_id, video_prompt_id
        )
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_RENDER_VIDEO,
        dedupe_key=f"render_video:{video_prompt_id}",
        label="生成成片视频",
        payload={"video_prompt_id": video_prompt_id},
    )


async def confirm(
    project_id: str,
    target_type: str,
    target_id: str,
) -> dict[str, Any]:
    """定版：将目标产物标记为 confirmed。"""
    if target_type not in _CONFIRM_TYPES:
        raise ValidationAppError(
            f"target_type 必须是 {', '.join(sorted(_CONFIRM_TYPES))} 之一",
            details={
                "code": "CONFIRM_TYPE_INVALID",
                "allowed": sorted(_CONFIRM_TYPES),
            },
        )
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        await precondition_service.assert_project_ready(
            session, tenant_id, project_id
        )
        if target_type in {"character", "prop"}:
            result = await parse_service.confirm_asset(
                session,
                tenant_id,
                project_id,
                target_type=target_type,
                target_id=target_id,
            )
        elif target_type == "shot":
            result = await shot_service.confirm_shot(
                session, tenant_id, target_id
            )
        elif target_type == "segment":
            result = await video_segment_service.confirm_segment(
                session, tenant_id, target_id
            )
        elif target_type == "video_prompt":
            result = await video_prompt_service.confirm_video_prompt(
                session, tenant_id, target_id
            )
        elif target_type == "material_prompt":
            result = await material_service.confirm_material_prompt(
                session, tenant_id, project_id, target_id
            )
        else:
            result = await structure_service.confirm_narrative_space(
                session, tenant_id, target_id
            )
    return {
        "target_type": target_type,
        "target_id": target_id,
        "record_status": "confirmed",
        "result": result,
    }


async def revert(revision_id: str) -> dict[str, Any]:
    """按废稿历史 revision_id 反悔写回。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        result = await revision_service.revert_to_revision(
            session,
            tenant_id=tenant_id,
            revision_id=revision_id,
        )
    return {"revision_id": revision_id, "result": result}
