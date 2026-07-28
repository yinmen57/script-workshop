"""物料提示词生成与查询。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import llm, parse_service, project_service
from packages.domain.errors import ValidationAppError
from packages.domain.ids import new_id


def _prompt_public(row: dict[str, Any]) -> dict[str, Any]:
    style_ref = row.get("style_ref")
    if isinstance(style_ref, str):
        style_ref = json.loads(style_ref)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "target_type": row["target_type"],
        "target_id": row["target_id"],
        "prompt_text": row["prompt_text"],
        "negative_prompt": row.get("negative_prompt") or "",
        "style_ref": style_ref,
        "version": int(row["version"]),
        "status": row["status"],
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


async def list_material_prompts(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM material_prompt
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY target_type, target_id, version DESC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    return {"items": [_prompt_public(dict(r)) for r in rows], "total": len(rows)}


async def generate_material_prompts(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    assets = await parse_service.get_assets(session, tenant_id, project_id)
    project = assets["project"]
    style_bible = project.get("style_bible")
    if not style_bible:
        raise ValidationAppError("项目尚未解析，缺少 style_bible")
    if not assets["characters"] and not assets["props"]:
        raise ValidationAppError("项目无人物或道具资产，无法生成物料提示词")

    char_tpl = llm.load_prompt("agents/asset-planner/prompts/material-character.md")
    prop_tpl = llm.load_prompt("agents/asset-planner/prompts/material-prop.md")
    created: list[dict[str, Any]] = []

    for character in assets["characters"]:
        user_prompt = llm.render_prompt(
            char_tpl, style_bible=style_bible, character=character
        )
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是物料提示词生成器。只输出 JSON。",
                },
                {"role": "user", "content": user_prompt},
            ]
        )
        created.append(
            await _insert_prompt(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                target_type="character",
                target_id=character["id"],
                prompt_text=(data.get("prompt_text") or "").strip(),
                negative_prompt=(data.get("negative_prompt") or "").strip(),
                style_ref=style_bible,
            )
        )

    for prop in assets["props"]:
        user_prompt = llm.render_prompt(prop_tpl, style_bible=style_bible, prop=prop)
        data = await llm.chat_json(
            [
                {
                    "role": "system",
                    "content": "你是物料提示词生成器。只输出 JSON。",
                },
                {"role": "user", "content": user_prompt},
            ]
        )
        created.append(
            await _insert_prompt(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                target_type="prop",
                target_id=prop["id"],
                prompt_text=(data.get("prompt_text") or "").strip(),
                negative_prompt=(data.get("negative_prompt") or "").strip(),
                style_ref=style_bible,
            )
        )

    await session.commit()
    return {"items": created, "total": len(created)}


async def _insert_prompt(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    target_type: str,
    target_id: str,
    prompt_text: str,
    negative_prompt: str,
    style_ref: dict[str, Any],
) -> dict:
    if not prompt_text:
        raise ValidationAppError(f"{target_type}/{target_id} 未生成 prompt_text")
    version = (
        await session.execute(
            text(
                """
                SELECT COALESCE(MAX(version), 0) + 1 AS next_version
                FROM material_prompt
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                  AND target_type = :target_type AND target_id = :target_id
                """
            ),
            {
                "project_id": project_id,
                "tenant_id": tenant_id,
                "target_type": target_type,
                "target_id": target_id,
            },
        )
    ).mappings().first()["next_version"]
    prompt_id = new_id("smp")
    await session.execute(
        text(
            """
            INSERT INTO material_prompt
              (id, tenant_id, project_id, target_type, target_id, prompt_text,
               negative_prompt, style_ref, version, status)
            VALUES
              (:id, :tenant_id, :project_id, :target_type, :target_id, :prompt_text,
               :negative_prompt, CAST(:style_ref AS JSON), :version, 'draft')
            """
        ),
        {
            "id": prompt_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "target_type": target_type,
            "target_id": target_id,
            "prompt_text": prompt_text,
            "negative_prompt": negative_prompt,
            "style_ref": json.dumps(style_ref, ensure_ascii=False),
            "version": int(version),
        },
    )
    row = (
        await session.execute(
            text("SELECT * FROM material_prompt WHERE id = :id"),
            {"id": prompt_id},
        )
    ).mappings().first()
    return _prompt_public(dict(row))
