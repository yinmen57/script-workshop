"""生图 / 生视频：提交与完结分离（无长轮询）。

submit：创建上游任务；finalize：下载 OSS 并写业务表。
方舟 Seedream 为同步生图：submit 即拿到 URL，由调度直接 finalize。
"""

from __future__ import annotations

import json
import logging
import mimetypes
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.adapters.media_client import (
    client_provider,
    default_video_duration,
    default_video_ratio,
    default_video_resolution,
    extract_image_result_url,
    extract_video_result_url,
    get_image_client,
    get_video_client,
    image_size_for_target,
    is_sync_image_provider,
)
from business.script import material_image_service, project_service
from framework.domain.errors import NotFoundError, ValidationAppError
from framework.domain.ids import new_id
from framework.infra.config import get_settings
from framework.infra.oss import put_bytes

logger = logging.getLogger(__name__)


def _video_job_public(row: dict[str, Any]) -> dict[str, Any]:
    cfg = row.get("generation_config")
    if isinstance(cfg, str):
        cfg = json.loads(cfg)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "video_prompt_id": row["video_prompt_id"],
        "video_segment_id": row["video_segment_id"],
        "narrative_space_id": row["narrative_space_id"],
        "provider_job_id": row.get("provider_job_id"),
        "status": row["status"],
        "oss_uri": row.get("oss_uri"),
        "result_url": row.get("result_url"),
        "error": row.get("error"),
        "duration_sec": float(row["duration_sec"])
        if row.get("duration_sec") is not None
        else None,
        "generation_config": cfg,
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "finished_at": str(row["finished_at"]) if row.get("finished_at") else None,
    }


async def _download_bytes(url: str) -> tuple[bytes, str | None]:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type")
        return resp.content, ctype


def _store_generated(
    *,
    tenant_id: str,
    project_id: str,
    kind: str,
    filename: str,
    data: bytes,
    content_type: str | None,
) -> str:
    """产物写入 OSS：tenant/project/generated/{kind}/{uuid_filename}。"""
    settings = get_settings()
    if not settings.oss_enabled:
        raise ValidationAppError("OSS 未启用，无法落生成产物")
    safe = filename.replace("\\", "/").split("/")[-1]
    key = f"{tenant_id}/{project_id}/generated/{kind}/{safe}"
    return put_bytes(key, data, content_type=content_type)


def _ext_from_url(url: str, default: str) -> str:
    path = urlparse(url).path
    if "." in path:
        return path.rsplit(".", 1)[-1][:8]
    return default


async def _require_material_prompt(
    session: AsyncSession, tenant_id: str, prompt_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM material_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("material prompt not found")
    return dict(row)


async def _require_video_prompt(
    session: AsyncSession, tenant_id: str, prompt_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_prompt
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": prompt_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("video prompt not found")
    return dict(row)


async def submit_material_image(
    session: AsyncSession,
    tenant_id: str,
    material_prompt_id: str,
) -> dict[str, Any]:
    """校验并创建上游生图任务；方舟同步生图直接返回结果载荷。"""
    prompt = await _require_material_prompt(session, tenant_id, material_prompt_id)
    if (prompt.get("record_status") or "ai") != "confirmed":
        raise ValidationAppError("请先确认物料提示词再生成图片")
    project_id = prompt["project_id"]
    await project_service.require_project(session, tenant_id, project_id)

    client = await get_image_client(tenant_id)
    provider = client_provider(client)
    preflight = await client.preflight()
    size = image_size_for_target(prompt["target_type"])
    gen_cfg = {
        "image_model": client.model_name,
        "size": size,
        "preflight_credits": preflight.get("credits"),
        "provider": provider,
    }

    created = await client.create_image_task(
        prompt=prompt["prompt_text"],
        size=size,
        negative_prompt=prompt.get("negative_prompt") or None,
    )
    task_id = str(created.get("id") or created.get("task_id") or "")
    if not task_id:
        raise ValidationAppError(f"生图未返回 task id: {created}")

    ready = is_sync_image_provider(provider) or bool(created.get("sync"))
    result_payload = created if ready else None
    if ready and not extract_image_result_url(created, provider=provider):
        raise ValidationAppError(f"同步生图未返回图片 URL: {created}")

    return {
        "provider_task_id": task_id,
        "project_id": project_id,
        "material_prompt_id": material_prompt_id,
        "gen_cfg": gen_cfg,
        "preflight": preflight,
        "prompt": prompt,
        "provider": provider,
        "ready_for_finalize": ready,
        "result_payload": result_payload,
    }


async def finalize_material_image(
    session: AsyncSession,
    tenant_id: str,
    *,
    material_prompt_id: str,
    provider_task_id: str,
    result_payload: dict[str, Any] | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """上游已成功：下载并登记 material_image。"""
    prompt = await _require_material_prompt(session, tenant_id, material_prompt_id)
    project_id = prompt["project_id"]

    payload = result_payload
    resolved_provider = provider
    if payload is None:
        client = await get_image_client(tenant_id)
        resolved_provider = client_provider(client)
        payload = await client.get_task(provider_task_id)
    elif not resolved_provider:
        client = await get_image_client(tenant_id)
        resolved_provider = client_provider(client)

    src_url = extract_image_result_url(payload, provider=resolved_provider)
    if not src_url:
        raise ValidationAppError("生图成功但无结果 URL")

    data, ctype = await _download_bytes(src_url)
    ext = _ext_from_url(src_url, "png")
    filename = f"{uuid4().hex}.{ext}"
    oss_uri = _store_generated(
        tenant_id=tenant_id,
        project_id=project_id,
        kind="material",
        filename=filename,
        data=data,
        content_type=ctype or mimetypes.guess_type(filename)[0],
    )

    image = await material_image_service.register_image(
        session,
        tenant_id,
        project_id,
        {
            "url": oss_uri,
            "label": f"{prompt['target_type']}:{prompt['target_id']}",
            "origin": "generated",
            "source_kind": prompt["target_type"],
            "source_id": prompt["target_id"],
            "prompt": prompt["prompt_text"],
            "generation_config": {
                "provider": resolved_provider,
                "provider_task_id": provider_task_id,
                "provider_url": src_url,
                "material_prompt_id": material_prompt_id,
            },
        },
    )
    return {
        "image": image,
        "provider_task_id": provider_task_id,
        "material_prompt_id": material_prompt_id,
        "oss_uri": oss_uri,
        "result_url": src_url,
    }


async def list_video_jobs(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    if narrative_space_id:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM video_job
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND narrative_space_id = :ns_id
                    ORDER BY created_at DESC
                    """
                ),
                {
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "ns_id": narrative_space_id,
                },
            )
        ).mappings().all()
    else:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT * FROM video_job
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                    ORDER BY created_at DESC
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    items = [_video_job_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def submit_video(
    session: AsyncSession,
    tenant_id: str,
    video_prompt_id: str,
) -> dict[str, Any]:
    """校验、落 video_job，并创建上游生视频任务。"""
    vp = await _require_video_prompt(session, tenant_id, video_prompt_id)
    if (vp.get("record_status") or "ai") != "confirmed":
        raise ValidationAppError("请先确认成片提示词再生成视频")
    project_id = vp["project_id"]
    ns_id = vp["narrative_space_id"]
    segment_id = vp["video_segment_id"]
    await project_service.require_project(session, tenant_id, project_id)

    client = await get_video_client(tenant_id)
    provider = client_provider(client)
    preflight = await client.preflight()

    content: list[dict[str, Any]] = [
        {"type": "text", "text": vp["prompt_text"]},
    ]
    ref_ids = vp.get("ref_image_ids") or []
    if isinstance(ref_ids, str):
        ref_ids = json.loads(ref_ids)
    for rid in ref_ids or []:
        img = (
            await session.execute(
                text(
                    """
                    SELECT url FROM material_image
                    WHERE id = :id AND tenant_id = :tenant_id
                      AND project_id = :project_id
                    """
                ),
                {
                    "id": rid,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                },
            )
        ).mappings().first()
        if img and img.get("url"):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": img["url"]},
                    "role": "reference_image",
                }
            )

    duration = vp.get("duration_sec")
    if duration is not None:
        try:
            duration_i = int(round(float(duration)))
        except (TypeError, ValueError):
            duration_i = default_video_duration(provider=provider)
    else:
        duration_i = default_video_duration(provider=provider)
    if duration_i > 15:
        duration_i = 15

    gen_cfg = {
        "video_model": client.model_name,
        "duration": duration_i,
        "resolution": default_video_resolution(provider=provider),
        "ratio": default_video_ratio(provider=provider),
        "preflight_credits": preflight.get("credits"),
        "ref_image_count": max(0, len(content) - 1),
        "provider": provider,
    }

    job_id = new_id("svj")
    await session.execute(
        text(
            """
            INSERT INTO video_job
              (id, tenant_id, project_id, video_prompt_id, video_segment_id,
               narrative_space_id, status, duration_sec, generation_config)
            VALUES
              (:id, :tenant_id, :project_id, :video_prompt_id, :video_segment_id,
               :narrative_space_id, 'queued', :duration_sec,
               CAST(:generation_config AS JSON))
            """
        ),
        {
            "id": job_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "video_prompt_id": video_prompt_id,
            "video_segment_id": segment_id,
            "narrative_space_id": ns_id,
            "duration_sec": float(duration_i) if duration_i and duration_i > 0 else None,
            "generation_config": json.dumps(gen_cfg, ensure_ascii=False),
        },
    )
    await session.commit()

    try:
        created = await client.create_video_task(
            content=content,
            duration=duration_i,
            resolution=default_video_resolution(provider=provider),
            ratio=default_video_ratio(provider=provider),
        )
        provider_id = str(created.get("id") or created.get("task_id") or "")
        if not provider_id:
            raise ValidationAppError(f"生视频未返回 task id: {created}")
        await session.execute(
            text(
                """
                UPDATE video_job
                SET status = 'processing', provider_job_id = :pid
                WHERE id = :id
                """
            ),
            {"id": job_id, "pid": provider_id},
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001 — 落 failed 状态
        msg = getattr(exc, "message", None) or str(exc)
        await session.execute(
            text(
                """
                UPDATE video_job
                SET status = 'failed', error = :error,
                    finished_at = CURRENT_TIMESTAMP(3)
                WHERE id = :id
                """
            ),
            {"id": job_id, "error": msg[:4000]},
        )
        await session.commit()
        raise

    return {
        "provider_task_id": provider_id,
        "video_job_id": job_id,
        "project_id": project_id,
        "video_prompt_id": video_prompt_id,
        "gen_cfg": gen_cfg,
        "preflight": preflight,
        "provider": provider,
        "ready_for_finalize": False,
    }


async def finalize_video(
    session: AsyncSession,
    tenant_id: str,
    *,
    video_job_id: str,
    provider_task_id: str,
    result_payload: dict[str, Any] | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """上游已成功：下载视频并更新 video_job。"""
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_job
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": video_job_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("video_job not found")
    job = dict(row)
    project_id = job["project_id"]

    payload = result_payload
    resolved_provider = provider
    if payload is None:
        client = await get_video_client(tenant_id)
        resolved_provider = client_provider(client)
        payload = await client.get_task(provider_task_id)
    elif not resolved_provider:
        client = await get_video_client(tenant_id)
        resolved_provider = client_provider(client)

    result_url = extract_video_result_url(payload, provider=resolved_provider)
    if not result_url:
        raise ValidationAppError("生视频成功但无结果 URL")

    data, ctype = await _download_bytes(str(result_url))
    ext = _ext_from_url(str(result_url), "mp4")
    filename = f"{uuid4().hex}.{ext}"
    oss_uri = _store_generated(
        tenant_id=tenant_id,
        project_id=project_id,
        kind="video",
        filename=filename,
        data=data,
        content_type=ctype or "video/mp4",
    )
    await session.execute(
        text(
            """
            UPDATE video_job
            SET status = 'succeeded', oss_uri = :oss_uri, result_url = :result_url,
                finished_at = CURRENT_TIMESTAMP(3), error = NULL
            WHERE id = :id
            """
        ),
        {
            "id": video_job_id,
            "oss_uri": oss_uri,
            "result_url": str(result_url),
        },
    )
    await session.commit()

    row2 = (
        await session.execute(
            text("SELECT * FROM video_job WHERE id = :id"),
            {"id": video_job_id},
        )
    ).mappings().first()
    return {
        "video_job": _video_job_public(dict(row2)),
        "video_prompt_id": job["video_prompt_id"],
        "oss_uri": oss_uri,
        "result_url": str(result_url),
    }


async def mark_video_job_failed(
    session: AsyncSession, video_job_id: str, error: str
) -> None:
    await session.execute(
        text(
            """
            UPDATE video_job
            SET status = 'failed', error = :error,
                finished_at = CURRENT_TIMESTAMP(3)
            WHERE id = :id AND status IN ('queued', 'processing')
            """
        ),
        {"id": video_job_id, "error": (error or "")[:4000]},
    )
    await session.commit()
