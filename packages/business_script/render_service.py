"""生图 / 生视频：走赏舞薄客户端，产物落 OSS 与业务表。

要求：物料提示词 / 成片提示词须已 confirmed；提交前做余额预检。
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

from packages.adapters.sd_client import get_sd_client
from packages.business_script import material_image_service, project_service
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id
from packages.infra.config import get_settings
from packages.infra.oss import put_bytes

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


def _image_size_for_target(target_type: str) -> str:
    settings = get_settings()
    if target_type == "character":
        return settings.sd_character_size
    if target_type == "prop":
        return settings.sd_background_size
    return settings.sd_background_size


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


async def render_material_image(
    session: AsyncSession,
    tenant_id: str,
    material_prompt_id: str,
) -> dict[str, Any]:
    """为已确认物料提示词生图，登记 material_image。"""
    prompt = await _require_material_prompt(session, tenant_id, material_prompt_id)
    if (prompt.get("record_status") or "ai") != "confirmed":
        raise ValidationAppError("请先确认物料提示词再生成图片")
    project_id = prompt["project_id"]
    await project_service.require_project(session, tenant_id, project_id)

    settings = get_settings()
    client = get_sd_client()
    preflight = await client.preflight()
    size = _image_size_for_target(prompt["target_type"])
    gen_cfg = {
        "image_model": settings.sd_image_model,
        "size": size,
        "resolution": settings.sd_resolution_norm,
        "preflight_credits": preflight.get("credits"),
    }

    created = await client.create_image_task(
        prompt=prompt["prompt_text"],
        size=size,
        negative_prompt=prompt.get("negative_prompt") or None,
    )
    task_id = str(created.get("id") or created.get("task_id") or "")
    if not task_id:
        raise ValidationAppError(f"赏舞生图未返回 task id: {created}")

    done = await client.poll_task(
        task_id,
        interval_sec=float(settings.sd_poll_interval_seconds),
        timeout_sec=float(settings.sd_poll_timeout_seconds),
    )
    urls = done.get("result_image_urls") or done.get("image_urls") or []
    if isinstance(urls, str):
        urls = [urls]
    if not urls:
        raise ValidationAppError("赏舞生图成功但无结果 URL")
    src_url = urls[0]
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
                **gen_cfg,
                "provider_task_id": task_id,
                "provider_url": src_url,
                "material_prompt_id": material_prompt_id,
            },
        },
    )
    return {
        "image": image,
        "provider_task_id": task_id,
        "preflight": preflight,
        "material_prompt_id": material_prompt_id,
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


async def render_video(
    session: AsyncSession,
    tenant_id: str,
    video_prompt_id: str,
) -> dict[str, Any]:
    """为已确认成片提示词生成一段视频片段成片，写入 video_job。"""
    vp = await _require_video_prompt(session, tenant_id, video_prompt_id)
    if (vp.get("record_status") or "ai") != "confirmed":
        raise ValidationAppError("请先确认成片提示词再生成视频")
    project_id = vp["project_id"]
    ns_id = vp["narrative_space_id"]
    segment_id = vp["video_segment_id"]
    await project_service.require_project(session, tenant_id, project_id)

    settings = get_settings()
    client = get_sd_client()
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

    # 业务 duration：优先提示词；否则配置；并封顶 15
    duration = vp.get("duration_sec")
    if duration is not None:
        try:
            duration_i = int(round(float(duration)))
        except (TypeError, ValueError):
            duration_i = settings.sd_video_duration
    else:
        duration_i = settings.sd_video_duration
    if duration_i > 15:
        duration_i = 15

    gen_cfg = {
        "video_model": settings.sd_video_model,
        "duration": duration_i,
        "resolution": settings.sd_video_resolution,
        "ratio": settings.sd_video_ratio,
        "preflight_credits": preflight.get("credits"),
        "ref_image_count": max(0, len(content) - 1),
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
        )
        provider_id = str(created.get("id") or created.get("task_id") or "")
        if not provider_id:
            raise ValidationAppError(f"赏舞生视频未返回 task id: {created}")
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

        done = await client.poll_task(
            provider_id,
            interval_sec=float(settings.sd_video_poll_interval_seconds),
            timeout_sec=float(settings.sd_video_poll_timeout_seconds),
        )
        result_url = (
            done.get("stored_video_url")
            or done.get("video_url")
            or (done.get("result") or {}).get("video_url")
        )
        if not result_url:
            raise ValidationAppError("赏舞生视频成功但无结果 URL")

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
                "id": job_id,
                "oss_uri": oss_uri,
                "result_url": str(result_url),
            },
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

    row = (
        await session.execute(
            text("SELECT * FROM video_job WHERE id = :id"),
            {"id": job_id},
        )
    ).mappings().first()
    return {
        "video_job": _video_job_public(dict(row)),
        "preflight": preflight,
        "video_prompt_id": video_prompt_id,
    }
