"""剧本解析：落文档、调 Chat、沉淀人物与道具资产。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import keys, llm, project_service
from packages.domain.errors import ValidationAppError
from packages.domain.ids import new_id

_VALID_CONTENT_TYPES = {"narration_comic", "commerce"}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


async def parse_project(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    script_text: str | None = None,
    title: str | None = None,
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)

    if script_text and script_text.strip():
        doc = await project_service.add_script(
            session,
            tenant_id,
            project_id,
            {"raw_text": script_text, "title": title or "未命名剧本"},
        )
    else:
        doc = await project_service.latest_document(session, tenant_id, project_id)
        if doc is None:
            raise ValidationAppError("项目尚无剧本文档，请先上传或传入 script_text")

    await session.execute(
        text(
            """
            UPDATE script_document
            SET parse_status = 'running', parse_result = NULL
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": doc["id"], "tenant_id": tenant_id},
    )
    await session.commit()

    template = llm.load_prompt("agents/parser/prompts/parse-script.md")
    user_prompt = llm.render_prompt(template, script_text=doc["raw_text"])
    try:
        parsed = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "你是剧本解析器。只输出符合 schema 的 JSON，"
                        "不要 markdown 说明，不要额外字段。"
                    ),
                },
                {"role": "user", "content": user_prompt},
            ]
        )
        result = await _persist_parse(
            session, tenant_id, project_id, doc["id"], parsed
        )
    except Exception as exc:  # noqa: BLE001
        await session.execute(
            text(
                """
                UPDATE script_document
                SET parse_status = 'failed',
                    parse_result = CAST(:parse_result AS JSON)
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {
                "id": doc["id"],
                "tenant_id": tenant_id,
                "parse_result": json.dumps(
                    {"error": str(exc)}, ensure_ascii=False
                ),
            },
        )
        await session.commit()
        raise

    return result


async def _persist_parse(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    document_id: str,
    parsed: dict[str, Any],
) -> dict:
    content_type = parsed.get("content_type")
    if content_type not in _VALID_CONTENT_TYPES:
        raise ValidationAppError("content_type 必须是 narration_comic 或 commerce")
    style_bible = parsed.get("style_bible")
    if not isinstance(style_bible, dict):
        raise ValidationAppError("style_bible 必须是对象")

    characters = _as_list(parsed.get("characters"))
    props = _as_list(parsed.get("props"))
    scenes = _as_list(parsed.get("scenes"))

    # 同名人物合并
    char_by_key: dict[str, dict[str, Any]] = {}
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue
        ck = (item.get("character_key") or "").strip() or keys.character_key(name)
        existing = char_by_key.get(ck)
        if existing is None:
            char_by_key[ck] = {
                "name": name,
                "character_key": ck,
                "appearance_anchor": (item.get("appearance_anchor") or "").strip(),
                "costume_baseline": (item.get("costume_baseline") or "").strip(),
                "personality_tags": item.get("personality_tags") or [],
                "status": "ready",
            }
        else:
            if len((item.get("appearance_anchor") or "")) > len(
                existing["appearance_anchor"]
            ):
                existing["appearance_anchor"] = (item.get("appearance_anchor") or "").strip()
            if len((item.get("costume_baseline") or "")) > len(
                existing.get("costume_baseline") or ""
            ):
                existing["costume_baseline"] = (item.get("costume_baseline") or "").strip()

    # 清空旧资产后按本次解析重建（B0：以最新解析为准）
    await session.execute(
        text(
            "DELETE FROM material_prompt WHERE project_id = :project_id AND tenant_id = :tenant_id"
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            "DELETE FROM prop_asset WHERE project_id = :project_id AND tenant_id = :tenant_id"
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            "DELETE FROM character_asset WHERE project_id = :project_id AND tenant_id = :tenant_id"
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )

    char_id_by_key: dict[str, str] = {}
    for item in char_by_key.values():
        if not item["appearance_anchor"]:
            item["appearance_anchor"] = item["name"]
        cid = new_id("schar")
        char_id_by_key[item["character_key"]] = cid
        await session.execute(
            text(
                """
                INSERT INTO character_asset
                  (id, tenant_id, project_id, name, character_key, appearance_anchor,
                   costume_baseline, personality_tags, status)
                VALUES
                  (:id, :tenant_id, :project_id, :name, :character_key, :appearance_anchor,
                   :costume_baseline, CAST(:personality_tags AS JSON), :status)
                """
            ),
            {
                "id": cid,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "name": item["name"],
                "character_key": item["character_key"],
                "appearance_anchor": item["appearance_anchor"],
                "costume_baseline": item.get("costume_baseline") or "",
                "personality_tags": json.dumps(
                    item.get("personality_tags") or [], ensure_ascii=False
                ),
                "status": item["status"],
            },
        )

    prop_by_key: dict[str, dict[str, Any]] = {}
    for item in props:
        if not isinstance(item, dict):
            continue
        prop_name = (item.get("name") or item.get("prop_name") or "").strip()
        prop_type = (item.get("prop_type") or "prop").strip() or "prop"
        if not prop_name:
            continue
        owner_name = item.get("owner_name")
        owner_name = owner_name.strip() if isinstance(owner_name, str) else None
        owner_key = keys.character_key(owner_name) if owner_name else None
        owner_id = char_id_by_key.get(owner_key) if owner_key else None
        status = (item.get("status") or "ready").strip()
        if owner_name and owner_id is None:
            status = "needs_review"
            owner_key = None
        pk = (item.get("prop_key") or "").strip() or keys.prop_key(
            owner_key, prop_type, prop_name
        )
        visual = (item.get("visual_anchor") or "").strip() or prop_name
        scope = (item.get("scope") or ("owned" if owner_id else "scene")).strip()
        existing = prop_by_key.get(pk)
        if existing is None or len(visual) > len(existing["visual_anchor"]):
            prop_by_key[pk] = {
                "prop_key": pk,
                "prop_type": prop_type,
                "prop_name": prop_name,
                "visual_anchor": visual,
                "owner_character_id": owner_id,
                "scope": scope,
                "status": status,
            }

    for item in prop_by_key.values():
        await session.execute(
            text(
                """
                INSERT INTO prop_asset
                  (id, tenant_id, project_id, owner_character_id, prop_key, prop_type,
                   prop_name, visual_anchor, scope, status)
                VALUES
                  (:id, :tenant_id, :project_id, :owner_character_id, :prop_key, :prop_type,
                   :prop_name, :visual_anchor, :scope, :status)
                """
            ),
            {
                "id": new_id("sprop"),
                "tenant_id": tenant_id,
                "project_id": project_id,
                "owner_character_id": item["owner_character_id"],
                "prop_key": item["prop_key"],
                "prop_type": item["prop_type"],
                "prop_name": item["prop_name"],
                "visual_anchor": item["visual_anchor"],
                "scope": item["scope"],
                "status": item["status"],
            },
        )

    await session.execute(
        text(
            """
            UPDATE script_project
            SET content_type = :content_type,
                style_bible = CAST(:style_bible AS JSON),
                status = 'parsed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "id": project_id,
            "tenant_id": tenant_id,
            "content_type": content_type,
            "style_bible": json.dumps(style_bible, ensure_ascii=False),
        },
    )
    await session.execute(
        text(
            """
            UPDATE script_document
            SET parse_status = 'succeeded',
                parse_result = CAST(:parse_result AS JSON)
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "id": document_id,
            "tenant_id": tenant_id,
            "parse_result": json.dumps(
                {
                    "content_type": content_type,
                    "style_bible": style_bible,
                    "characters": list(char_by_key.values()),
                    "props": list(prop_by_key.values()),
                    "scenes": scenes,
                },
                ensure_ascii=False,
            ),
        },
    )
    await session.commit()
    return await get_assets(session, tenant_id, project_id)


async def get_assets(session: AsyncSession, tenant_id: str, project_id: str) -> dict:
    project = await project_service.require_project(session, tenant_id, project_id)
    chars = (
        await session.execute(
            text(
                """
                SELECT * FROM character_asset
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY created_at ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    props = (
        await session.execute(
            text(
                """
                SELECT p.*, c.name AS owner_name
                FROM prop_asset p
                LEFT JOIN character_asset c ON c.id = p.owner_character_id
                WHERE p.project_id = :project_id AND p.tenant_id = :tenant_id
                ORDER BY p.created_at ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    doc = await project_service.latest_document(session, tenant_id, project_id)
    return {
        "project": project,
        "document": doc,
        "characters": [
            {
                "id": r["id"],
                "name": r["name"],
                "character_key": r["character_key"],
                "appearance_anchor": r["appearance_anchor"],
                "costume_baseline": r.get("costume_baseline") or "",
                "personality_tags": json.loads(r["personality_tags"])
                if isinstance(r.get("personality_tags"), str)
                else (r.get("personality_tags") or []),
                "status": r["status"],
            }
            for r in chars
        ],
        "props": [
            {
                "id": r["id"],
                "prop_key": r["prop_key"],
                "prop_type": r["prop_type"],
                "prop_name": r["prop_name"],
                "visual_anchor": r["visual_anchor"],
                "owner_character_id": r.get("owner_character_id"),
                "owner_name": r.get("owner_name"),
                "scope": r["scope"],
                "status": r["status"],
            }
            for r in props
        ],
    }
