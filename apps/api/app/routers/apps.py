"""应用空间接口：列表与详情均来自内存注册表。"""

from __future__ import annotations

from fastapi import APIRouter

from app.deps import AuthDep, DbSession
from packages.domain.permissions import APP_READ
from packages.agent_apps import registry
from packages.governance import vector_namespace_service

router = APIRouter(prefix="/apps", tags=["apps"])


@router.get("")
async def list_apps(auth: AuthDep) -> dict:
    auth.require(APP_READ)
    return registry.list_workspaces(auth.tenant_id)


@router.get("/{slug}")
async def get_workspace(slug: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    data = registry.get_workspace(auth.tenant_id, slug)
    indexed = await vector_namespace_service.list_namespaces(session, auth.tenant_id)
    by_ns = {item["namespace"]: item for item in indexed.get("items") or []}
    knowledge = []
    for item in data.get("knowledge") or []:
        meta = by_ns.get(item["namespace"]) or {}
        knowledge.append(
            {
                **item,
                "indexed": bool(meta),
                "chunk_count": meta.get("chunk_count"),
                "dimension": meta.get("dimension"),
                "indexed_at": meta.get("updated_at"),
            }
        )
    data["knowledge"] = knowledge
    return data
