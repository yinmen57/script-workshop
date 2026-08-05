"""对话与会话接口：流式走 WebSocket，非流式仍用 POST。"""

from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.deps import AuthDep, DbSession, RequestIdDep
from framework.domain.errors import AppError, UnauthorizedError, ValidationAppError
from framework.domain.permissions import APP_READ
from framework.governance import agent_run_service, chat_service
from framework.governance.audit import write_audit
from framework.governance.auth_service import resolve_bearer
from framework.infra.db import get_session_factory

router = APIRouter(tags=["chat"])


@router.post("/chat/completions")
async def chat_completions(
    body: dict,
    auth: AuthDep,
    session: DbSession,
    request_id: RequestIdDep,
):
    """非流式对话；流式请用 WebSocket /chat/ws。"""
    auth.require(APP_READ)
    if body.get("stream"):
        raise ValidationAppError("流式对话请使用 WebSocket：/api/v1/chat/ws")
    slug = body.get("slug") or ""
    selection = body.get("selection")
    agent_id = body.get("agent_id")
    if selection is not None and not isinstance(selection, dict):
        raise ValidationAppError("selection 必须是对象")
    if agent_id is not None and not isinstance(agent_id, str):
        raise ValidationAppError("agent_id 必须是字符串")
    prepared = await chat_service.prepare_completion(
        session,
        tenant_id=auth.tenant_id,
        user_id=auth.user_id,
        slug=slug,
        session_id=body.get("session_id"),
        message=body.get("message") or "",
        request_id=request_id,
        selection=selection,
        agent_id=agent_id,
    )
    await write_audit(
        session,
        tenant_id=auth.tenant_id,
        actor=auth.actor,
        action="chat.completions",
        request_id=request_id,
        resource_type="workspace",
        resource_id=slug,
        payload={"stream": False, "agent_id": prepared.get("agent_id")},
    )
    return await chat_service.complete_non_stream(session, prepared)


@router.websocket("/chat/ws")
async def chat_ws(websocket: WebSocket) -> None:
    """流式对话 WebSocket。

    查询参数：token=<access_token>
    客户端首包：{ "action": "chat", "slug", "message", "session_id?", "selection?", "agent_id?" }
    可选取消：{ "action": "cancel" }
    服务端推送：{ "event": "reasoning"|"delta"|"step"|"usage"|"done"|"error", "data": {...} }
    """
    token = (websocket.query_params.get("token") or "").strip()
    await websocket.accept()
    if not token:
        await websocket.send_json(
            {
                "event": "error",
                "data": {"code": "UNAUTHORIZED", "message": "missing token"},
            }
        )
        await websocket.close(code=4401)
        return

    factory = get_session_factory()
    try:
        async with factory() as session:
            auth = await resolve_bearer(session, token)
            auth.require(APP_READ)
    except (UnauthorizedError, AppError) as exc:
        await websocket.send_json(
            {
                "event": "error",
                "data": {
                    "code": getattr(exc, "code", None) or "UNAUTHORIZED",
                    "message": str(exc),
                },
            }
        )
        await websocket.close(code=4401)
        return

    # 等客户端发起 chat；可 cancel
    run_task: asyncio.Task | None = None
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {
                            "code": "VALIDATION_ERROR",
                            "message": "消息必须是 JSON",
                        },
                    }
                )
                continue
            action = msg.get("action") or "chat"
            if action == "cancel":
                if run_task and not run_task.done():
                    run_task.cancel()
                continue
            if action != "chat":
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {
                            "code": "VALIDATION_ERROR",
                            "message": f"未知 action: {action}",
                        },
                    }
                )
                continue
            if run_task and not run_task.done():
                await websocket.send_json(
                    {
                        "event": "error",
                        "data": {
                            "code": "BUSY",
                            "message": "上一轮仍在进行，请先 cancel",
                        },
                    }
                )
                continue

            async def _run_one(payload: dict) -> None:
                request_id = f"req_{uuid.uuid4().hex}"
                selection = payload.get("selection")
                agent_id = payload.get("agent_id")
                if selection is not None and not isinstance(selection, dict):
                    await websocket.send_json(
                        {
                            "event": "error",
                            "data": {
                                "code": "VALIDATION_ERROR",
                                "message": "selection 必须是对象",
                                "request_id": request_id,
                            },
                        }
                    )
                    return
                if agent_id is not None and not isinstance(agent_id, str):
                    await websocket.send_json(
                        {
                            "event": "error",
                            "data": {
                                "code": "VALIDATION_ERROR",
                                "message": "agent_id 必须是字符串",
                                "request_id": request_id,
                            },
                        }
                    )
                    return
                slug = payload.get("slug") or ""
                async with factory() as session:
                    try:
                        prepared = await chat_service.prepare_completion(
                            session,
                            tenant_id=auth.tenant_id,
                            user_id=auth.user_id,
                            slug=slug,
                            session_id=payload.get("session_id"),
                            message=payload.get("message") or "",
                            request_id=request_id,
                            selection=selection,
                            agent_id=agent_id,
                        )
                        await write_audit(
                            session,
                            tenant_id=auth.tenant_id,
                            actor=auth.actor,
                            action="chat.ws",
                            request_id=request_id,
                            resource_type="workspace",
                            resource_id=slug,
                            payload={
                                "stream": True,
                                "agent_id": prepared.get("agent_id"),
                            },
                        )
                        async for item in chat_service.complete_stream(
                            session, prepared
                        ):
                            await websocket.send_json(
                                {
                                    "event": item["event"],
                                    "data": item["data"],
                                }
                            )
                    except asyncio.CancelledError:
                        await websocket.send_json(
                            {
                                "event": "error",
                                "data": {
                                    "code": "CANCELLED",
                                    "message": "已取消",
                                    "request_id": request_id,
                                },
                            }
                        )
                        raise
                    except AppError as exc:
                        await websocket.send_json(
                            {
                                "event": "error",
                                "data": {
                                    "code": getattr(exc, "code", None)
                                    or "APP_ERROR",
                                    "message": str(exc),
                                    "request_id": request_id,
                                },
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        await websocket.send_json(
                            {
                                "event": "error",
                                "data": {
                                    "code": "INTERNAL_ERROR",
                                    "message": str(exc),
                                    "request_id": request_id,
                                },
                            }
                        )

            run_task = asyncio.create_task(_run_one(msg))
            try:
                await run_task
            except asyncio.CancelledError:
                pass
            finally:
                run_task = None
    except WebSocketDisconnect:
        if run_task and not run_task.done():
            run_task.cancel()
            try:
                await run_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


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
