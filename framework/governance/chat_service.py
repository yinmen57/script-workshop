"""对话与会话服务：slug 标识应用，接入 Agent 工具循环与轨迹。"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from framework.agent_apps.runtime import iter_agent_run
from framework.domain.errors import NotFoundError, ValidationAppError
from framework.domain.ids import new_id
from framework.governance import agent_run_service, app_service, model_service

# 近期原文条数；超出部分压入会话 summary
_RECENT_MESSAGE_LIMIT = 8
_HISTORY_SOFT_LIMIT = 12
_SUMMARY_MAX_CHARS = 2400


async def ensure_chat_schema(session: AsyncSession) -> None:
    """会话列扩宽 + Agent 轨迹表 + 向量命名空间表。"""
    await session.execute(
        text("ALTER TABLE chat_session MODIFY COLUMN app_id VARCHAR(128) NOT NULL")
    )
    await session.execute(
        text("ALTER TABLE run_trace MODIFY COLUMN app_id VARCHAR(128) NULL")
    )
    # 会话长期摘要（不存在则加列）
    exists = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'chat_session'
                  AND COLUMN_NAME = 'summary'
                """
            )
        )
    ).mappings().first()
    if not exists or int(exists["c"]) == 0:
        await session.execute(
            text("ALTER TABLE chat_session ADD COLUMN summary MEDIUMTEXT NULL")
        )
    await session.commit()
    await agent_run_service.ensure_agent_run_tables(session)
    from framework.governance.vector_namespace_service import ensure_namespace_table

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


def _compress_history_excerpt(
    messages: list[dict[str, Any]], prior_summary: str | None
) -> str:
    """抽取式会话摘要，避免无限拉长 prompt。"""
    lines: list[str] = []
    if prior_summary and prior_summary.strip():
        lines.append(prior_summary.strip())
    for item in messages:
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        label = "用户" if role == "user" else "助手"
        content = " ".join(str(item.get("content") or "").split())
        if len(content) > 220:
            content = content[:220] + "…"
        if content:
            lines.append(f"- {label}: {content}")
    text = "\n".join(lines).strip()
    if len(text) > _SUMMARY_MAX_CHARS:
        text = text[:_SUMMARY_MAX_CHARS] + "…"
    return text


async def _load_session_summary(
    session: AsyncSession, tenant_id: str, session_id: str
) -> str | None:
    row = (
        await session.execute(
            text(
                """
                SELECT summary FROM chat_session
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": session_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if not row:
        return None
    summary = row.get("summary")
    return str(summary) if summary else None


async def _save_session_summary(
    session: AsyncSession, *, tenant_id: str, session_id: str, summary: str
) -> None:
    await session.execute(
        text(
            """
            UPDATE chat_session
            SET summary = :summary, updated_at = CURRENT_TIMESTAMP(3)
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"summary": summary, "id": session_id, "tenant_id": tenant_id},
    )
    await session.commit()


def _format_selection_block(selection: dict[str, Any] | None) -> str:
    """把前端结构化选中对象拼成系统前缀，避免把 id 塞进用户原文。"""
    if not selection or not isinstance(selection, dict):
        return ""
    project_id = selection.get("project_id")
    sel = selection.get("selection") if isinstance(selection.get("selection"), dict) else selection
    lines = ["当前工作台选中上下文（结构化，勿编造未列出的 id）："]
    if project_id:
        lines.append(f"- project_id: {project_id}")
    for key in (
        "type",
        "id",
        "episode_id",
        "narrative_space_id",
        "video_segment_id",
        "shot_id",
        "title",
    ):
        value = sel.get(key) if isinstance(sel, dict) else None
        if value:
            lines.append(f"- {key}: {value}")
    lines.append(
        "若用户文字指向的对象与上述选中冲突，先向用户确认，不要静默选择其中一个。"
    )
    return "\n".join(lines)


def _resolve_run_agent(
    app: dict[str, Any], agent_id: str | None
) -> tuple[str | None, dict[str, Any] | None]:
    """解析调试目标 Agent；返回 (agent_id|None, agent_dict|None)。"""
    raw = (agent_id or "").strip() or None
    if raw is None:
        return None, None
    for agent in app.get("agents") or []:
        if agent.get("agent_id") == raw:
            return raw, agent
    raise ValidationAppError(f"应用中不存在 Agent：{raw}")


async def prepare_completion(
    session: AsyncSession,
    *,
    tenant_id: str,
    user_id: str | None,
    slug: str,
    session_id: str | None,
    message: str,
    request_id: str,
    selection: dict[str, Any] | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    if not slug or not message.strip():
        raise ValidationAppError("slug and message required")

    app = app_service.get_app(tenant_id, slug)
    run_agent_id, run_agent = _resolve_run_agent(app, agent_id)

    if run_agent is not None:
        system_content = run_agent.get("system_prompt_content") or (
            f"你是 {run_agent.get('name') or run_agent_id}。"
        )
        max_steps = int(run_agent.get("max_steps") or app.get("max_steps") or 8)
        session_title = f"[{run_agent_id}] {message}"
    else:
        system_content = app.get("system_prompt") or (
            "你是企业助手。需要时请调用可用工具完成任务。"
        )
        max_steps = int(app.get("max_steps") or 8)
        session_title = message

    sid = await ensure_session(
        session,
        tenant_id=tenant_id,
        slug=slug,
        user_id=user_id,
        session_id=session_id,
        title=session_title,
    )

    history = await list_messages(session, tenant_id, sid)
    prior_summary = await _load_session_summary(session, tenant_id, sid)
    recent = history
    if len(history) > _HISTORY_SOFT_LIMIT:
        older = history[:-_RECENT_MESSAGE_LIMIT]
        recent = history[-_RECENT_MESSAGE_LIMIT:]
        prior_summary = _compress_history_excerpt(older, prior_summary)
        await _save_session_summary(
            session, tenant_id=tenant_id, session_id=sid, summary=prior_summary
        )

    selection_block = _format_selection_block(selection)
    if selection_block:
        system_content = system_content + "\n\n" + selection_block
    if prior_summary:
        system_content = (
            system_content
            + "\n\n以下是本会话较早轮次的摘要（长期记忆，勿编造未出现的事实）：\n"
            + prior_summary
        )
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": system_content,
        }
    ]
    for item in recent:
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
        "messages": messages,
        "request_id": request_id,
        "agent_id": run_agent_id,
        "max_steps": max_steps,
    }


async def _drive_agent(
    session: AsyncSession, prepared: dict
) -> AsyncIterator[dict[str, Any]]:
    """LangGraph 执行循环：产出 delta / step / 最终结果字典（_final）。"""
    app = prepared["app"]
    request_id = prepared["request_id"]
    async for ev in iter_agent_run(
        app=app,
        messages=prepared["messages"],
        max_steps=int(prepared.get("max_steps") or app.get("max_steps") or 8),
        agent_id=prepared.get("agent_id"),
    ):
        if ev.get("_final"):
            yield ev
            continue
        if ev.get("_delta"):
            yield {
                "event": "delta",
                "data": {
                    "text": ev.get("text") or "",
                    "request_id": request_id,
                    "agent_id": ev.get("agent_id"),
                },
            }
            continue
        await agent_run_service.append_step(
            session, run_id=prepared["run_id"], step=ev
        )
        yield {"event": "step", "data": {**ev, "request_id": request_id}}


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
            "model": (
                await model_service.load_runtime_model(app["tenant_id"], "chat")
            )["model_name"],
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
        # 已 token 流式推送则不再整段重复；未流式时兜底一次 delta
        if answer and not final.get("streamed"):
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
