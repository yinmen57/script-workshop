"""剧本物料业务接口：/api/v1/script-biz。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.business_script import (
    ingest,
    material_service,
    parse_service,
    project_service,
    shot_service,
    structure_service,
)
from packages.domain.permissions import APP_READ, APP_WRITE
from packages.governance.audit import write_audit

router = APIRouter(prefix="/script-biz", tags=["script-biz"])


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
    index_knowledge: bool = Form(True),
) -> dict:
    """上传剧本文件：markitdown 转 Markdown，落库并写入项目知识库命名空间。"""
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
        index_knowledge=index_knowledge,
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
            "indexed": (result.get("knowledge") or {}).get("indexed"),
            "namespace": (result.get("knowledge") or {}).get("namespace"),
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
    auth.require(APP_WRITE)
    data = await parse_service.parse_project(
        session,
        auth.tenant_id,
        project_id,
        script_text=body.get("script_text") or body.get("raw_text"),
        title=body.get("title"),
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.project.parse",
        request_id=request_id,
        resource_type="script_project",
        resource_id=project_id,
        payload={
            "characters": len(data.get("characters") or []),
            "props": len(data.get("props") or []),
        },
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
    """为项目下尚未有确认分镜的叙事空间规划分镜。"""
    auth.require(APP_WRITE)
    data = await shot_service.plan_shots_for_project(
        session, auth.tenant_id, project_id
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.shots.plan_project",
        request_id=request_id,
        resource_type="script_project",
        resource_id=project_id,
        payload={
            "space_count": data.get("space_count"),
            "total": data.get("total"),
        },
    )
    return data


@router.post("/narrative-spaces/{space_id}/shots/plan")
async def plan_space_shots(
    space_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    """为单个叙事空间规划分镜。"""
    auth.require(APP_WRITE)
    data = await shot_service.plan_shots_for_space(
        session, auth.tenant_id, space_id
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.shots.plan_space",
        request_id=request_id,
        resource_type="narrative_space",
        resource_id=space_id,
        payload={"total": data.get("total")},
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


@router.post("/projects/{project_id}/material-prompts/generate")
async def generate_material_prompts(
    project_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(APP_WRITE)
    data = await material_service.generate_material_prompts(
        session, auth.tenant_id, project_id
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="script_biz.material_prompts.generate",
        request_id=request_id,
        resource_type="script_project",
        resource_id=project_id,
        payload={
            "total": data.get("total"),
            "skipped_confirmed": data.get("skipped_confirmed"),
        },
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
