"""剧本物料业务接口：/api/v1/script-biz。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.adapters.sd_client import get_sd_client
from packages.business_script import (
    canvas_service,
    ingest,
    job_service,
    material_image_service,
    material_service,
    parse_service,
    project_service,
    render_service,
    revision_service,
    shot_service,
    structure_service,
    video_prompt_service,
    video_segment_service,
)
from packages.domain.permissions import APP_READ, APP_WRITE
from packages.governance.audit import write_audit

router = APIRouter(prefix="/script-biz", tags=["script-biz"])


async def _project_id_of_narrative_space(
    session: DbSession, tenant_id: str, space_id: str
) -> str:
    from sqlalchemy import text

    from packages.domain.errors import NotFoundError

    row = (
        await session.execute(
            text(
                """
                SELECT project_id FROM narrative_space
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("narrative space not found")
    return row["project_id"]


@router.post("/projects")
async def create_project(
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await project_service.create_project(session, auth.tenant_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.project.create",
        request_id=request_id,
        resource_type="script_project",
        resource_id=data["id"],
    )
    return data


@router.get("/projects")
async def list_projects(auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await project_service.list_projects(session, auth.tenant_id)


@router.get("/projects/{project_id}")
async def get_project(project_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await project_service.get_project(session, auth.tenant_id, project_id)


@router.post("/projects/{project_id}/scripts")
async def add_script(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await project_service.add_script(session, auth.tenant_id, project_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.script.create",
        request_id=request_id,
        resource_type="script_document",
        resource_id=data["id"],
        payload={"project_id": project_id, "version": data["version"]},
    )
    return data


@router.get("/projects/{project_id}/scripts")
async def list_scripts(project_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await project_service.list_documents(session, auth.tenant_id, project_id)


@router.post("/projects/{project_id}/scripts/upload")
async def upload_script(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
    file: UploadFile = File(...),
    title: str | None = Form(None),
) -> dict:
    """上传剧本文件：markitdown 转 Markdown 并落库。知识库索引见 knowledge/index。"""
    auth.require(APP_WRITE)
    data = await file.read()
    result = await ingest.upload_script_file(
        session,
        auth.tenant_id,
        project_id,
        filename=file.filename or "script.bin",
        data=data,
        content_type=file.content_type,
        title=title,
    )
    doc = result["document"]
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.script.upload",
        request_id=request_id,
        resource_type="script_document",
        resource_id=doc["id"],
        payload={
            "project_id": project_id,
            "source_filename": result.get("source_filename"),
        },
    )
    return result


@router.post("/projects/{project_id}/parse")
async def parse_project(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递解析作业，立即返回 job_id（由 Worker 执行）。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_PARSE,
        dedupe_key=f"parse:{project_id}",
        label="解析剧本",
        payload={
            "script_text": body.get("script_text") or body.get("raw_text"),
            "title": body.get("title"),
        },
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.project.parse",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id, "deduped": data.get("deduped")},
    )
    return data


@router.get("/projects/{project_id}/assets")
async def get_assets(project_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await parse_service.get_assets(session, auth.tenant_id, project_id)


@router.post("/projects/{project_id}/assets/confirm")
async def confirm_asset(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """确认人物或道具：record_status=confirmed，重解析不再覆盖。"""
    auth.require(APP_WRITE)
    data = await parse_service.confirm_asset(
        session,
        auth.tenant_id,
        project_id,
        target_type=body.get("target_type") or "",
        target_id=body.get("target_id") or "",
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.asset.confirm",
        request_id=request_id,
        resource_type=body.get("target_type") or "asset",
        resource_id=body.get("target_id"),
        payload={"project_id": project_id},
    )
    return data


@router.get("/projects/{project_id}/structure")
async def get_structure(project_id: str, auth: AuthDep, session: DbSession) -> dict:
    """目录树：集 → 叙事空间。"""
    auth.require(APP_READ)
    return await structure_service.list_structure(
        session, auth.tenant_id, project_id
    )


@router.post("/projects/{project_id}/structure/parse")
async def parse_structure(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """仅规则解析结构（不调 LLM）。默认使用最新剧本文档。"""
    auth.require(APP_WRITE)
    script_text = (body.get("script_text") or body.get("raw_text") or "").strip()
    if not script_text:
        doc = await project_service.latest_document(
            session, auth.tenant_id, project_id
        )
        if doc is None:
            from packages.domain.errors import ValidationAppError

            raise ValidationAppError("项目尚无剧本文档，请先上传或传入 script_text")
        script_text = doc["raw_text"]
    data = await structure_service.parse_and_sync_structure(
        session, auth.tenant_id, project_id, script_text
    )
    await session.commit()
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.structure.parse",
        request_id=request_id,
        resource_type="script_project",
        resource_id=project_id,
        payload=data.get("parsed"),
    )
    return data


@router.post("/projects/{project_id}/structure/segment")
async def segment_structure(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递语义切分作业：LLM 判定叙事空间边界，覆盖规则粗切结果。"""
    auth.require(APP_WRITE)
    script_text = (body.get("script_text") or body.get("raw_text") or "").strip()
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_SEGMENT,
        dedupe_key=f"narrative_segment:{project_id}",
        label="语义切分叙事空间",
        payload={"script_text": script_text} if script_text else {},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.structure.segment",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.post("/projects/{project_id}/knowledge/index")
async def index_project_knowledge(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递知识库索引作业：按叙事空间覆盖写入项目命名空间。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_INDEX_NARRATIVE,
        dedupe_key=f"index_narrative:{project_id}",
        label="索引叙事空间",
        payload={},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.knowledge.index",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.post("/narrative-spaces/{space_id}/confirm")
async def confirm_narrative_space(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await structure_service.confirm_narrative_space(
        session, auth.tenant_id, space_id, created_by=auth.actor
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.narrative_space.confirm",
        request_id=request_id,
        resource_type="narrative_space",
        resource_id=space_id,
    )
    return data


@router.get("/projects/{project_id}/shots")
async def list_shots(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    narrative_space_id: str | None = None,
) -> dict:
    """分镜列表；可按叙事空间过滤。"""
    auth.require(APP_READ)
    return await shot_service.list_shots(
        session,
        auth.tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )


@router.post("/projects/{project_id}/shots/plan")
async def plan_project_shots(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递批量分镜规划作业。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_PLAN_SHOTS,
        dedupe_key=f"plan_shots:{project_id}",
        label="批量规划分镜",
        payload={},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.shots.plan_project",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.post("/narrative-spaces/{space_id}/shots/plan")
async def plan_space_shots(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递单叙事空间分镜规划作业。"""
    auth.require(APP_WRITE)
    from sqlalchemy import text

    from packages.domain.errors import NotFoundError

    row = (
        await session.execute(
            text(
                """
                SELECT project_id FROM narrative_space
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": space_id, "tenant_id": auth.tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("narrative space not found")
    project_id = row["project_id"]
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_PLAN_SHOTS,
        dedupe_key=f"plan_shots:{space_id}",
        label="规划分镜",
        payload={"narrative_space_id": space_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.shots.plan_space",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"narrative_space_id": space_id},
    )
    return data


@router.post("/shots/{shot_id}/confirm")
async def confirm_shot(
    shot_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await shot_service.confirm_shot(
        session,
        auth.tenant_id,
        shot_id,
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.shot.confirm",
        request_id=request_id,
        resource_type="shot_plan",
        resource_id=shot_id,
    )
    return data


@router.patch("/narrative-spaces/{space_id}")
async def update_narrative_space(
    space_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """手工编辑叙事空间标题 / 时空 / 正文等。"""
    auth.require(APP_WRITE)
    data = await structure_service.update_narrative_space(
        session,
        auth.tenant_id,
        space_id,
        body,
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.narrative_space.update",
        request_id=request_id,
        resource_type="narrative_space",
        resource_id=space_id,
    )
    return data


@router.delete("/narrative-spaces/{space_id}")
async def delete_narrative_space(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """删除 ai 态叙事空间。"""
    auth.require(APP_WRITE)
    data = await structure_service.delete_narrative_space(
        session, auth.tenant_id, space_id
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.narrative_space.delete",
        request_id=request_id,
        resource_type="narrative_space",
        resource_id=space_id,
    )
    return data


@router.get("/projects/{project_id}/scene-spaces")
async def list_scene_spaces(
    project_id: str, auth: AuthDep, session: DbSession
) -> dict:
    """地点身份列表（跨集一致性锚点）。"""
    auth.require(APP_READ)
    return await structure_service.list_scene_spaces(
        session, auth.tenant_id, project_id
    )


@router.get("/projects/{project_id}/video-segments")
async def list_video_segments(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    narrative_space_id: str | None = None,
) -> dict:
    """视频片段列表；可按叙事空间过滤。"""
    auth.require(APP_READ)
    return await video_segment_service.list_segments(
        session,
        auth.tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )


@router.post("/projects/{project_id}/video-segments/plan")
async def plan_project_video_segments(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递批量视频片段划分作业。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_VIDEO_SEGMENTS,
        dedupe_key=f"video_segments:{project_id}",
        label="批量划分视频片段",
        payload={},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_segments.plan_project",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.post("/narrative-spaces/{space_id}/video-segments/plan")
async def plan_space_video_segments(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递单叙事空间视频片段划分作业。"""
    auth.require(APP_WRITE)
    project_id = await _project_id_of_narrative_space(session, auth.tenant_id, space_id)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_VIDEO_SEGMENTS,
        dedupe_key=f"video_segments:{space_id}",
        label="划分视频片段",
        payload={"narrative_space_id": space_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_segments.plan_space",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"narrative_space_id": space_id},
    )
    return data


@router.post("/video-segments/{segment_id}/confirm")
async def confirm_video_segment(
    segment_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await video_segment_service.confirm_segment(
        session, auth.tenant_id, segment_id, created_by=auth.actor
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_segment.confirm",
        request_id=request_id,
        resource_type="video_segment",
        resource_id=segment_id,
    )
    return data


@router.get("/projects/{project_id}/video-prompts")
async def list_video_prompts(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    narrative_space_id: str | None = None,
    video_segment_id: str | None = None,
) -> dict:
    auth.require(APP_READ)
    return await video_prompt_service.list_video_prompts(
        session,
        auth.tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
        video_segment_id=video_segment_id,
    )


@router.post("/projects/{project_id}/video-prompts/generate")
async def generate_project_video_prompts(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递批量成片提示词作业。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_VIDEO_PROMPTS,
        dedupe_key=f"video_prompts:{project_id}",
        label="批量生成成片提示词",
        payload={},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_prompts.generate_project",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.post("/narrative-spaces/{space_id}/video-prompts/generate")
async def generate_space_video_prompt(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递单叙事空间成片提示词作业（覆盖该空间全部视频片段）。"""
    auth.require(APP_WRITE)
    project_id = await _project_id_of_narrative_space(session, auth.tenant_id, space_id)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_VIDEO_PROMPTS,
        dedupe_key=f"video_prompts:{space_id}",
        label="生成叙事空间全部成片提示词",
        payload={"narrative_space_id": space_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_prompts.generate_space",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"narrative_space_id": space_id},
    )
    return data


@router.post("/video-segments/{segment_id}/video-prompts/generate")
async def generate_segment_video_prompt(
    segment_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递单视频片段成片提示词作业。"""
    auth.require(APP_WRITE)
    segment = await video_segment_service.require_segment(
        session, auth.tenant_id, segment_id
    )
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=segment["project_id"],
        kind=job_service.KIND_VIDEO_PROMPTS,
        dedupe_key=f"video_prompts:{segment_id}",
        label="生成成片提示词",
        payload={"video_segment_id": segment_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_prompts.generate_segment",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"video_segment_id": segment_id},
    )
    return data


@router.post("/video-prompts/{prompt_id}/confirm")
async def confirm_video_prompt(
    prompt_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await video_prompt_service.confirm_video_prompt(
        session,
        auth.tenant_id,
        prompt_id,
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video_prompt.confirm",
        request_id=request_id,
        resource_type="video_prompt",
        resource_id=prompt_id,
    )
    return data


@router.get("/projects/{project_id}/material-images")
async def list_material_images(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    source_kind: str | None = None,
    source_id: str | None = None,
) -> dict:
    auth.require(APP_READ)
    return await material_image_service.list_images(
        session,
        auth.tenant_id,
        project_id,
        source_kind=source_kind,
        source_id=source_id,
    )


@router.post("/projects/{project_id}/material-images")
async def register_material_image(
    project_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await material_image_service.register_image(
        session, auth.tenant_id, project_id, body
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_image.register",
        request_id=request_id,
        resource_type="material_image",
        resource_id=data.get("id"),
        payload={"project_id": project_id},
    )
    return data


@router.post("/projects/{project_id}/material-images/{image_id}/set-current")
async def set_current_material_image(
    project_id: str,
    image_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """把目录图设为 scene_space / costume_change 的当前指针。"""
    auth.require(APP_WRITE)
    data = await material_image_service.set_current(
        session,
        auth.tenant_id,
        project_id,
        image_id=image_id,
        source_kind=body.get("source_kind") or "",
        source_id=body.get("source_id") or "",
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_image.set_current",
        request_id=request_id,
        resource_type="material_image",
        resource_id=image_id,
        payload={
            "project_id": project_id,
            "source_kind": body.get("source_kind"),
            "source_id": body.get("source_id"),
        },
    )
    return data


@router.get("/revisions")
async def list_revisions(
    auth: AuthDep,
    session: DbSession,
    target_type: str,
    target_id: str,
) -> dict:
    auth.require(APP_READ)
    return await revision_service.list_revisions(
        session,
        tenant_id=auth.tenant_id,
        target_type=target_type,
        target_id=target_id,
    )


@router.post("/revisions/{revision_id}/revert")
async def revert_revision(
    revision_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """反悔：把历史快照写回主记录。"""
    auth.require(APP_WRITE)
    data = await revision_service.revert_to_revision(
        session,
        tenant_id=auth.tenant_id,
        revision_id=revision_id,
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.revision.revert",
        request_id=request_id,
        resource_type=data.get("target_type") or "record_revision",
        resource_id=data.get("target_id"),
        payload={"revision_id": revision_id},
    )
    return data


@router.post("/projects/{project_id}/material-prompts/generate")
async def generate_material_prompts(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递物料提示词生成作业。"""
    auth.require(APP_WRITE)
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=project_id,
        kind=job_service.KIND_MATERIAL,
        dedupe_key=f"material_prompts:{project_id}",
        label="生成物料提示词",
        payload={},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_prompts.generate",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"project_id": project_id},
    )
    return data


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await job_service.get_job(session, auth.tenant_id, job_id)


@router.get("/projects/{project_id}/jobs")
async def list_project_jobs(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    auth.require(APP_READ)
    return await job_service.list_jobs(
        session,
        auth.tenant_id,
        project_id,
        status=status,
        limit=limit,
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await job_service.request_cancel(session, auth.tenant_id, job_id)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.job.cancel",
        request_id=request_id,
        resource_type="job_run",
        resource_id=job_id,
    )
    return data


@router.get("/projects/{project_id}/material-prompts")
async def list_material_prompts(
    project_id: str, auth: AuthDep, session: DbSession
) -> dict:
    auth.require(APP_READ)
    return await material_service.list_material_prompts(
        session, auth.tenant_id, project_id
    )


@router.post("/projects/{project_id}/material-prompts/{prompt_id}/confirm")
async def confirm_material_prompt(
    project_id: str,
    prompt_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await material_service.confirm_material_prompt(
        session, auth.tenant_id, project_id, prompt_id
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_prompt.confirm",
        request_id=request_id,
        resource_type="material_prompt",
        resource_id=prompt_id,
        payload={"project_id": project_id},
    )
    return data


@router.get("/sd/balance")
async def sd_balance(auth: AuthDep) -> dict:
    """赏舞余额预检（连通性）。"""
    auth.require(APP_READ)
    client = get_sd_client()
    return await client.preflight()


@router.post("/material-prompts/{prompt_id}/render")
async def render_material_image(
    prompt_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递物料生图作业。"""
    auth.require(APP_WRITE)
    from sqlalchemy import text

    from packages.domain.errors import NotFoundError

    row = (
        await session.execute(
            text(
                """
                SELECT project_id FROM material_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": auth.tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("material prompt not found")
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=row["project_id"],
        kind=job_service.KIND_RENDER_IMAGE,
        dedupe_key=f"render_image:{prompt_id}",
        label="生成物料图",
        payload={"material_prompt_id": prompt_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_image.render",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"material_prompt_id": prompt_id},
    )
    return data


@router.post("/video-prompts/{prompt_id}/render")
async def render_video(
    prompt_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """投递成片视频生成作业。"""
    auth.require(APP_WRITE)
    from sqlalchemy import text

    from packages.domain.errors import NotFoundError

    row = (
        await session.execute(
            text(
                """
                SELECT project_id FROM video_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": auth.tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("video prompt not found")
    data = await job_service.submit_job(
        session,
        tenant_id=auth.tenant_id,
        project_id=row["project_id"],
        kind=job_service.KIND_RENDER_VIDEO,
        dedupe_key=f"render_video:{prompt_id}",
        label="生成成片视频",
        payload={"video_prompt_id": prompt_id},
        created_by=auth.actor,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.video.render",
        request_id=request_id,
        resource_type="job_run",
        resource_id=data["id"],
        payload={"video_prompt_id": prompt_id},
    )
    return data


@router.get("/projects/{project_id}/video-jobs")
async def list_video_jobs(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    narrative_space_id: str | None = None,
) -> dict:
    auth.require(APP_READ)
    return await render_service.list_video_jobs(
        session,
        auth.tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )


@router.get("/narrative-spaces/{space_id}/canvas")
async def get_canvas(space_id: str, auth: AuthDep, session: DbSession) -> dict:
    """读取叙事空间画布；无快照时按资产/分镜自动铺节点。"""
    auth.require(APP_READ)
    return await canvas_service.get_or_bootstrap(
        session, auth.tenant_id, space_id
    )


@router.put("/narrative-spaces/{space_id}/canvas")
async def put_canvas(
    space_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """保存画布布局（就地更新并递增 version）。"""
    auth.require(APP_WRITE)
    data = await canvas_service.save_snapshot(
        session,
        auth.tenant_id,
        space_id,
        nodes=body.get("nodes") or [],
        edges=body.get("edges") or [],
        viewport=body.get("viewport"),
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.canvas.save",
        request_id=request_id,
        resource_type="canvas_snapshot",
        resource_id=data.get("id"),
        payload={
            "narrative_space_id": space_id,
            "version": data.get("version"),
        },
    )
    return data
