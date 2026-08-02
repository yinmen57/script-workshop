"""generation_task：claim、状态与阶段快照。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.ids import new_id
from packages.infra.config import get_settings

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_SUBMITTING = "submitting"
STATUS_WAITING = "waiting_provider"
STATUS_FINALIZING = "finalizing"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

CLAIM_TTL_DISPATCH = 60
CLAIM_TTL_SUBMIT = 120
CLAIM_TTL_POLL = 30
CLAIM_TTL_FINALIZE = 180
CLAIM_TTL_RECONCILE = 60


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        return json.loads(raw) if raw else {}
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _append_event(snapshot: dict[str, Any], event: str, **extra: Any) -> dict[str, Any]:
    events = list(snapshot.get("events") or [])
    item = {"at": _now().isoformat(timespec="milliseconds"), "event": event, **extra}
    events.append(item)
    snapshot["events"] = events[-50:]
    return snapshot


def _row_to_task(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["stage_snapshot"] = _parse_snapshot(data.get("stage_snapshot"))
    return data


async def create_generation_task(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    job_run_id: str,
    kind: str,
    provider: str,
    model_name: str,
    biz_ref_type: str,
    biz_ref_id: str,
) -> dict[str, Any]:
    task_id = new_id("gen")
    snapshot = _append_event(
        {"phase": STATUS_PENDING, "provider": provider},
        "created",
    )
    await session.execute(
        text(
            """
            INSERT INTO generation_task
              (id, tenant_id, project_id, job_run_id, kind, provider, model_name,
               biz_ref_type, biz_ref_id, status, stage_snapshot)
            VALUES
              (:id, :tenant_id, :project_id, :job_run_id, :kind, :provider, :model_name,
               :biz_ref_type, :biz_ref_id, :status, CAST(:stage_snapshot AS JSON))
            """
        ),
        {
            "id": task_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "job_run_id": job_run_id,
            "kind": kind,
            "provider": provider,
            "model_name": model_name,
            "biz_ref_type": biz_ref_type,
            "biz_ref_id": biz_ref_id,
            "status": STATUS_PENDING,
            "stage_snapshot": json.dumps(snapshot, ensure_ascii=False),
        },
    )
    await session.commit()
    return await get_task(session, task_id)


async def get_task(session: AsyncSession, task_id: str) -> dict[str, Any]:
    row = (
        await session.execute(
            text("SELECT * FROM generation_task WHERE id = :id"),
            {"id": task_id},
        )
    ).mappings().first()
    if row is None:
        raise LookupError(f"generation_task not found: {task_id}")
    return _row_to_task(row)


async def reserve_for_dispatch(
    session: AsyncSession,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = CLAIM_TTL_DISPATCH,
) -> bool:
    """Beat 软预留：不改 status，仅占 claim，避免重复投递。"""
    until = _now() + timedelta(seconds=ttl_seconds)
    result = await session.execute(
        text(
            """
            UPDATE generation_task
            SET claim_owner = :owner, claim_until = :until
            WHERE id = :id
              AND status = :status
              AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
            """
        ),
        {
            "id": task_id,
            "status": STATUS_PENDING,
            "owner": owner,
            "until": until,
        },
    )
    await session.commit()
    return result.rowcount == 1


async def begin_submit(
    session: AsyncSession,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = CLAIM_TTL_SUBMIT,
) -> dict[str, Any] | None:
    """pending → submitting（可接管 Beat 预留）。"""
    until = _now() + timedelta(seconds=ttl_seconds)
    result = await session.execute(
        text(
            """
            UPDATE generation_task
            SET status = :new_status,
                claim_owner = :owner,
                claim_until = :until,
                attempt = attempt + 1
            WHERE id = :id AND status = :old_status
            """
        ),
        {
            "id": task_id,
            "old_status": STATUS_PENDING,
            "new_status": STATUS_SUBMITTING,
            "owner": owner,
            "until": until,
        },
    )
    await session.commit()
    if result.rowcount != 1:
        return None
    return await get_task(session, task_id)


async def begin_poll(
    session: AsyncSession,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = CLAIM_TTL_POLL,
) -> dict[str, Any] | None:
    until = _now() + timedelta(seconds=ttl_seconds)
    result = await session.execute(
        text(
            """
            UPDATE generation_task
            SET claim_owner = :owner,
                claim_until = :until,
                attempt = attempt + 1
            WHERE id = :id
              AND status = :status
              AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
            """
        ),
        {
            "id": task_id,
            "status": STATUS_WAITING,
            "owner": owner,
            "until": until,
        },
    )
    await session.commit()
    if result.rowcount != 1:
        return None
    return await get_task(session, task_id)


async def begin_reconcile(
    session: AsyncSession,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = CLAIM_TTL_RECONCILE,
) -> dict[str, Any] | None:
    """对账占用中间态任务。"""
    until = _now() + timedelta(seconds=ttl_seconds)
    result = await session.execute(
        text(
            """
            UPDATE generation_task
            SET claim_owner = :owner,
                claim_until = :until,
                attempt = attempt + 1
            WHERE id = :id
              AND status IN ('submitting', 'waiting_provider', 'finalizing')
              AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
            """
        ),
        {"id": task_id, "owner": owner, "until": until},
    )
    await session.commit()
    if result.rowcount != 1:
        return None
    return await get_task(session, task_id)


async def begin_finalize(
    session: AsyncSession,
    *,
    task_id: str,
    owner: str,
    ttl_seconds: int = CLAIM_TTL_FINALIZE,
) -> dict[str, Any] | None:
    until = _now() + timedelta(seconds=ttl_seconds)
    result = await session.execute(
        text(
            """
            UPDATE generation_task
            SET status = :new_status,
                claim_owner = :owner,
                claim_until = :until,
                attempt = attempt + 1
            WHERE id = :id
              AND status = :old_status
              AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
            """
        ),
        {
            "id": task_id,
            "old_status": STATUS_WAITING,
            "new_status": STATUS_FINALIZING,
            "owner": owner,
            "until": until,
        },
    )
    await session.commit()
    if result.rowcount != 1:
        return None
    return await get_task(session, task_id)


async def clear_claim(session: AsyncSession, task_id: str) -> None:
    await session.execute(
        text(
            """
            UPDATE generation_task
            SET claim_owner = NULL, claim_until = NULL
            WHERE id = :id
            """
        ),
        {"id": task_id},
    )
    await session.commit()


async def update_task(
    session: AsyncSession,
    task_id: str,
    *,
    status: str | None = None,
    provider_task_id: str | None = None,
    error: str | None = None,
    oss_uri: str | None = None,
    result_url: str | None = None,
    video_job_id: str | None = None,
    submitted: bool = False,
    polled: bool = False,
    finished: bool = False,
    event: str | None = None,
    event_extra: dict[str, Any] | None = None,
    phase: str | None = None,
    provider_status: str | None = None,
    snapshot_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    task = await get_task(session, task_id)
    snapshot = dict(task.get("stage_snapshot") or {})
    if phase:
        snapshot["phase"] = phase
    if provider_status is not None:
        snapshot["provider_status"] = provider_status
    if provider_task_id:
        snapshot["provider_task_id"] = provider_task_id
    if snapshot_patch:
        snapshot.update(snapshot_patch)
    if event:
        snapshot = _append_event(snapshot, event, **(event_extra or {}))
    if polled:
        snapshot["poll_count"] = int(snapshot.get("poll_count") or 0) + 1

    sets = ["stage_snapshot = CAST(:stage_snapshot AS JSON)"]
    params: dict[str, Any] = {
        "id": task_id,
        "stage_snapshot": json.dumps(snapshot, ensure_ascii=False),
    }
    if status is not None:
        sets.append("status = :status")
        params["status"] = status
    if provider_task_id is not None:
        sets.append("provider_task_id = :provider_task_id")
        params["provider_task_id"] = provider_task_id
    if error is not None:
        sets.append("error = :error")
        params["error"] = error[:4000]
    if oss_uri is not None:
        sets.append("oss_uri = :oss_uri")
        params["oss_uri"] = oss_uri
    if result_url is not None:
        sets.append("result_url = :result_url")
        params["result_url"] = result_url
    if video_job_id is not None:
        sets.append("video_job_id = :video_job_id")
        params["video_job_id"] = video_job_id
    if submitted:
        sets.append("submitted_at = CURRENT_TIMESTAMP(3)")
    if polled:
        sets.append("last_polled_at = CURRENT_TIMESTAMP(3)")
    if finished:
        sets.append("finished_at = CURRENT_TIMESTAMP(3)")
        sets.append("claim_owner = NULL")
        sets.append("claim_until = NULL")

    await session.execute(
        text(f"UPDATE generation_task SET {', '.join(sets)} WHERE id = :id"),
        params,
    )
    await session.commit()
    return await get_task(session, task_id)


async def list_pending_for_dispatch(
    session: AsyncSession, *, limit: int
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM generation_task
                WHERE status = :status
                  AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"status": STATUS_PENDING, "limit": limit},
        )
    ).mappings().all()
    return [_row_to_task(r) for r in rows]


async def count_inflight(session: AsyncSession, tenant_id: str) -> int:
    row = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM generation_task
                WHERE tenant_id = :tenant_id
                  AND status IN ('submitting', 'waiting_provider', 'finalizing')
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().first()
    return int(row["c"] if row else 0)


async def list_waiting_for_poll(
    session: AsyncSession, *, limit: int
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM generation_task
                WHERE status = :status
                  AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
                ORDER BY COALESCE(last_polled_at, submitted_at, created_at) ASC
                LIMIT :limit
                """
            ),
            {"status": STATUS_WAITING, "limit": limit},
        )
    ).mappings().all()
    return [_row_to_task(r) for r in rows]


async def list_inflight_for_reconcile(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM generation_task
                WHERE status IN ('submitting', 'waiting_provider', 'finalizing')
                  AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3))
                """
            )
        )
    ).mappings().all()
    return [_row_to_task(r) for r in rows]


def on_generation_forced_fail(task: dict[str, Any]) -> None:
    """退款钩子占位：账本接入后在此冲正。"""
    logger.warning(
        "generation forced fail hook task_id=%s job_run_id=%s provider=%s",
        task.get("id"),
        task.get("job_run_id"),
        task.get("provider"),
    )


def max_inflight() -> int:
    return int(get_settings().gen_max_inflight_per_tenant)


def submit_batch() -> int:
    return int(get_settings().gen_submit_batch)


def poll_batch() -> int:
    return int(get_settings().gen_poll_batch)


def age_seconds(ts: Any) -> float | None:
    if ts is None:
        return None
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
    if not isinstance(ts, datetime):
        return None
    return (_now() - ts).total_seconds()
