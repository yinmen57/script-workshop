"""剧本业务作业：投递、去重、状态机、等待完成。

状态：queued → running → done / failed / cancelled。
同 project + dedupe_key 下仅允许一个活动作业（queued|running）。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import project_service
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("done", "failed", "cancelled")

KIND_PARSE = "parse"
KIND_STRUCTURE = "structure_parse"
KIND_SEGMENT = "narrative_segment"
KIND_INDEX_NARRATIVE = "index_narrative"
KIND_MATERIAL = "material_prompts"
KIND_PLAN_SHOTS = "plan_shots"
KIND_VIDEO_SEGMENTS = "video_segments"
KIND_VIDEO_PROMPTS = "video_prompts"
KIND_RENDER_IMAGE = "render_material_image"
KIND_RENDER_VIDEO = "render_video"


def _job_public(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if isinstance(payload, str):
        payload = json.loads(payload)
    result = row.get("result")
    if isinstance(result, str):
        result = json.loads(result)

    def _ts(v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat(sep=" ", timespec="milliseconds")
        return str(v)

    public = {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "project_id": row["project_id"],
        "kind": row["kind"],
        "dedupe_key": row["dedupe_key"],
        "label": row.get("label") or "",
        "status": row["status"],
        "progress": int(row.get("progress") or 0),
        "payload": payload,
        "result": result,
        "error": row.get("error"),
        "cancel_requested": bool(int(row.get("cancel_requested") or 0)),
        "created_by": row.get("created_by"),
        "created_at": _ts(row.get("created_at")),
        "started_at": _ts(row.get("started_at")),
        "finished_at": _ts(row.get("finished_at")),
    }
    public.update(_recovery_fields(public))
    return public


def _business_object_from_payload(
    kind: str, payload: dict[str, Any] | None
) -> dict[str, Any] | None:
    payload = payload or {}
    if payload.get("video_segment_id"):
        return {"type": "video_segment", "id": payload["video_segment_id"]}
    if payload.get("narrative_space_id"):
        return {"type": "narrative_space", "id": payload["narrative_space_id"]}
    if payload.get("video_prompt_id"):
        return {"type": "video_prompt", "id": payload["video_prompt_id"]}
    if payload.get("material_prompt_id"):
        return {"type": "material_prompt", "id": payload["material_prompt_id"]}
    if kind in {
        KIND_PARSE,
        KIND_STRUCTURE,
        KIND_SEGMENT,
        KIND_INDEX_NARRATIVE,
        KIND_MATERIAL,
        KIND_PLAN_SHOTS,
        KIND_VIDEO_SEGMENTS,
        KIND_VIDEO_PROMPTS,
    }:
        return None
    return None


def _recovery_fields(job: dict[str, Any]) -> dict[str, Any]:
    status = job.get("status")
    progress = int(job.get("progress") or 0)
    if status in ACTIVE_STATUSES:
        step = "queued" if status == "queued" else f"running@{progress}"
    elif status == "done":
        step = "done"
    elif status == "failed":
        step = "failed"
    else:
        step = status or "unknown"
    return {
        "current_step": step,
        "business_object": _business_object_from_payload(
            job.get("kind") or "", job.get("payload") if isinstance(job.get("payload"), dict) else {}
        ),
        "retryable": status == "failed",
        "waiting_confirmation": False,
        "has_result": bool(job.get("result")),
    }


def job_recovery_view(job: dict[str, Any]) -> dict[str, Any]:
    """供 inspect / 选择 Agent 使用的任务恢复摘要。"""
    payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
    return {
        "id": job["id"],
        "project_id": job["project_id"],
        "kind": job["kind"],
        "dedupe_key": job.get("dedupe_key"),
        "label": job.get("label") or "",
        "status": job["status"],
        "progress": int(job.get("progress") or 0),
        "current_step": job.get("current_step"),
        "business_object": job.get("business_object")
        or _business_object_from_payload(job.get("kind") or "", payload),
        "error": job.get("error"),
        "retryable": bool(job.get("retryable")),
        "waiting_confirmation": bool(job.get("waiting_confirmation")),
        "has_result": bool(job.get("has_result") or job.get("result")),
        "result": job.get("result") if job.get("status") == "done" else None,
        "created_at": job.get("created_at"),
        "finished_at": job.get("finished_at"),
    }


async def get_job(session: AsyncSession, tenant_id: str, job_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM job_run
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": job_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("job not found")
    return _job_public(dict(row))


async def list_jobs(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    limit = max(1, min(int(limit), 200))
    if status:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM job_run
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                      AND status = :status
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "status": status,
                    "limit": limit,
                },
            )
        ).mappings().all()
    else:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM job_run
                    WHERE tenant_id = :tenant_id AND project_id = :project_id
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "limit": limit,
                },
            )
        ).mappings().all()
    items = [_job_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def find_active(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    dedupe_key: str,
) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM job_run
                WHERE tenant_id = :tenant_id AND project_id = :project_id
                  AND dedupe_key = :dedupe_key
                  AND status IN ('queued', 'running')
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "dedupe_key": dedupe_key,
            },
        )
    ).mappings().first()
    return _job_public(dict(row)) if row else None


async def submit_job(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    kind: str,
    dedupe_key: str,
    label: str,
    payload: dict[str, Any] | None = None,
    created_by: str | None = None,
    enqueue: bool = True,
) -> dict:
    """创建作业并投递到 Redis Stream；若已有活动作业则直接返回。"""
    await project_service.require_project(session, tenant_id, project_id)
    active = await find_active(
        session,
        tenant_id=tenant_id,
        project_id=project_id,
        dedupe_key=dedupe_key,
    )
    if active:
        return {**active, "deduped": True}

    job_id = new_id("sjob")
    await session.execute(
        text(
            """
            INSERT INTO job_run
              (id, tenant_id, project_id, kind, dedupe_key, label, status,
               progress, payload, cancel_requested, created_by)
            VALUES
              (:id, :tenant_id, :project_id, :kind, :dedupe_key, :label, 'queued',
               0, CAST(:payload AS JSON), 0, :created_by)
            """
        ),
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "kind": kind,
            "dedupe_key": dedupe_key,
            "label": label[:255],
            "payload": json.dumps(payload or {}, ensure_ascii=False),
            "created_by": created_by,
        },
    )
    await session.commit()
    job = await get_job(session, tenant_id, job_id)

    if enqueue:
        from packages.infra.queue_stream import enqueue_script_job

        await enqueue_script_job(
            {
                "job_id": job_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "kind": kind,
            }
        )
    return {**job, "deduped": False}


async def mark_running(session: AsyncSession, job_id: str) -> dict | None:
    row = (
        await session.execute(
            text("SELECT * FROM job_run WHERE id = :id"),
            {"id": job_id},
        )
    ).mappings().first()
    if row is None:
        return None
    if row["status"] != "queued":
        return _job_public(dict(row))
    if int(row.get("cancel_requested") or 0):
        await session.execute(
            text(
                """
                UPDATE job_run
                SET status = 'cancelled', progress = 100,
                    finished_at = CURRENT_TIMESTAMP(3),
                    error = 'cancelled before start'
                WHERE id = :id
                """
            ),
            {"id": job_id},
        )
        await session.commit()
        return await get_job(session, row["tenant_id"], job_id)
    await session.execute(
        text(
            """
            UPDATE job_run
            SET status = 'running', progress = 5,
                started_at = CURRENT_TIMESTAMP(3)
            WHERE id = :id AND status = 'queued'
            """
        ),
        {"id": job_id},
    )
    await session.commit()
    return await get_job(session, row["tenant_id"], job_id)


async def mark_progress(session: AsyncSession, job_id: str, progress: int) -> None:
    await session.execute(
        text(
            """
            UPDATE job_run
            SET progress = :progress
            WHERE id = :id AND status = 'running'
            """
        ),
        {"id": job_id, "progress": max(0, min(int(progress), 99))},
    )
    await session.commit()


async def mark_done(
    session: AsyncSession, job_id: str, result: dict[str, Any] | None = None
) -> dict:
    row = (
        await session.execute(
            text("SELECT tenant_id FROM job_run WHERE id = :id"),
            {"id": job_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("job not found")
    await session.execute(
        text(
            """
            UPDATE job_run
            SET status = 'done', progress = 100,
                result = CAST(:result AS JSON),
                finished_at = CURRENT_TIMESTAMP(3),
                error = NULL
            WHERE id = :id
            """
        ),
        {
            "id": job_id,
            "result": json.dumps(result or {}, ensure_ascii=False),
        },
    )
    await session.commit()
    return await get_job(session, row["tenant_id"], job_id)


async def mark_failed(session: AsyncSession, job_id: str, error: str) -> dict:
    row = (
        await session.execute(
            text("SELECT tenant_id FROM job_run WHERE id = :id"),
            {"id": job_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("job not found")
    await session.execute(
        text(
            """
            UPDATE job_run
            SET status = 'failed', progress = 100,
                error = :error,
                finished_at = CURRENT_TIMESTAMP(3)
            WHERE id = :id
            """
        ),
        {"id": job_id, "error": (error or "unknown error")[:4000]},
    )
    await session.commit()
    return await get_job(session, row["tenant_id"], job_id)


async def request_cancel(
    session: AsyncSession, tenant_id: str, job_id: str
) -> dict:
    job = await get_job(session, tenant_id, job_id)
    if job["status"] in TERMINAL_STATUSES:
        return job
    await session.execute(
        text(
            """
            UPDATE job_run
            SET cancel_requested = 1
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": job_id, "tenant_id": tenant_id},
    )
    if job["status"] == "queued":
        await session.execute(
            text(
                """
                UPDATE job_run
                SET status = 'cancelled', progress = 100,
                    finished_at = CURRENT_TIMESTAMP(3),
                    error = 'cancelled'
                WHERE id = :id AND status = 'queued'
                """
            ),
            {"id": job_id},
        )
    await session.commit()
    return await get_job(session, tenant_id, job_id)


async def is_cancel_requested(session: AsyncSession, job_id: str) -> bool:
    row = (
        await session.execute(
            text("SELECT cancel_requested FROM job_run WHERE id = :id"),
            {"id": job_id},
        )
    ).mappings().first()
    return bool(row and int(row["cancel_requested"] or 0))


async def wait_until_terminal(
    *,
    tenant_id: str,
    job_id: str,
    timeout_sec: float = 600,
    poll_interval: float = 1.0,
) -> dict:
    """供 Agent 工具等待作业完成。"""
    from packages.infra.db import get_session_factory

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_sec
    factory = get_session_factory()
    while True:
        async with factory() as session:
            job = await get_job(session, tenant_id, job_id)
        if job["status"] in TERMINAL_STATUSES:
            if job["status"] == "failed":
                raise ValidationAppError(job.get("error") or "作业失败")
            if job["status"] == "cancelled":
                raise ValidationAppError("作业已取消")
            return job
        if loop.time() >= deadline:
            raise ValidationAppError(f"作业等待超时：{job_id}")
        await asyncio.sleep(poll_interval)
