"""向量命名空间索引与检索接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import AuthDep, DbSession, RequestIdDep
from framework.domain.permissions import KB_READ, KB_WRITE
from framework.governance import vector_namespace_service
from framework.governance.audit import write_audit

router = APIRouter(tags=["index"])


@router.post("/index")
async def index_texts(
    body: dict, auth: AuthDep, session: DbSession, request_id: RequestIdDep
) -> dict:
    """业务层索引入口：namespace + texts。"""
    auth.require(KB_WRITE)
    data = await vector_namespace_service.index_texts(
        session,
        auth.tenant_id,
        namespace=body.get("namespace") or "",
        texts=body.get("texts") or [],
        chunk_size=int(body.get("chunk_size") or 800),
        chunk_overlap=int(body.get("chunk_overlap") or 100),
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="vector.index",
        request_id=request_id,
        resource_type="vector_namespace",
        resource_id=data["namespace"],
        payload={"indexed": data["indexed"]},
    )
    return data


@router.post("/index/search")
async def search_index(body: dict, auth: AuthDep) -> dict:
    auth.require(KB_READ)
    namespaces = body.get("namespaces") or []
    if isinstance(namespaces, str):
        namespaces = [namespaces]
    return await vector_namespace_service.search(
        tenant_id=auth.tenant_id,
        namespaces=list(namespaces),
        query=body.get("query") or "",
        top_k=int(body.get("top_k") or 5),
        recall_n=int(body.get("recall_n") or 30),
        rerank=bool(body.get("rerank", True)),
    )


@router.get("/index/namespaces")
async def list_namespaces(auth: AuthDep, session: DbSession) -> dict:
    auth.require(KB_READ)
    return await vector_namespace_service.list_namespaces(session, auth.tenant_id)
