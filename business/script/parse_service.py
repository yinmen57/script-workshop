"""剧本解析：规则切结构 + LLM 抽语义资产。

1. structure_parser 规则切集 / 叙事空间（D6），不进 LLM；
2. Chat 只抽 style_bible / 人物 / 道具；
重跑只清理 record_status=ai；confirmed 永不覆盖（D5）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import (
    keys,
    knowledge_context,
    llm,
    project_service,
    structure_service,
)
from framework.domain.errors import NotFoundError, ValidationAppError
from framework.domain.ids import new_id


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
    project = await project_service.require_project(session, tenant_id, project_id)

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

    try:
        # 先规则切结构并落库；LLM 失败时结构仍保留
        structure_bundle = await structure_service.parse_and_sync_structure(
            session, tenant_id, project_id, doc["raw_text"]
        )
        await session.commit()

        craft = await knowledge_context.assemble_parse_knowledge(tenant_id=tenant_id)
        system_prompt = llm.load_prompt("parser/system.md")
        if craft:
            system_prompt = (
                system_prompt
                + "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n"
                + craft
            )
        system_prompt += (
            "\n\n你必须只输出符合 parse-script 模板的 JSON，"
            "不要 markdown 说明，不要额外字段。"
            "不要输出 scenes：集与叙事空间已由规则解析完成。"
        )

        template = llm.load_prompt("parser/parse-script.md")
        # 超长剧本只把 preamble + 各集摘要与现身角色送给资产抽取，控制 token
        asset_text = _asset_extract_text(doc["raw_text"], structure_bundle)
        user_prompt = llm.render_prompt(template, script_text=asset_text)
        parsed = await llm.chat_json(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        result = await _persist_parse(
            session,
            tenant_id,
            project_id,
            doc["id"],
            parsed,
            structure_bundle=structure_bundle,
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


def _asset_extract_text(_raw_text: str, structure_bundle: dict[str, Any]) -> str:
    """为人物/道具抽取准备输入：preamble（含 Core Characters）+ 各集元数据与空间目录。"""
    parsed = (structure_bundle or {}).get("parsed") or {}
    parts: list[str] = []
    preamble = (parsed.get("preamble") or "").strip()
    if preamble:
        parts.append(preamble)
    for ep in parsed.get("episodes") or []:
        block = [
            f"剧集 [{ep.get('ordinal')}]",
            f"标题: {ep.get('title') or ''}",
            f"现身角色: {ep.get('characters') or ''}",
            f"时间: {ep.get('time') or ''}",
            f"位置: {ep.get('location') or ''}",
            f"氛围: {ep.get('mood') or ''}",
            f"情节梗概: {ep.get('summary') or ''}",
            "叙事空间:",
        ]
        for ns in ep.get("narrative_spaces") or []:
            block.append(
                f"- {ns.get('ordinal')}: {ns.get('title')}"
                f" | {ns.get('time_place') or ''}"
                f" | 约 {ns.get('estimated_duration_sec') or '?'}s"
            )
            summary = (ns.get("summary") or "").strip()
            if summary:
                block.append(f"  摘要: {summary}")
        parts.append("\n".join(block))
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValidationAppError("结构解析结果为空，无法抽取人物与道具")
    return text


async def _persist_parse(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    document_id: str,
    parsed: dict[str, Any],
    *,
    structure_bundle: dict[str, Any],
) -> dict:
    style_bible = parsed.get("style_bible")
    if not isinstance(style_bible, dict):
        raise ValidationAppError("style_bible 必须是对象")

    characters = _as_list(parsed.get("characters"))
    props = _as_list(parsed.get("props"))

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
                existing["appearance_anchor"] = (
                    item.get("appearance_anchor") or ""
                ).strip()
            if len((item.get("costume_baseline") or "")) > len(
                existing.get("costume_baseline") or ""
            ):
                existing["costume_baseline"] = (
                    item.get("costume_baseline") or ""
                ).strip()

    # D5：只删 AI 产物；confirmed 资产与其物料提示词保留
    await session.execute(
        text(
            """
            DELETE FROM material_prompt
            WHERE project_id = :project_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM prop_asset
            WHERE project_id = :project_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    # 仍被 confirmed 道具引用的人物即使是 ai 也不删，避免孤儿引用
    await session.execute(
        text(
            """
            DELETE FROM character_asset
            WHERE project_id = :project_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
              AND id NOT IN (
                SELECT owner_character_id FROM (
                  SELECT owner_character_id FROM prop_asset
                  WHERE project_id = :project_id AND tenant_id = :tenant_id
                    AND record_status = 'confirmed'
                    AND owner_character_id IS NOT NULL
                ) AS keep_owners
              )
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )

    confirmed_chars = (
        await session.execute(
            text(
                """
                SELECT id, character_key FROM character_asset
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                  AND record_status = 'confirmed'
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    char_id_by_key: dict[str, str] = {
        r["character_key"]: r["id"] for r in confirmed_chars
    }

    for item in char_by_key.values():
        if item["character_key"] in char_id_by_key:
            # confirmed 人物跳过，不覆盖
            continue
        if not item["appearance_anchor"]:
            item["appearance_anchor"] = item["name"]
        cid = new_id("schar")
        char_id_by_key[item["character_key"]] = cid
        await session.execute(
            text(
                """
                INSERT INTO character_asset
                  (id, tenant_id, project_id, name, character_key, appearance_anchor,
                   costume_baseline, personality_tags, status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :name, :character_key, :appearance_anchor,
                   :costume_baseline, CAST(:personality_tags AS JSON), :status, 'ai')
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

    confirmed_prop_keys = {
        r["prop_key"]
        for r in (
            await session.execute(
                text(
                    """
                    SELECT prop_key FROM prop_asset
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND record_status = 'confirmed'
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    }

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
        if pk in confirmed_prop_keys:
            continue
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
                   prop_name, visual_anchor, scope, status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :owner_character_id, :prop_key, :prop_type,
                   :prop_name, :visual_anchor, :scope, :status, 'ai')
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
            SET style_bible = CAST(:style_bible AS JSON),
                status = 'parsed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "id": project_id,
            "tenant_id": tenant_id,
            "style_bible": json.dumps(style_bible, ensure_ascii=False),
        },
    )
    structure = structure_bundle.get("structure") or await structure_service.list_structure(
        session, tenant_id, project_id
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
                    "style_bible": style_bible,
                    "characters": list(char_by_key.values()),
                    "props": list(prop_by_key.values()),
                    "structure_stats": structure_bundle.get("parsed"),
                    "structure": structure,
                },
                ensure_ascii=False,
            ),
        },
    )
    await session.commit()
    result = await get_assets(session, tenant_id, project_id)
    result["structure"] = structure
    result["structure_stats"] = structure_bundle.get("parsed")
    return result


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
                "record_status": r.get("record_status") or "ai",
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
                "record_status": r.get("record_status") or "ai",
            }
            for r in props
        ],
    }


async def confirm_asset(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    target_type: str,
    target_id: str,
) -> dict:
    """将人物或道具标记为人工确认，重解析不再覆盖。"""
    await project_service.require_project(session, tenant_id, project_id)
    if target_type == "character":
        table = "character_asset"
    elif target_type == "prop":
        table = "prop_asset"
    else:
        raise ValidationAppError("target_type 必须是 character 或 prop")

    result = await session.execute(
        text(
            f"""
            UPDATE {table}
            SET record_status = 'confirmed'
            WHERE id = :id AND project_id = :project_id AND tenant_id = :tenant_id
            """
        ),
        {"id": target_id, "project_id": project_id, "tenant_id": tenant_id},
    )
    if result.rowcount == 0:
        raise NotFoundError(f"{target_type} not found")
    await session.commit()
    return await get_assets(session, tenant_id, project_id)
