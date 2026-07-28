"""剧本物料业务接口：/api/v1/script-biz。"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.business_script import (
    ingest,
    material_service,
    parse_service,
    project_service,
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
        payload={"total": data.get("total")},
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
