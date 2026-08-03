"""项目知识库索引：从工作台 DB 生成可重建的检索副本。

工作台 DB 是唯一事实来源；知识库只存叙事空间 / 人物 / 场景的语义索引，
供检索与生成辅助，不替代 confirmed 资产与参考图。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import project_service
from framework.domain.errors import ValidationAppError
from framework.governance import vector_namespace_service

PROJECT_NS_PREFIX = "script/project/"


def project_namespace(project_id: str) -> str:
    return f"{PROJECT_NS_PREFIX}{project_id}"


def _space_document(space: dict[str, Any]) -> dict[str, Any]:
    ep = space.get("episode_no")
    ordinal = space.get("ordinal")
    title = (space.get("title") or "").strip() or "未命名空间"
    header = f"第{ep}集 空间{ordinal} {title}" if ep is not None else title
    parts = [
        header,
        f"地点：{space.get('time_place') or ''}",
        f"摘要：{space.get('summary') or ''}",
        f"节拍：{space.get('beat_type') or ''}",
        f"情绪：{space.get('mood') or ''}",
        f"正文：{(space.get('source_text') or '')[:4000]}",
    ]
    return {
        "text": "\n".join(parts),
        "metadata": {
            "doc_type": "narrative_space",
            "project_id": space["project_id"],
            "episode_id": space.get("episode_id") or "",
            "episode_no": int(ep) if ep is not None else 0,
            "narrative_space_id": space["id"],
            "space_ordinal": int(ordinal) if ordinal is not None else 0,
            "title": title,
            "time_place": space.get("time_place") or "",
            "beat_type": space.get("beat_type") or "",
            "mood": space.get("mood") or "",
            "scene_space_id": space.get("scene_space_id") or "",
            "record_status": space.get("record_status") or "ai",
            "source_updated_at": str(space.get("updated_at") or ""),
        },
    }


def _character_document(char: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    name = (char.get("name") or "").strip() or char.get("character_key") or "未命名"
    tags = char.get("personality_tags") or []
    if isinstance(tags, str):
        tags_text = tags
    elif isinstance(tags, list):
        tags_text = "、".join(str(t) for t in tags if t)
    else:
        tags_text = ""
    parts = [
        f"人物：{name}",
        f"角色键：{char.get('character_key') or ''}",
        f"外貌锚点：{char.get('appearance_anchor') or ''}",
        f"服装基线：{char.get('costume_baseline') or ''}",
        f"性格标签：{tags_text}",
    ]
    return {
        "text": "\n".join(p for p in parts if p.split("：", 1)[-1].strip()),
        "metadata": {
            "doc_type": "character",
            "project_id": project_id,
            "character_id": char["id"],
            "character_key": char.get("character_key") or "",
            "name": name,
            "record_status": char.get("record_status") or "ai",
            "source_updated_at": str(char.get("updated_at") or ""),
        },
    }


def _scene_document(scene: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    name = (scene.get("name") or "").strip() or scene.get("canonical_key") or "未命名场景"
    parts = [
        f"场景：{name}",
        f"场景键：{scene.get('canonical_key') or ''}",
        f"锚点：{scene.get('anchor') or ''}",
    ]
    return {
        "text": "\n".join(p for p in parts if p.split("：", 1)[-1].strip()),
        "metadata": {
            "doc_type": "scene_space",
            "project_id": project_id,
            "scene_space_id": scene["id"],
            "canonical_key": scene.get("canonical_key") or "",
            "name": name,
            "record_status": scene.get("record_status") or "ai",
            "has_reference_image": bool(scene.get("reference_image_url")),
            "source_updated_at": str(scene.get("updated_at") or ""),
        },
    }


async def _load_spaces(
    session: AsyncSession, tenant_id: str, project_id: str
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT ns.*, ep.ordinal AS episode_no
                FROM narrative_space ns
                JOIN episode ep ON ep.id = ns.episode_id
                WHERE ns.project_id = :project_id AND ns.tenant_id = :tenant_id
                ORDER BY ep.ordinal ASC, ns.ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _load_characters(
    session: AsyncSession, tenant_id: str, project_id: str
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM character_asset
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY name ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _load_scenes(
    session: AsyncSession, tenant_id: str, project_id: str
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT * FROM scene_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY name ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def index_project_knowledge(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """从工作台事实重建项目知识库索引（叙事空间 + 人物 + 场景）。"""
    await project_service.require_project(session, tenant_id, project_id)
    spaces = await _load_spaces(session, tenant_id, project_id)
    characters = await _load_characters(session, tenant_id, project_id)
    scenes = await _load_scenes(session, tenant_id, project_id)
    if not spaces and not characters and not scenes:
        raise ValidationAppError("项目无可索引内容（需叙事空间、人物或场景）")

    docs: list[dict[str, Any]] = []
    docs.extend(_space_document(s) for s in spaces)
    docs.extend(_character_document(c, project_id=project_id) for c in characters)
    docs.extend(_scene_document(s, project_id=project_id) for s in scenes)

    ns = project_namespace(project_id)
    result = await vector_namespace_service.replace_texts(
        session,
        tenant_id,
        namespace=ns,
        texts=docs,
        chunk_size=900,
        chunk_overlap=80,
    )
    return {
        "project_id": project_id,
        "namespace": ns,
        "indexed_spaces": len(spaces),
        "indexed_characters": len(characters),
        "indexed_scenes": len(scenes),
        "indexed_documents": len(docs),
        "chunk_count": result.get("chunk_count", 0),
        "role": "search_replica",
        "source_of_truth": "workspace_db",
    }


# 兼容旧入口名
async def index_narrative_spaces(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    return await index_project_knowledge(session, tenant_id, project_id)


async def index_project_narrative(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    return await index_project_knowledge(session, tenant_id, project_id)


async def get_project_knowledge_status(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """工作台事实计数 vs 知识库索引状态。"""
    await project_service.require_project(session, tenant_id, project_id)
    space_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM narrative_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]
    char_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM character_asset
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]
    scene_count = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM scene_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]

    ns = project_namespace(project_id)
    vector_row = await vector_namespace_service.get_namespace(
        session, tenant_id, namespace=ns
    )
    fact_total = int(space_count or 0) + int(char_count or 0) + int(scene_count or 0)
    indexed = bool(vector_row and int(vector_row.get("chunk_count") or 0) > 0)
    if fact_total == 0:
        status = "empty"
    elif not indexed:
        status = "not_indexed"
    else:
        status = "indexed"

    return {
        "project_id": project_id,
        "namespace": ns,
        "status": status,
        "source_of_truth": "workspace_db",
        "role": "search_replica",
        "workspace": {
            "narrative_space_count": int(space_count or 0),
            "character_count": int(char_count or 0),
            "scene_space_count": int(scene_count or 0),
            "fact_document_estimate": fact_total,
        },
        "index": {
            "chunk_count": int(vector_row["chunk_count"]) if vector_row else 0,
            "updated_at": vector_row.get("updated_at") if vector_row else None,
            "collection": vector_row.get("collection") if vector_row else None,
        },
        "craft_namespaces": [
            "script/craft/prompting",
            "script/craft/cinematography",
            "script/craft/visual-style",
            "script/craft/consistency",
        ],
    }


async def clear_project_knowledge(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """删除项目时清理向量副本；工作台事实由调用方删 DB。"""
    ns = project_namespace(project_id)
    cleared = await vector_namespace_service.clear_namespace(
        session, tenant_id, namespace=ns
    )
    return {"project_id": project_id, **cleared}
