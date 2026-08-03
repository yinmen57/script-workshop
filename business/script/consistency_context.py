"""ConsistencyPack：生成前从工作台事实组装一致性上下文。

事实顺序：style_bible / character_asset / scene_space / costume_change /
参考图指针（DB） > 工艺规范（知识库）。知识库不替代资产主库。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import knowledge_context, parse_service, project_service
from framework.domain.errors import ValidationAppError


async def _load_scene_space(
    session: AsyncSession,
    tenant_id: str,
    scene_space_id: str | None,
) -> dict[str, Any] | None:
    if not scene_space_id:
        return None
    row = (
        await session.execute(
            text(
                """
                SELECT id, name, canonical_key, anchor, reference_image_url, record_status
                FROM scene_space
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": scene_space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "canonical_key": row["canonical_key"],
        "anchor": row.get("anchor") or "",
        "reference_image_url": row.get("reference_image_url"),
        "record_status": row.get("record_status") or "ai",
    }


async def _load_costume_changes(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
    character_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    conditions = [
        "project_id = :project_id",
        "tenant_id = :tenant_id",
    ]
    params: dict[str, Any] = {"project_id": project_id, "tenant_id": tenant_id}
    if narrative_space_id:
        conditions.append(
            "(narrative_space_id = :ns_id OR narrative_space_id IS NULL OR series_wide = 1)"
        )
        params["ns_id"] = narrative_space_id
    if character_ids:
        placeholders = ", ".join(f":cid{i}" for i in range(len(character_ids)))
        conditions.append(f"character_id IN ({placeholders})")
        for i, cid in enumerate(character_ids):
            params[f"cid{i}"] = cid
    rows = (
        await session.execute(
            text(
                f"""
                SELECT id, character_id, episode_id, narrative_space_id, description,
                       change_point, image_url, series_wide, record_status
                FROM costume_change
                WHERE {" AND ".join(conditions)}
                ORDER BY series_wide DESC, updated_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "character_id": r["character_id"],
            "episode_id": r.get("episode_id"),
            "narrative_space_id": r.get("narrative_space_id"),
            "description": r["description"],
            "change_point": r.get("change_point") or "",
            "image_url": r.get("image_url"),
            "series_wide": int(r.get("series_wide") or 0),
            "record_status": r.get("record_status") or "ai",
        }
        for r in rows
    ]


async def _load_reference_images(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    character_ids: list[str],
    scene_space_id: str | None,
) -> list[dict[str, Any]]:
    """取人物 / 场景当前关联的物料图指针（最新优先）。"""
    refs: list[dict[str, Any]] = []
    for cid in character_ids:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, url, label, source_kind, source_id, record_status
                    FROM material_image
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND source_kind = 'character' AND source_id = :source_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "source_id": cid,
                },
            )
        ).mappings().first()
        if row:
            refs.append(
                {
                    "image_id": row["id"],
                    "url": row["url"],
                    "label": row.get("label") or "",
                    "target_type": "character",
                    "target_id": cid,
                    "record_status": row.get("record_status") or "ai",
                }
            )
    if scene_space_id:
        row = (
            await session.execute(
                text(
                    """
                    SELECT id, url, label, source_kind, source_id, record_status
                    FROM material_image
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND source_kind = 'scene_space' AND source_id = :source_id
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                ),
                {
                    "project_id": project_id,
                    "tenant_id": tenant_id,
                    "source_id": scene_space_id,
                },
            )
        ).mappings().first()
        if row:
            refs.append(
                {
                    "image_id": row["id"],
                    "url": row["url"],
                    "label": row.get("label") or "",
                    "target_type": "scene_space",
                    "target_id": scene_space_id,
                    "record_status": row.get("record_status") or "ai",
                }
            )
    return refs


def format_pack_for_prompt(pack: dict[str, Any], *, max_chars: int = 8000) -> str:
    """把 ConsistencyPack 压成可注入 system/user 的文本。"""
    lines = [
        "## ConsistencyPack（工作台事实，冲突时以此为准）",
        f"- source_of_truth: {pack.get('source_of_truth')}",
        f"- project_id: {pack.get('project_id')}",
    ]
    style = pack.get("style_bible")
    if style:
        lines.append("### style_bible")
        lines.append(json.dumps(style, ensure_ascii=False, indent=2)[:2000])

    scene = pack.get("scene_space")
    if scene:
        lines.append("### scene_space")
        lines.append(
            json.dumps(scene, ensure_ascii=False, indent=2)[:1200]
        )

    chars = pack.get("characters") or []
    if chars:
        lines.append("### characters")
        lines.append(json.dumps(chars, ensure_ascii=False, indent=2)[:3000])

    props = pack.get("props") or []
    if props:
        lines.append("### props")
        lines.append(json.dumps(props, ensure_ascii=False, indent=2)[:1500])

    costumes = pack.get("costume_changes") or []
    if costumes:
        lines.append("### costume_changes")
        lines.append(json.dumps(costumes, ensure_ascii=False, indent=2)[:1500])

    refs = pack.get("reference_images") or []
    if refs:
        lines.append("### reference_images")
        lines.append(json.dumps(refs, ensure_ascii=False, indent=2)[:1200])

    rules = pack.get("craft_rules") or ""
    if rules:
        lines.append("### craft_rules（规范检索，不可覆盖上方事实）")
        lines.append(rules)

    text_out = "\n".join(lines)
    if len(text_out) > max_chars:
        return text_out[: max_chars - 1] + "…"
    return text_out


async def assemble_pack(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    *,
    narrative_space_id: str | None = None,
    character_ids: list[str] | None = None,
    include_props: bool = True,
    include_craft: bool = True,
    craft_query: str = "人物一致性 场景一致性 风格锁定 参考图",
) -> dict[str, Any]:
    """组装 ConsistencyPack。

    narrative_space_id 可选：有则带上该空间绑定的 scene_space 与局部服装变化。
    character_ids 可选：有则只保留指定人物；无则全量人物。
    """
    project = await project_service.require_project(session, tenant_id, project_id)
    style_bible = project.get("style_bible")
    if not style_bible:
        raise ValidationAppError("项目尚未解析，缺少 style_bible")

    assets = await parse_service.get_assets(session, tenant_id, project_id)
    characters = assets["characters"]
    props = assets["props"] if include_props else []
    if character_ids is not None:
        allow = set(character_ids)
        characters = [c for c in characters if c["id"] in allow]
        props = [
            p
            for p in props
            if not p.get("owner_character_id") or p.get("owner_character_id") in allow
        ]

    scene_space_id: str | None = None
    if narrative_space_id:
        ns = (
            await session.execute(
                text(
                    """
                    SELECT scene_space_id FROM narrative_space
                    WHERE id = :id AND tenant_id = :tenant_id
                      AND project_id = :project_id
                    """
                ),
                {
                    "id": narrative_space_id,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                },
            )
        ).mappings().first()
        if ns:
            scene_space_id = ns.get("scene_space_id")

    scene = await _load_scene_space(session, tenant_id, scene_space_id)
    # 场景参考图优先用 scene_space.reference_image_url
    if scene and scene.get("reference_image_url") and not scene_space_id:
        pass

    char_ids = [c["id"] for c in characters]
    costumes = await _load_costume_changes(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
        character_ids=char_ids or None,
    )
    refs = await _load_reference_images(
        session,
        tenant_id,
        project_id,
        character_ids=char_ids,
        scene_space_id=scene_space_id,
    )
    if scene and scene.get("reference_image_url"):
        if not any(r.get("target_type") == "scene_space" for r in refs):
            refs.append(
                {
                    "image_id": None,
                    "url": scene["reference_image_url"],
                    "label": scene.get("name") or "",
                    "target_type": "scene_space",
                    "target_id": scene["id"],
                    "record_status": scene.get("record_status") or "ai",
                }
            )

    craft_rules = ""
    if include_craft:
        craft_rules = await knowledge_context.assemble_consistency_knowledge(
            tenant_id=tenant_id, query=craft_query
        )

    pack = {
        "project_id": project_id,
        "narrative_space_id": narrative_space_id,
        "source_of_truth": "workspace_db",
        "style_bible": style_bible,
        "scene_space": scene,
        "characters": characters,
        "props": props,
        "costume_changes": costumes,
        "reference_images": refs,
        "craft_rules": craft_rules,
    }
    pack["prompt_block"] = format_pack_for_prompt(pack)
    return pack
