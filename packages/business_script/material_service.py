"""物料提示词生成与查询。

生成前注入工艺知识。
已 confirmed 的提示词不重生成；重跑只覆盖 record_status=ai 的版本。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import (
    consistency_context,
    knowledge_context,
    llm,
    parse_service,
    project_service,
)
from packages.domain.errors import NotFoundError, ValidationAppError
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
        "record_status": row.get("record_status") or "ai",
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
    if not assets["characters"] and not assets["props"]:
        raise ValidationAppError("项目无人物或道具资产，无法生成物料提示词")
    pack = await consistency_context.assemble_pack(
        session,
        tenant_id,
        project_id,
        include_craft=False,
    )
    style_bible = pack["style_bible"]

    craft = await knowledge_context.assemble_material_knowledge(tenant_id=tenant_id)
    system_base = llm.load_prompt("agents/asset-planner/prompts/system.md")
    system_prompt = system_base
    if craft:
        system_prompt = (
            system_base
            + "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n"
            + craft
        )
    system_prompt = (
        system_prompt + "\n\n" + pack["prompt_block"]
        + "\n\n只输出 JSON，不要 markdown 说明。"
    )

    # 已有 confirmed 提示词的目标跳过；ai 版本先删再生成
    confirmed_targets = {
        (r["target_type"], r["target_id"])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT target_type, target_id
                    FROM material_prompt
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND record_status = 'confirmed'
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    }
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

    char_tpl = llm.load_prompt("agents/asset-planner/prompts/material-character.md")
    prop_tpl = llm.load_prompt("agents/asset-planner/prompts/material-prop.md")
    created: list[dict[str, Any]] = []
    skipped = 0

    for character in assets["characters"]:
        if ("character", character["id"]) in confirmed_targets:
            skipped += 1
            continue
        user_prompt = llm.render_prompt(
            char_tpl,
            style_bible=style_bible,
            character=character,
        )
        data = await llm.chat_json(
            [
                {"role": "system", "content": system_prompt},
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
        if ("prop", prop["id"]) in confirmed_targets:
            skipped += 1
            continue
        user_prompt = llm.render_prompt(
            prop_tpl,
            style_bible=style_bible,
            prop=prop,
        )
        data = await llm.chat_json(
            [
                {"role": "system", "content": system_prompt},
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
    return {
        "items": created,
        "total": len(created),
        "skipped_confirmed": skipped,
    }


async def confirm_material_prompt(
    session: AsyncSession, tenant_id: str, project_id: str, prompt_id: str
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    result = await session.execute(
        text(
            """
            UPDATE material_prompt
            SET record_status = 'confirmed', status = 'confirmed'
            WHERE id = :id AND project_id = :project_id AND tenant_id = :tenant_id
            """
        ),
        {"id": prompt_id, "project_id": project_id, "tenant_id": tenant_id},
    )
    if result.rowcount == 0:
        raise NotFoundError("material prompt not found")
    await session.commit()
    row = (
        await session.execute(
            text("SELECT * FROM material_prompt WHERE id = :id"),
            {"id": prompt_id},
        )
    ).mappings().first()
    return _prompt_public(dict(row))


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
               negative_prompt, style_ref, version, status, record_status)
            VALUES
              (:id, :tenant_id, :project_id, :target_type, :target_id, :prompt_text,
               :negative_prompt, CAST(:style_ref AS JSON), :version, 'draft', 'ai')
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
