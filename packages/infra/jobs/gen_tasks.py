"""生成任务：submit / finalize + Beat 调度。"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from packages.adapters.media_client import (
    classify_provider_status,
    get_image_client,
    get_video_client,
    provider_error_message,
)
from packages.business_script import generation_service as gen_svc
from packages.business_script import job_service, render_service
from packages.infra.async_bridge import run_async
from packages.infra.celery_app import celery_app
from packages.infra.jobs.enqueue import enqueue_gen_finalize, enqueue_gen_submit

logger = logging.getLogger(__name__)


def _owner(task_self: Any, prefix: str) -> str:
    req = getattr(task_self, "request", None)
    tid = getattr(req, "id", None) or "local"
    host = getattr(req, "hostname", None) or "worker"
    return f"{prefix}:{host}:{tid}"


async def _fail_generation(
    session: Any,
    task: dict[str, Any],
    error: str,
    *,
    event: str = "failed",
    forced: bool = False,
) -> None:
    await gen_svc.update_task(
        session,
        task["id"],
        status=gen_svc.STATUS_FAILED,
        error=error,
        finished=True,
        event=event,
        phase=gen_svc.STATUS_FAILED,
        event_extra={"forced": forced} if forced else None,
    )
    if task.get("video_job_id"):
        await render_service.mark_video_job_failed(
            session, task["video_job_id"], error
        )
    await job_service.mark_failed(session, task["job_run_id"], error)
    if forced:
        gen_svc.on_generation_forced_fail(task)


async def _submit_one(task_id: str, owner: str) -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        task = await gen_svc.begin_submit(session, task_id=task_id, owner=owner)
        if task is None:
            logger.info("gen.submit skip (not pending) id=%s", task_id)
            return

        if await job_service.is_cancel_requested(session, task["job_run_id"]):
            await gen_svc.update_task(
                session,
                task_id,
                status=gen_svc.STATUS_CANCELLED,
                error="cancelled",
                finished=True,
                event="cancelled",
                phase=gen_svc.STATUS_CANCELLED,
            )
            await job_service.mark_failed(session, task["job_run_id"], "cancelled")
            return

        running = await job_service.mark_running(session, task["job_run_id"])
        if running and running["status"] in job_service.TERMINAL_STATUSES:
            await gen_svc.update_task(
                session,
                task_id,
                status=gen_svc.STATUS_CANCELLED,
                error="job already terminal",
                finished=True,
                event="cancelled",
                phase=gen_svc.STATUS_CANCELLED,
            )
            return

        tenant_id = task["tenant_id"]
        try:
            if task["kind"] == "image":
                submitted = await render_service.submit_material_image(
                    session, tenant_id, task["biz_ref_id"]
                )
                snapshot_patch: dict[str, Any] = {
                    "provider": submitted.get("provider") or task.get("provider"),
                }
                if submitted.get("ready_for_finalize") and submitted.get(
                    "result_payload"
                ):
                    snapshot_patch["sync_result"] = submitted["result_payload"]
                await gen_svc.update_task(
                    session,
                    task_id,
                    status=gen_svc.STATUS_WAITING,
                    provider_task_id=submitted["provider_task_id"],
                    submitted=True,
                    event="submitted",
                    phase=gen_svc.STATUS_WAITING,
                    event_extra={
                        "provider_task_id": submitted["provider_task_id"],
                        "ready_for_finalize": bool(
                            submitted.get("ready_for_finalize")
                        ),
                    },
                    snapshot_patch=snapshot_patch,
                )
                await gen_svc.clear_claim(session, task_id)
                await job_service.mark_progress(session, task["job_run_id"], 40)
                # 方舟同步生图：跳过长等待，直接 finalize
                if submitted.get("ready_for_finalize"):
                    enqueue_gen_finalize(task_id)
            elif task["kind"] == "video":
                submitted = await render_service.submit_video(
                    session, tenant_id, task["biz_ref_id"]
                )
                await gen_svc.update_task(
                    session,
                    task_id,
                    status=gen_svc.STATUS_WAITING,
                    provider_task_id=submitted["provider_task_id"],
                    video_job_id=submitted["video_job_id"],
                    submitted=True,
                    event="submitted",
                    phase=gen_svc.STATUS_WAITING,
                    event_extra={
                        "provider_task_id": submitted["provider_task_id"],
                        "video_job_id": submitted["video_job_id"],
                    },
                    snapshot_patch={
                        "provider": submitted.get("provider") or task.get("provider"),
                    },
                )
                await gen_svc.clear_claim(session, task_id)
                await job_service.mark_progress(session, task["job_run_id"], 40)
            else:
                raise ValueError(f"unknown generation kind: {task['kind']}")
        except Exception as exc:  # noqa: BLE001 — 边界落失败
            msg = getattr(exc, "message", None) or str(exc)
            logger.exception("gen.submit failed id=%s", task_id)
            await _fail_generation(session, task, msg, event="submit_failed")


async def _finalize_one(task_id: str, owner: str) -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        task = await gen_svc.begin_finalize(session, task_id=task_id, owner=owner)
        if task is None:
            logger.info("gen.finalize skip id=%s", task_id)
            return

        provider_task_id = task.get("provider_task_id") or ""
        if not provider_task_id:
            await _fail_generation(session, task, "缺少 provider_task_id")
            return

        tenant_id = task["tenant_id"]
        snapshot = task.get("stage_snapshot") or {}
        sync_result = snapshot.get("sync_result")
        provider = task.get("provider") or snapshot.get("provider")
        try:
            if task["kind"] == "image":
                result = await render_service.finalize_material_image(
                    session,
                    tenant_id,
                    material_prompt_id=task["biz_ref_id"],
                    provider_task_id=provider_task_id,
                    result_payload=sync_result if isinstance(sync_result, dict) else None,
                    provider=provider,
                )
                image = result.get("image") or {}
                job_result = {
                    "material_prompt_id": task["biz_ref_id"],
                    "image_id": image.get("id"),
                    "url": image.get("url"),
                    "provider_task_id": provider_task_id,
                    "generation_task_id": task_id,
                }
                await gen_svc.update_task(
                    session,
                    task_id,
                    status=gen_svc.STATUS_SUCCEEDED,
                    oss_uri=result.get("oss_uri"),
                    result_url=result.get("result_url"),
                    finished=True,
                    event="finalized",
                    phase=gen_svc.STATUS_SUCCEEDED,
                )
            elif task["kind"] == "video":
                video_job_id = task.get("video_job_id") or ""
                if not video_job_id:
                    raise ValueError("缺少 video_job_id")
                result = await render_service.finalize_video(
                    session,
                    tenant_id,
                    video_job_id=video_job_id,
                    provider_task_id=provider_task_id,
                    provider=provider,
                )
                vj = result.get("video_job") or {}
                job_result = {
                    "video_prompt_id": task["biz_ref_id"],
                    "video_job_id": vj.get("id"),
                    "status": vj.get("status"),
                    "oss_uri": vj.get("oss_uri"),
                    "generation_task_id": task_id,
                }
                await gen_svc.update_task(
                    session,
                    task_id,
                    status=gen_svc.STATUS_SUCCEEDED,
                    oss_uri=result.get("oss_uri"),
                    result_url=result.get("result_url"),
                    finished=True,
                    event="finalized",
                    phase=gen_svc.STATUS_SUCCEEDED,
                )
            else:
                raise ValueError(f"unknown generation kind: {task['kind']}")

            await job_service.mark_done(session, task["job_run_id"], job_result)
        except Exception as exc:  # noqa: BLE001
            msg = getattr(exc, "message", None) or str(exc)
            logger.exception("gen.finalize failed id=%s", task_id)
            await _fail_generation(session, task, msg, event="finalize_failed")


async def _fetch_provider_once(task: dict[str, Any]) -> dict[str, Any]:
    tenant_id = task["tenant_id"]
    provider_task_id = task.get("provider_task_id") or ""
    if not provider_task_id:
        raise ValueError("缺少 provider_task_id")
    # 同步生图结果已在 snapshot，无需再查上游
    snapshot = task.get("stage_snapshot") or {}
    sync_result = snapshot.get("sync_result")
    if isinstance(sync_result, dict):
        return sync_result
    if task["kind"] == "image":
        client = await get_image_client(tenant_id)
    else:
        client = await get_video_client(tenant_id)
    return await client.get_task(provider_task_id)


async def _poll_one(task: dict[str, Any], owner: str) -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        claimed = await gen_svc.begin_poll(
            session, task_id=task["id"], owner=owner
        )
        if claimed is None:
            return
        task = claimed
        provider = task.get("provider") or (task.get("stage_snapshot") or {}).get(
            "provider"
        )
        try:
            if await job_service.is_cancel_requested(session, task["job_run_id"]):
                await _fail_generation(session, task, "cancelled", event="cancelled")
                return
            payload = await _fetch_provider_once(task)
            state = classify_provider_status(payload, provider=provider)
            await gen_svc.update_task(
                session,
                task["id"],
                polled=True,
                provider_status=state,
                event="poll",
                event_extra={"provider_status": state},
            )
            if state == "succeeded":
                await gen_svc.clear_claim(session, task["id"])
                enqueue_gen_finalize(task["id"])
            elif state == "failed":
                await _fail_generation(
                    session,
                    task,
                    provider_error_message(payload, provider=provider),
                    event="provider_failed",
                )
            else:
                await gen_svc.clear_claim(session, task["id"])
                await job_service.mark_progress(session, task["job_run_id"], 60)
        except Exception as exc:  # noqa: BLE001
            msg = getattr(exc, "message", None) or str(exc)
            logger.exception("gen.poll failed id=%s", task["id"])
            await gen_svc.clear_claim(session, task["id"])
            # 单次查询失败不立刻终态，留给对账
            await gen_svc.update_task(
                session,
                task["id"],
                polled=True,
                event="poll_error",
                event_extra={"error": msg[:500]},
            )


async def _dispatch_pending() -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        pending = await gen_svc.list_pending_for_dispatch(
            session, limit=gen_svc.submit_batch()
        )
    by_tenant: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in pending:
        by_tenant[item["tenant_id"]].append(item)

    owner = "beat:dispatch"
    for tenant_id, tasks in by_tenant.items():
        async with factory() as session:
            inflight = await gen_svc.count_inflight(session, tenant_id)
        slots = max(0, gen_svc.max_inflight() - inflight)
        for task in tasks[:slots]:
            async with factory() as session:
                reserved = await gen_svc.reserve_for_dispatch(
                    session, task_id=task["id"], owner=owner
                )
            if reserved:
                enqueue_gen_submit(task["id"])


async def _poll_waiting() -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        waiting = await gen_svc.list_waiting_for_poll(
            session, limit=gen_svc.poll_batch()
        )
    for task in waiting:
        await _poll_one(task, owner="beat:poll")


async def _reconcile() -> None:
    from packages.infra.db import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        tasks = await gen_svc.list_inflight_for_reconcile(session)

    for task in tasks:
        submitted_age = gen_svc.age_seconds(
            task.get("submitted_at") or task.get("created_at")
        )
        # 超过 2 小时强制失败
        if submitted_age is not None and submitted_age >= 7200:
            async with factory() as session:
                claimed = await gen_svc.begin_reconcile(
                    session, task_id=task["id"], owner="beat:reconcile"
                )
                if claimed is not None:
                    await _fail_generation(
                        session,
                        claimed,
                        "generation forced timeout (2h)",
                        event="forced_timeout",
                        forced=True,
                    )
            continue

        # waiting 无进展 ≥ 30 分钟：回查上游
        if task["status"] != gen_svc.STATUS_WAITING:
            continue
        idle_age = gen_svc.age_seconds(
            task.get("last_polled_at") or task.get("submitted_at") or task.get("created_at")
        )
        if idle_age is None or idle_age < 1800:
            continue
        await _poll_one(task, owner="beat:reconcile")


@celery_app.task(name="gen.submit_one", bind=True, acks_late=True)
def submit_one(self, generation_task_id: str) -> None:
    run_async(_submit_one(generation_task_id, _owner(self, "submit")))


@celery_app.task(name="gen.finalize_one", bind=True, acks_late=True)
def finalize_one(self, generation_task_id: str) -> None:
    run_async(_finalize_one(generation_task_id, _owner(self, "finalize")))


@celery_app.task(name="gen.dispatch_pending")
def dispatch_pending() -> None:
    run_async(_dispatch_pending())


@celery_app.task(name="gen.poll_waiting")
def poll_waiting() -> None:
    run_async(_poll_waiting())


@celery_app.task(name="gen.reconcile")
def reconcile() -> None:
    run_async(_reconcile())
