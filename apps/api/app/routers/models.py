"""模型管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.domain.permissions import MODEL_READ, MODEL_WRITE
from packages.governance import model_service
from packages.governance.audit import write_audit

router = APIRouter(prefix="/models", tags=["models"])


@router.post("")
async def create_model(
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(MODEL_WRITE)
    data = await model_service.create_model(session, auth.tenant_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="model.create",
        request_id=request_id,
        resource_type="model",
        resource_id=data["id"],
    )
    return data


@router.get("")
async def list_models(
    auth: AuthDep,
    session: DbSession,
    model_type: str | None = None,
    status: str | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    auth.require(MODEL_READ)
    return await model_service.list_models(
        session,
        auth.tenant_id,
        model_type=model_type,
        status=status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


@router.get("/{model_id}")
async def get_model(model_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(MODEL_READ)
    return await model_service.get_model(session, auth.tenant_id, model_id)


@router.patch("/{model_id}")
async def update_model(
    model_id: str,
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(MODEL_WRITE)
    data = await model_service.update_model(session, auth.tenant_id, model_id, body)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="model.update",
        request_id=request_id,
        resource_type="model",
        resource_id=model_id,
    )
    return data


@router.delete("/{model_id}")
async def delete_model(
    model_id: str,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
) -> dict:
    auth.require(MODEL_WRITE)
    await model_service.delete_model(session, auth.tenant_id, model_id)
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="model.delete",
        request_id=request_id,
        resource_type="model",
        resource_id=model_id,
    )
    return {"ok": True}


@router.post("/{model_id}/test")
async def test_model(model_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(MODEL_READ)
    return await model_service.test_model(session, auth.tenant_id, model_id)
