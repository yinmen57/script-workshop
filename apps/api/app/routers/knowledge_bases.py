"""知识库与文档接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.domain.permissions import KB_READ, KB_WRITE
from packages.governance import kb_service
from packages.governance.audit import write_audit

router = APIRouter(tags=["knowledge-bases"])


@router.post("/knowledge-bases")
async def create_kb(
    body: dict, auth: AuthDep, session: DbSession, request_id: RequestIdDep
) -> dict:
    auth.require(KB_WRITE)
    data = await kb_service.create_kb(session, auth.tenant_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="kb.create",
        request_id=request_id,
        resource_type="knowledge_base",
        resource_id=data["id"],
    )
    return data


@router.get("/knowledge-bases")
async def list_kbs(
    auth: AuthDep,
    session: DbSession,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    auth.require(KB_READ)
    return await kb_service.list_kbs(
        session, auth.tenant_id, keyword=keyword, page=page, page_size=page_size
    )


@router.get("/knowledge-bases/{kb_id}")
async def get_kb(kb_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(KB_READ)
    return await kb_service.get_kb(session, auth.tenant_id, kb_id)


@router.patch("/knowledge-bases/{kb_id}")
async def update_kb(
    kb_id: str, body: dict, auth: AuthDep, session: DbSession, request_id: RequestIdDep
) -> dict:
    auth.require(KB_WRITE)
    data = await kb_service.update_kb(session, auth.tenant_id, kb_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="kb.update",
        request_id=request_id,
        resource_type="knowledge_base",
        resource_id=kb_id,
    )
    return data


@router.delete("/knowledge-bases/{kb_id}")
async def delete_kb(
    kb_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
    confirm: bool = False,
) -> dict:
    auth.require(KB_WRITE)
    await kb_service.delete_kb(session, auth.tenant_id, kb_id, confirm=confirm)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="kb.delete",
        request_id=request_id,
        resource_type="knowledge_base",
        resource_id=kb_id,
    )
    return {"ok": True}


@router.post("/knowledge-bases/{kb_id}/documents/text")
async def create_text_doc(
    kb_id: str, body: dict, auth: AuthDep, session: DbSession, request_id: RequestIdDep
) -> dict:
    auth.require(KB_WRITE)
    data = await kb_service.create_text_document(
        session,
        auth.tenant_id,
        kb_id,
        title=body.get("title") or "未命名文本",
        content=body.get("content") or "",
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="document.create_text",
        request_id=request_id,
        resource_type="document",
        resource_id=data["doc_id"],
    )
    return data


@router.get("/knowledge-bases/{kb_id}/documents")
async def list_docs(
    kb_id: str,
    auth: AuthDep,
    session: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    auth.require(KB_READ)
    return await kb_service.list_documents(
        session, auth.tenant_id, kb_id, page=page, page_size=page_size
    )


@router.post("/rag/search")
async def rag_search(body: dict, auth: AuthDep, session: DbSession) -> dict:
    auth.require(KB_READ)
    return await kb_service.rag_search(
        session,
        auth.tenant_id,
        kb_ids=body.get("knowledge_base_ids") or [],
        query=body.get("query") or "",
        top_k=int(body.get("top_k") or 5),
    )
