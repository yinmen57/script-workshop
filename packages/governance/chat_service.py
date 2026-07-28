"""对话与会话服务：slug 标识应用，接入 Agent 工具循环与轨迹。"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.adapters.llm_openai import OpenAICompatibleChatAdapter
from packages.core.agent_runtime import iter_agent_run
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id
from packages.governance import agent_run_service, app_service
from packages.infra.config import get_settings


async def ensure_chat_schema(session: AsyncSession) -> None:
    """会话列扩宽 + Agent 轨迹表 + 向量命名空间表。"""
    await session.execute(
        text("ALTER TABLE chat_session MODIFY COLUMN app_id VARCHAR(128) NOT NULL")
    )
    await session.execute(
        text("ALTER TABLE run_trace MODIFY COLUMN app_id VARCHAR(128) NULL")
    )
    await session.commit()
    await agent_run_service.ensure_agent_run_tables(session)
    from packages.governance.vector_namespace_service import ensure_namespace_table

    await ensure_namespace_table(session)


async def ensure_session(
    session: AsyncSession,
    *,
    tenant_id: str,
    slug: str,
    user_id: str | None,
    session_id: str | None,
    title: str,
) -> str:
    if session_id:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id FROM chat_session
                    WHERE id = :id AND tenant_id = :tenant_id AND app_id = :slug
                    """
                ),
                {"id": session_id, "tenant_id": tenant_id, "slug": slug},
            )
        ).mappings().first()
        if row is None:
            raise NotFoundError("session not found")
        return session_id

    sid = new_id("ses")
    await session.execute(
        text(
            """
            INSERT INTO chat_session (id, tenant_id, app_id, user_id, title, status)
            VALUES (:id, :tenant_id, :slug, :user_id, :title, 'active')
            """
        ),
        {
            "id": sid,
            "tenant_id": tenant_id,
            "slug": slug,
            "user_id": user_id,
            "title": title[:200],
        },
    )
    await session.commit()
    return sid


async def list_messages(
    session: AsyncSession, tenant_id: str, session_id: str
) -> list[dict]:
    await _get_session(session, tenant_id, session_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT id, role, content, token_count, request_id, created_at
                FROM chat_message
                WHERE session_id = :session_id
                ORDER BY created_at ASC
                """
            ),
            {"session_id": session_id},
        )
    ).mappings().all()
    return [
        {
            **dict(r),
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
        }
        for r in rows
    ]


async def list_sessions(
    session: AsyncSession,
    tenant_id: str,
    *,
    slug: str | None,
    page: int,
    page_size: int,
) -> dict:
    where = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": tenant_id}
    if slug:
        where.append("app_id = :slug")
        params["slug"] = slug
    where_sql = " AND ".join(where)
    total = (
        await session.execute(
            text(f"SELECT COUNT(1) AS c FROM chat_session WHERE {where_sql}"),
            params,
        )
    ).mappings().first()["c"]
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, app_id AS slug, title, status, created_at, updated_at
                FROM chat_session
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [
            {
                **dict(r),
                "created_at": str(r["created_at"]) if r.get("created_at") else None,
                "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
            }
            for r in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


def _build_chat_adapter(app: dict) -> OpenAICompatibleChatAdapter:
    settings = get_settings()
    primary = (app.get("model") or {}).get("primary") or "default"
    if primary != "default":
        raise ValidationAppError(f"未知模型逻辑名：{primary}（当前仅支持 default）")
    timeout_ms = int(
        (app.get("model") or {}).get("timeout_ms") or settings.llm_timeout * 1000
    )
    return OpenAICompatibleChatAdapter(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        timeout_ms=timeout_ms,
    )


async def prepare_completion(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str | None,
    slug: str,
    session_id: str | None,
    message: str,
    request_id: str,
) -> dict[str, Any]:
    if not slug or not message.strip():
        raise ValidationAppError("slug and message required")

    app = app_service.get_app(tenant_id, slug)
    adapter = _build_chat_adapter(app)

    sid = await ensure_session(
        session,
        tenant_id=tenant_id,
        slug=slug,
        user_id=user_id,
        session_id=session_id,
        title=message,
    )

    history = await list_messages(session, tenant_id, sid)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": app.get("system_prompt")
            or "你是企业助手。需要时请调用可用工具完成任务。",
        }
    ]
    for item in history[-12:]:
        if item["role"] in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": message})

    await _insert_message(
        session,
        session_id=sid,
        role="user",
        content=message,
        request_id=request_id,
    )

    run_id = await agent_run_service.create_run(
        session,
        tenant_id=tenant_id,
        workspace_slug=slug,
        session_id=sid,
        request_id=request_id,
    )

    return {
        "session_id": sid,
        "run_id": run_id,
        "app": app,
        "adapter": adapter,
        "messages": messages,
        "request_id": request_id,
    }


async def _drive_agent(
    session: AsyncSession, prepared: dict
) -> AsyncIterator[dict[str, Any]]:
    """执行循环：产出 step / 最终结果字典（_final）。"""
    app = prepared["app"]
    async for ev in iter_agent_run(
        slug=app["slug"],
        workspace_path=app["workspace_path"],
        agent_id=app["coordinator_agent_id"],
        messages=prepared["messages"],
        tools=app.get("allowed_tools") or [],
        adapter=prepared["adapter"],
        max_steps=int(app.get("max_steps") or 8),
        tenant_id=app["tenant_id"],
        specialists=app.get("specialists") or [],
        workspace_tools=app.get("all_tools") or [],
    ):
        if ev.get("_final"):
            yield ev
            continue
        await agent_run_service.append_step(
            session, run_id=prepared["run_id"], step=ev
        )
        yield {"event": "step", "data": {**ev, "request_id": prepared["request_id"]}}


async def complete_non_stream(session: AsyncSession, prepared: dict) -> dict:
    started = time.perf_counter()
    request_id = prepared["request_id"]
    app = prepared["app"]
    steps: list[dict] = []
    try:
        final: dict[str, Any] | None = None
        async for ev in _drive_agent(session, prepared):
            if ev.get("_final"):
                final = ev
            elif ev.get("event") == "step":
                steps.append(ev["data"])
        if final is None:
            raise RuntimeError("agent run produced no final result")
        answer = final["answer"]
        usage = final["usage"]
        await _insert_message(
            session,
            session_id=prepared["session_id"],
            role="assistant",
            content=answer,
            request_id=request_id,
            token_count=usage.get("completion_tokens"),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        await agent_run_service.finish_run(
            session,
            run_id=prepared["run_id"],
            status="succeeded",
            answer=answer,
            usage=usage,
            latency_ms=latency_ms,
        )
        await _write_trace(
            session,
            request_id=request_id,
            tenant_id=app["tenant_id"],
            slug=app["slug"],
            session_id=prepared["session_id"],
            model_id=app["model"].get("primary") or "default",
            status="success",
            latency_ms=latency_ms,
            usage=usage,
            tool_trace=final.get("tool_trace") or [],
        )
        return {
            "request_id": request_id,
            "run_id": prepared["run_id"],
            "session_id": prepared["session_id"],
            "answer": answer,
            "model": get_settings().llm_model,
            "usage": usage,
            "tool_trace": final.get("tool_trace") or [],
            "steps": steps,
            "citations": [],
        }
    except Exception as exc:  # noqa: BLE001
        await agent_run_service.finish_run(
            session,
            run_id=prepared["run_id"],
            status="failed",
            error_message=str(exc),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        await _write_trace(
            session,
            request_id=request_id,
            tenant_id=app["tenant_id"],
            slug=app["slug"],
            session_id=prepared["session_id"],
            model_id=app["model"].get("primary") or "default",
            status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage={},
            tool_trace=[],
            error_code="MODEL_UNAVAILABLE",
            detail={"error": str(exc)},
        )
        raise


async def complete_stream(
    session: AsyncSession, prepared: dict
) -> AsyncIterator[dict[str, Any]]:
    started = time.perf_counter()
    request_id = prepared["request_id"]
    app = prepared["app"]
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    try:
        final: dict[str, Any] | None = None
        async for ev in _drive_agent(session, prepared):
            if ev.get("_final"):
                final = ev
                continue
            yield ev

        if final is None:
            raise RuntimeError("agent run produced no final result")
        answer = final.get("answer") or ""
        usage = final.get("usage") or usage
        if answer:
            yield {
                "event": "delta",
                "data": {"text": answer, "request_id": request_id},
            }
        yield {"event": "usage", "data": {**usage, "request_id": request_id}}
        await _insert_message(
            session,
            session_id=prepared["session_id"],
            role="assistant",
            content=answer,
            request_id=request_id,
            token_count=usage.get("completion_tokens"),
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        await agent_run_service.finish_run(
            session,
            run_id=prepared["run_id"],
            status="succeeded",
            answer=answer,
            usage=usage,
            latency_ms=latency_ms,
        )
        await _write_trace(
            session,
            request_id=request_id,
            tenant_id=app["tenant_id"],
            slug=app["slug"],
            session_id=prepared["session_id"],
            model_id=app["model"].get("primary") or "default",
            status="success",
            latency_ms=latency_ms,
            usage=usage,
            tool_trace=final.get("tool_trace") or [],
        )
        yield {
            "event": "done",
            "data": {
                "request_id": request_id,
                "run_id": prepared["run_id"],
                "session_id": prepared["session_id"],
                "answer": answer,
            },
        }
    except Exception as exc:  # noqa: BLE001
        await agent_run_service.finish_run(
            session,
            run_id=prepared["run_id"],
            status="failed",
            error_message=str(exc),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
        await _write_trace(
            session,
            request_id=request_id,
            tenant_id=app["tenant_id"],
            slug=app["slug"],
            session_id=prepared["session_id"],
            model_id=app["model"].get("primary") or "default",
            status="error",
            latency_ms=int((time.perf_counter() - started) * 1000),
            usage=usage,
            tool_trace=[],
            error_code="MODEL_UNAVAILABLE",
            detail={"error": str(exc)},
        )
        yield {
            "event": "error",
            "data": {
                "request_id": request_id,
                "code": "MODEL_UNAVAILABLE",
                "message": str(exc),
                "details": {},
            },
        }


async def get_trace(session: AsyncSession, tenant_id: str, request_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM run_trace
                WHERE request_id = :request_id AND tenant_id = :tenant_id
                """
            ),
            {"request_id": request_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("trace not found")
    detail = row["detail"]
    if isinstance(detail, str):
        detail = json.loads(detail)
    return {
        **dict(row),
        "detail": detail or {},
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


async def _get_session(session: AsyncSession, tenant_id: str, session_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM chat_session
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": session_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("session not found")
    return dict(row)


async def _insert_message(
    session: AsyncSession,
    *,
    session_id: str,
    role: str,
    content: str,
    request_id: str,
    token_count: int | None = None,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO chat_message
              (id, session_id, role, content, token_count, request_id)
            VALUES
              (:id, :session_id, :role, :content, :token_count, :request_id)
            """
        ),
        {
            "id": new_id("msg"),
            "session_id": session_id,
            "role": role,
            "content": content,
            "token_count": token_count,
            "request_id": request_id,
        },
    )
    await session.execute(
        text("UPDATE chat_session SET updated_at = CURRENT_TIMESTAMP(3) WHERE id = :id"),
        {"id": session_id},
    )
    await session.commit()


async def _write_trace(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: str,
    slug: str,
    session_id: str,
    model_id: str,
    status: str,
    latency_ms: int,
    usage: dict,
    tool_trace: list,
    error_code: str | None = None,
    detail: dict | None = None,
) -> None:
    payload = {
        "tool_trace": tool_trace,
        **(detail or {}),
    }
    await session.execute(
        text(
            """
            INSERT INTO run_trace
              (request_id, tenant_id, app_id, session_id, run_type, model_id, status,
               latency_ms, prompt_tokens, completion_tokens, error_code, detail)
            VALUES
              (:request_id, :tenant_id, :slug, :session_id, 'chat', :model_id, :status,
               :latency_ms, :prompt_tokens, :completion_tokens, :error_code, :detail)
            ON DUPLICATE KEY UPDATE
              status = VALUES(status),
              latency_ms = VALUES(latency_ms),
              prompt_tokens = VALUES(prompt_tokens),
              completion_tokens = VALUES(completion_tokens),
              error_code = VALUES(error_code),
              detail = VALUES(detail)
            """
        ),
        {
            "request_id": request_id,
            "tenant_id": tenant_id,
            "slug": slug,
            "session_id": session_id,
            "model_id": model_id,
            "status": status,
            "latency_ms": latency_ms,
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "error_code": error_code,
            "detail": json.dumps(payload, ensure_ascii=False),
        },
    )
    await session.commit()
