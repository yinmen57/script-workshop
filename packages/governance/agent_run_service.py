"""Agent 运行轨迹落库与查询。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.errors import NotFoundError
from packages.domain.ids import new_id


async def ensure_agent_run_tables(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agent_run (
              id VARCHAR(32) PRIMARY KEY,
              tenant_id VARCHAR(32) NOT NULL,
              workspace_slug VARCHAR(128) NOT NULL,
              session_id VARCHAR(32) NULL,
              request_id VARCHAR(64) NOT NULL,
              status VARCHAR(16) NOT NULL,
              answer MEDIUMTEXT NULL,
              error_message VARCHAR(1024) NULL,
              prompt_tokens INT NULL,
              completion_tokens INT NULL,
              latency_ms INT NULL,
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_agent_run_request (request_id),
              INDEX idx_agent_run_slug (tenant_id, workspace_slug, created_at)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS agent_run_step (
              id VARCHAR(32) PRIMARY KEY,
              run_id VARCHAR(32) NOT NULL,
              step_no INT NOT NULL,
              agent_id VARCHAR(64) NOT NULL,
              type VARCHAR(16) NOT NULL,
              tool_id VARCHAR(128) NULL,
              args_json JSON NULL,
              output_json MEDIUMTEXT NULL,
              duration_ms INT NULL,
              error VARCHAR(1024) NULL,
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              UNIQUE KEY uq_agent_run_step (run_id, step_no),
              INDEX idx_agent_run_step_run (run_id)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.commit()


async def create_run(
    session: AsyncSession,
    *,
    tenant_id: str,
    workspace_slug: str,
    session_id: str,
    request_id: str,
) -> str:
    run_id = new_id("run")
    await session.execute(
        text(
            """
            INSERT INTO agent_run
              (id, tenant_id, workspace_slug, session_id, request_id, status)
            VALUES
              (:id, :tenant_id, :slug, :session_id, :request_id, 'running')
            """
        ),
        {
            "id": run_id,
            "tenant_id": tenant_id,
            "slug": workspace_slug,
            "session_id": session_id,
            "request_id": request_id,
        },
    )
    await session.commit()
    return run_id


async def append_step(
    session: AsyncSession,
    *,
    run_id: str,
    step: dict[str, Any],
) -> None:
    output = step.get("output")
    if output is not None and not isinstance(output, str):
        output = json.dumps(output, ensure_ascii=False, default=str)
    args = step.get("args")
    await session.execute(
        text(
            """
            INSERT INTO agent_run_step
              (id, run_id, step_no, agent_id, type, tool_id, args_json,
               output_json, duration_ms, error)
            VALUES
              (:id, :run_id, :step_no, :agent_id, :type, :tool_id, CAST(:args AS JSON),
               :output, :duration_ms, :error)
            """
        ),
        {
            "id": new_id("stp"),
            "run_id": run_id,
            "step_no": int(step["step_no"]),
            "agent_id": step.get("agent_id") or "",
            "type": step.get("type") or "thought",
            "tool_id": step.get("tool_id"),
            "args": json.dumps(args, ensure_ascii=False) if args is not None else None,
            "output": output,
            "duration_ms": step.get("duration_ms"),
            "error": (step.get("error") or None),
        },
    )
    await session.commit()


async def finish_run(
    session: AsyncSession,
    *,
    run_id: str,
    status: str,
    answer: str | None = None,
    error_message: str | None = None,
    usage: dict | None = None,
    latency_ms: int | None = None,
) -> None:
    usage = usage or {}
    await session.execute(
        text(
            """
            UPDATE agent_run SET
              status = :status,
              answer = :answer,
              error_message = :error_message,
              prompt_tokens = :prompt_tokens,
              completion_tokens = :completion_tokens,
              latency_ms = :latency_ms
            WHERE id = :id
            """
        ),
        {
            "id": run_id,
            "status": status,
            "answer": answer,
            "error_message": error_message,
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "latency_ms": latency_ms,
        },
    )
    await session.commit()


async def get_run(
    session: AsyncSession, tenant_id: str, run_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM agent_run
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": run_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        # 也支持按 request_id 查
        row = (
            await session.execute(
                text(
                    """
                    SELECT * FROM agent_run
                    WHERE request_id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": run_id, "tenant_id": tenant_id},
            )
        ).mappings().first()
    if row is None:
        raise NotFoundError("agent run not found")

    steps = (
        await session.execute(
            text(
                """
                SELECT step_no, agent_id, type, tool_id, args_json, output_json,
                       duration_ms, error, created_at
                FROM agent_run_step
                WHERE run_id = :run_id
                ORDER BY step_no ASC
                """
            ),
            {"run_id": row["id"]},
        )
    ).mappings().all()

    step_items = []
    for s in steps:
        args = s["args_json"]
        if isinstance(args, str):
            args = json.loads(args)
        step_items.append(
            {
                "step_no": s["step_no"],
                "agent_id": s["agent_id"],
                "type": s["type"],
                "tool_id": s["tool_id"],
                "args": args,
                "output": s["output_json"],
                "duration_ms": s["duration_ms"],
                "error": s["error"],
                "created_at": str(s["created_at"]) if s.get("created_at") else None,
            }
        )

    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "workspace_slug": row["workspace_slug"],
        "session_id": row["session_id"],
        "request_id": row["request_id"],
        "status": row["status"],
        "answer": row["answer"],
        "error_message": row["error_message"],
        "usage": {
            "prompt_tokens": row["prompt_tokens"] or 0,
            "completion_tokens": row["completion_tokens"] or 0,
        },
        "latency_ms": row["latency_ms"],
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "steps": step_items,
    }
