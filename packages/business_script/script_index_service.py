"""剧本知识库索引：以叙事空间为条目粒度。

上传时按长度盲切会把一场戏拆散，检索回来的片段没有场次归属。
改为按叙事空间入库：一个空间一条，带集号 / 空间号 / 地点 / 节拍等 payload，
命中后能直接定位回具体场次，也能按集过滤。

前置：项目已完成结构切分。切分只是粗切还是 LLM 语义切分，本层不关心。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import project_service
from packages.domain.errors import ValidationAppError
from packages.governance import vector_namespace_service

# 叙事空间是语义完整的一场戏，切块粒度比通用语料大，尽量一条一块
_CHUNK_SIZE = 1500
_CHUNK_OVERLAP = 150


def project_namespace(project_id: str) -> str:
    return f"script/project/{project_id}"


def _build_entry(
    row: dict[str, Any], *, project_name: str
) -> dict[str, Any] | None:
    body = (row.get("source_text") or "").strip()
    if not body:
        return None
    episode_ordinal = int(row["episode_ordinal"])
    ordinal = int(row["ordinal"])
    title = (row.get("title") or "").strip()
    time_place = (row.get("time_place") or "").strip()
    summary = (row.get("summary") or "").strip()

    header = [f"# 第 {episode_ordinal} 集 · 叙事空间 {ordinal} {title}".strip()]
    if time_place:
        header.append(f"时空：{time_place}")
    if summary:
        header.append(f"梗概：{summary}")
    mood = (row.get("mood") or "").strip()
    if mood:
        header.append(f"氛围：{mood}")

    return {
        "text": "\n".join(header) + "\n\n" + body,
        "metadata": {
            "project_id": row["project_id"],
            "project_name": project_name,
            "episode_id": row["episode_id"],
            "episode_ordinal": episode_ordinal,
            "narrative_space_id": row["id"],
            "narrative_space_ordinal": ordinal,
            "title": title,
            "time_place": time_place,
            "beat_type": (row.get("beat_type") or "").strip(),
            "mood": mood,
            "segment_source": row.get("segment_source") or "rule",
            "estimated_duration_sec": float(row["estimated_duration_sec"])
            if row.get("estimated_duration_sec") is not None
            else None,
        },
    }


async def index_project_narrative(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """按叙事空间覆盖写入项目命名空间。"""
    project = await project_service.require_project(session, tenant_id, project_id)
    rows = (
        await session.execute(
            text(
                """
                SELECT ns.*, e.ordinal AS episode_ordinal
                FROM narrative_space ns
                JOIN episode e ON e.id = ns.episode_id
                WHERE ns.project_id = :project_id AND ns.tenant_id = :tenant_id
                ORDER BY e.ordinal ASC, ns.ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    if not rows:
        raise ValidationAppError("项目尚无叙事空间，请先完成结构切分")

    project_name = project.get("name") or ""
    entries = [
        entry
        for entry in (
            _build_entry(dict(r), project_name=project_name) for r in rows
        )
        if entry is not None
    ]
    if not entries:
        raise ValidationAppError("叙事空间均无正文，无法写入知识库")

    result = await vector_namespace_service.replace_texts(
        session,
        tenant_id,
        namespace=project_namespace(project_id),
        texts=entries,
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
    )
    return {
        "namespace": result["namespace"],
        "narrative_space_count": len(entries),
        "indexed": result["indexed"],
    }
