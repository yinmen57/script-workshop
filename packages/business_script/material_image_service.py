"""统一图片目录：登记生成 / 上传 / 导入图；主记录仅存当前选中指针。

生图客户端（第四段）产出后也走本服务登记。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import project_service
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id

# 可被「设为当前」写回的主表指针
_CURRENT_POINTERS: dict[str, tuple[str, str]] = {
    "scene_space": ("scene_space", "reference_image_url"),
    "costume_change": ("costume_change", "image_url"),
}


def _image_public(row: dict[str, Any]) -> dict[str, Any]:
    gen = row.get("generation_config")
    if isinstance(gen, str):
        gen = json.loads(gen)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "url": row["url"],
        "label": row.get("label") or "",
        "origin": row.get("origin") or "generated",
        "source_kind": row.get("source_kind"),
        "source_id": row.get("source_id"),
        "prompt": row.get("prompt") or "",
        "generation_config": gen,
        "series_wide": bool(int(row.get("series_wide") or 0)),
        "record_status": row.get("record_status") or "ai",
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
    }


async def list_images(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    source_kind: str | None = None,
    source_id: str | None = None,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    clauses = [
        "project_id = :project_id",
        "tenant_id = :tenant_id",
    ]
    params: dict[str, Any] = {"project_id": project_id, "tenant_id": tenant_id}
    if source_kind:
        clauses.append("source_kind = :source_kind")
        params["source_kind"] = source_kind
    if source_id:
        clauses.append("source_id = :source_id")
        params["source_id"] = source_id
    where = " AND ".join(clauses)
    rows = (
        await session.execute(
            text(
                f"""
                SELECT * FROM material_image
                WHERE {where}
                ORDER BY created_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    items = [_image_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def register_image(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    payload: dict[str, Any],
) -> dict:
    """登记一张图片到目录；同一 project+url 唯一。"""
    await project_service.require_project(session, tenant_id, project_id)
    url = (payload.get("url") or "").strip()
    if not url:
        raise ValidationAppError("url 不能为空")
    if len(url) > 512:
        raise ValidationAppError("url 长度不能超过 512")
    label = (payload.get("label") or "").strip()[:255]
    origin = (payload.get("origin") or "uploaded").strip()
    if origin not in ("generated", "uploaded", "imported"):
        raise ValidationAppError("origin 必须是 generated / uploaded / imported")
    source_kind = payload.get("source_kind")
    source_id = payload.get("source_id")
    prompt = payload.get("prompt")
    series_wide = 1 if payload.get("series_wide") else 0
    gen_cfg = payload.get("generation_config")
    if gen_cfg is not None and not isinstance(gen_cfg, dict):
        raise ValidationAppError("generation_config 必须是对象")

    existing = (
        await session.execute(
            text(
                """
                SELECT * FROM material_image
                WHERE project_id = :project_id AND url = :url
                LIMIT 1
                """
            ),
            {"project_id": project_id, "url": url},
        )
    ).mappings().first()
    if existing:
        if existing["tenant_id"] != tenant_id:
            raise ValidationAppError("图片 url 冲突")
        return _image_public(dict(existing))

    image_id = new_id("simg")
    gen_sql = (
        "CAST(:generation_config AS JSON)"
        if gen_cfg is not None
        else "NULL"
    )
    await session.execute(
        text(
            f"""
            INSERT INTO material_image
              (id, tenant_id, project_id, url, label, origin,
               source_kind, source_id, prompt, generation_config,
               series_wide, record_status)
            VALUES
              (:id, :tenant_id, :project_id, :url, :label, :origin,
               :source_kind, :source_id, :prompt, {gen_sql},
               :series_wide, 'ai')
            """
        ),
        {
            "id": image_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "url": url,
            "label": label,
            "origin": origin,
            "source_kind": source_kind,
            "source_id": source_id,
            "prompt": prompt,
            "generation_config": json.dumps(gen_cfg, ensure_ascii=False)
            if gen_cfg is not None
            else None,
            "series_wide": series_wide,
        },
    )
    await session.commit()
    row = (
        await session.execute(
            text("SELECT * FROM material_image WHERE id = :id"),
            {"id": image_id},
        )
    ).mappings().first()
    return _image_public(dict(row))


async def set_current(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    image_id: str,
    source_kind: str,
    source_id: str,
) -> dict:
    """把目录中的图设为主记录当前选中指针。"""
    await project_service.require_project(session, tenant_id, project_id)
    if source_kind not in _CURRENT_POINTERS:
        raise ValidationAppError(
            f"source_kind 暂不支持设为当前，可选：{', '.join(_CURRENT_POINTERS)}"
        )
    image = (
        await session.execute(
            text(
                """
                SELECT * FROM material_image
                WHERE id = :id AND project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"id": image_id, "project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if image is None:
        raise NotFoundError("material image not found")

    table, column = _CURRENT_POINTERS[source_kind]
    result = await session.execute(
        text(
            f"""
            UPDATE {table}
            SET {column} = :url
            WHERE id = :source_id AND project_id = :project_id
              AND tenant_id = :tenant_id
            """
        ),
        {
            "url": image["url"],
            "source_id": source_id,
            "project_id": project_id,
            "tenant_id": tenant_id,
        },
    )
    if result.rowcount == 0:
        raise NotFoundError(f"{source_kind} not found")

    await session.execute(
        text(
            """
            UPDATE material_image
            SET source_kind = :source_kind, source_id = :source_id
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "source_kind": source_kind,
            "source_id": source_id,
            "id": image_id,
            "tenant_id": tenant_id,
        },
    )
    await session.commit()
    return {
        "image": _image_public(dict(image)),
        "source_kind": source_kind,
        "source_id": source_id,
        "current_url": image["url"],
    }
