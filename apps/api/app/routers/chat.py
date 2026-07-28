"""对话与会话接口。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from app.deps import AuthDep, DbSession, RequestIdDep
from packages.domain.permissions import APP_READ
from packages.governance import agent_run_service, chat_service
from packages.governance.audit import write_audit

router = APIRouter(tags=["chat"])


@router.post("/chat/completions")
async def chat_completions(
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
):
    auth.require(APP_READ)
    slug = body.get("slug") or ""
    prepared = await chat_service.prepare_completion(
        session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        slug=slug,
        session_id=body.get("session_id"),
        message=body.get("message") or "",
        request_id=request_id,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="chat.completions",
        request_id=request_id,
        resource_type="workspace",
        resource_id=slug,
        payload={"stream": bool(body.get("stream"))},
    )

    if body.get("stream"):

        async def event_gen():
            async for item in chat_service.complete_stream(session, prepared):
                yield {
                    "event": item["event"],
                    "data": json.dumps(item["data"], ensure_ascii=False),
                }

        return EventSourceResponse(event_gen())

    data = await chat_service.complete_non_stream(session, prepared)
    return data


@router.get("/sessions")
async def list_sessions(
    auth: AuthDep,
    session: DbSession,
    slug: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    auth.require(APP_READ)
    return await chat_service.list_sessions(
        session, auth.tenant_id, slug=slug, page=page, page_size=page_size
    )


@router.get("/sessions/{session_id}/messages")
async def session_messages(
    session_id: str, auth: AuthDep, session: DbSession
) -> dict:
    auth.require(APP_READ)
    items = await chat_service.list_messages(session, auth.tenant_id, session_id)
    return {"items": items}


@router.get("/traces/{request_id}")
async def get_trace(request_id: str, auth: AuthDep, session: DbSession) -> dict:
    auth.require(APP_READ)
    return await chat_service.get_trace(session, auth.tenant_id, request_id)


@router.get("/agent/runs/{run_id}")
async def get_agent_run(run_id: str, auth: AuthDep, session: DbSession) -> dict:
    """按 run_id 或 request_id 查询运行轨迹。"""
    auth.require(APP_READ)
    return await agent_run_service.get_run(session, auth.tenant_id, run_id)
