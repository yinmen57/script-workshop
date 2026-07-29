"""剧本项目与剧本文档。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id


def _json_load(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _project_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "status": row["status"],
        "style_bible": _json_load(row.get("style_bible")),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


def _document_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "version": int(row["version"]),
        "parse_status": row["parse_status"],
        "parse_result": _json_load(row.get("parse_result")),
        "source_filename": row.get("source_filename"),
        "source_format": row.get("source_format"),
        "source_uri": row.get("source_uri"),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


async def create_project(session: AsyncSession, tenant_id: str, payload: dict) -> dict:
    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationAppError("name required")
    project_id = new_id("sprj")
    await session.execute(
        text(
            """
            INSERT INTO script_project
              (id, tenant_id, name, status, style_bible)
            VALUES
              (:id, :tenant_id, :name, :status, :style_bible)
            """
        ),
        {
            "id": project_id,
            "tenant_id": tenant_id,
            "name": name,
            "status": "draft",
            "style_bible": None,
        },
    )
    await session.commit()
    return await get_project(session, tenant_id, project_id)


async def list_projects(session: AsyncSession, tenant_id: str) -> dict:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM script_project
                WHERE tenant_id = :tenant_id
                ORDER BY updated_at DESC
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    return {"items": [_project_public(dict(r)) for r in rows], "total": len(rows)}


async def get_project(session: AsyncSession, tenant_id: str, project_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM script_project
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("script project not found")
    return _project_public(dict(row))


async def require_project(session: AsyncSession, tenant_id: str, project_id: str) -> dict:
    return await get_project(session, tenant_id, project_id)


async def add_script(
    session: AsyncSession, tenant_id: str, project_id: str, payload: dict
) -> dict:
    await require_project(session, tenant_id, project_id)
    raw_text = (payload.get("raw_text") or payload.get("script_text") or "").strip()
    if not raw_text:
        raise ValidationAppError("raw_text required")
    title = (payload.get("title") or "").strip() or "未命名剧本"
    version = (
        await session.execute(
            text(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM script_document
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["next_version"]
    doc_id = (payload.get("id") or "").strip() or new_id("sdoc")
    await session.execute(
        text(
            """
            INSERT INTO script_document
              (id, tenant_id, project_id, title, raw_text, version, parse_status,
               source_filename, source_format, source_uri)
            VALUES
              (:id, :tenant_id, :project_id, :title, :raw_text, :version, 'pending',
               :source_filename, :source_format, :source_uri)
            """
        ),
        {
            "id": doc_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "title": title,
            "raw_text": raw_text,
            "version": int(version),
            "source_filename": payload.get("source_filename"),
            "source_format": payload.get("source_format"),
            "source_uri": payload.get("source_uri"),
        },
    )
    await session.commit()
    return await get_document(session, tenant_id, doc_id)


async def get_document(session: AsyncSession, tenant_id: str, document_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM script_document
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": document_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("script document not found")
    return _document_public(dict(row))


async def latest_document(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict | None:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM script_document
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    return _document_public(dict(row)) if row else None


async def list_documents(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    await require_project(session, tenant_id, project_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT id, tenant_id, project_id, title, version, parse_status,
                       source_filename, source_format, source_uri,
                       created_at, updated_at,
                       LEFT(raw_text, 200) AS raw_text
                FROM script_document
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY version DESC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    items = []
    for row in rows:
        item = _document_public(dict(row))
        item.pop("parse_result", None)
        items.append(item)
    return {"items": items, "total": len(items)}
