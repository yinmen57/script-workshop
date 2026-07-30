"""剧本工坊工具入口：投递作业并由 Worker 执行（与 /script-biz 共用）。

同进程内不走 HTTP 自调用；租户由 agent_runtime 注入 tool_context。
工具侧提交后轮询至终态，以便 Agent 拿到结果。
"""

from __future__ import annotations

from typing import Any

from packages.business_script import job_service
from packages.core.tool_context import require_tenant_id
from packages.infra.db import get_session_factory


async def _submit_and_wait(
    *,
    project_id: str,
    kind: str,
    dedupe_key: str,
    label: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    tenant_id = require_tenant_id()
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
    finished = await job_service.wait_until_terminal(
        tenant_id=tenant_id,
        job_id=job["id"],
    )
    return {
        "job_id": finished["id"],
        "status": finished["status"],
        "result": finished.get("result") or {},
    }


async def _project_id_of_material_prompt(material_prompt_id: str) -> str:
    from sqlalchemy import text

    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT project_id FROM material_prompt
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": material_prompt_id, "tenant_id": tenant_id},
            )
        ).mappings().first()
    if row is None:
        from packages.domain.errors import NotFoundError

        raise NotFoundError("material prompt not found")
    return row["project_id"]


async def _project_id_of_video_prompt(video_prompt_id: str) -> str:
    from sqlalchemy import text

    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        row = (
            await session.execute(
                text(
                    """
                    SELECT project_id FROM video_prompt
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": video_prompt_id, "tenant_id": tenant_id},
            )
        ).mappings().first()
    if row is None:
        from packages.domain.errors import NotFoundError

        raise NotFoundError("video prompt not found")
    return row["project_id"]


async def parse_script(project_id: str, script_text: str) -> dict[str, Any]:
    """解析剧本并创建人物、归属道具；结构由规则切分。"""
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_PARSE,
        dedupe_key=f"parse:{project_id}",
        label="解析剧本",
        payload={"script_text": script_text},
    )


async def segment_narrative(
    project_id: str, script_text: str | None = None
) -> dict[str, Any]:
    """按语义判定集内叙事空间边界并落库；缺省 script_text 时取项目最新剧本。"""
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_SEGMENT,
        dedupe_key=f"narrative_segment:{project_id}",
        label="语义切分叙事空间",
        payload={"script_text": script_text} if script_text else {},
    )


async def index_narrative_knowledge(project_id: str) -> dict[str, Any]:
    """把项目叙事空间按场次写入知识库，供后续检索定位到具体空间。"""
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_INDEX_NARRATIVE,
        dedupe_key=f"index_narrative:{project_id}",
        label="索引叙事空间",
    )


async def generate_material_prompts(project_id: str) -> dict[str, Any]:
    """为人物和归属道具生成可编辑的物料提示词。"""
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
    """把叙事空间的分镜按模型时长上限分成视频片段；缺省则处理项目下全部空间。"""
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
    project_id = await _project_id_of_material_prompt(material_prompt_id)
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_RENDER_IMAGE,
        dedupe_key=f"render_image:{material_prompt_id}",
        label="生成物料图",
        payload={"material_prompt_id": material_prompt_id},
    )


async def render_video(video_prompt_id: str) -> dict[str, Any]:
    """通过赏舞为已确认成片提示词生成叙事空间视频。"""
    project_id = await _project_id_of_video_prompt(video_prompt_id)
    return await _submit_and_wait(
        project_id=project_id,
        kind=job_service.KIND_RENDER_VIDEO,
        dedupe_key=f"render_video:{video_prompt_id}",
        label="生成成片视频",
        payload={"video_prompt_id": video_prompt_id},
    )
