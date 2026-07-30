"""视频片段：叙事空间内的成片生成单元，单段不超过模型上限。

叙事空间按语义切，长度不设限；能不能一次生成出来是模型的物理约束，
因此在这一层按分镜顺序累加时长分组，一组即一次生视频调用。
分组是机械约束，不进 LLM。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import (
    project_service,
    revision_service,
    shot_service,
    structure_parser,
)
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id

# 视频模型单次生成上限（秒）
MAX_SEGMENT_DURATION_SEC = 15.0


def _segment_public(row: dict[str, Any]) -> dict[str, Any]:
    shot_ids = row.get("shot_ids")
    if isinstance(shot_ids, str):
        shot_ids = json.loads(shot_ids)
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "narrative_space_id": row["narrative_space_id"],
        "ordinal": int(row["ordinal"]),
        "title": row["title"] or "",
        "summary": row.get("summary") or "",
        "shot_ids": shot_ids or [],
        "source_text": row.get("source_text") or "",
        "duration_sec": float(row["duration_sec"])
        if row.get("duration_sec") is not None
        else None,
        "status": row["status"],
        "record_status": row.get("record_status") or "ai",
    }


async def _require_space(
    session: AsyncSession, tenant_id: str, space_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM narrative_space
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("narrative space not found")
    return dict(row)


async def require_segment(
    session: AsyncSession, tenant_id: str, segment_id: str
) -> dict[str, Any]:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_segment
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("video segment not found")
    return dict(row)


async def list_segments(
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
                    SELECT * FROM video_segment
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                      AND narrative_space_id = :ns_id
                    ORDER BY ordinal ASC
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
                    SELECT * FROM video_segment
                    WHERE project_id = :project_id AND tenant_id = :tenant_id
                    ORDER BY narrative_space_id, ordinal ASC
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    items = [_segment_public(dict(r)) for r in rows]
    return {"items": items, "total": len(items)}


async def plan_segments_for_project(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    """为尚无确认片段、且已有分镜的叙事空间划分视频片段。"""
    await project_service.require_project(session, tenant_id, project_id)
    spaces = (
        await session.execute(
            text(
                """
                SELECT ns.id
                FROM narrative_space ns
                WHERE ns.project_id = :project_id AND ns.tenant_id = :tenant_id
                  AND EXISTS (
                    SELECT 1 FROM shot_plan sp
                    WHERE sp.narrative_space_id = ns.id
                      AND sp.tenant_id = :tenant_id
                  )
                  AND NOT EXISTS (
                    SELECT 1 FROM video_segment vs
                    WHERE vs.narrative_space_id = ns.id
                      AND vs.tenant_id = :tenant_id
                      AND vs.record_status = 'confirmed'
                  )
                ORDER BY ns.episode_id, ns.ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    results: list[dict[str, Any]] = []
    for space in spaces:
        results.append(
            await plan_segments_for_space(
                session, tenant_id, space["id"], commit=False
            )
        )
    await session.commit()
    return {
        "spaces": results,
        "space_count": len(results),
        "total": sum(int(r.get("total") or 0) for r in results),
    }


async def plan_segments_for_space(
    session: AsyncSession,
    tenant_id: str,
    narrative_space_id: str,
    *,
    commit: bool = True,
) -> dict:
    space = await _require_space(session, tenant_id, narrative_space_id)
    project_id = space["project_id"]

    confirmed = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM video_segment
                WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
                  AND record_status = 'confirmed'
                """
            ),
            {"ns_id": narrative_space_id, "tenant_id": tenant_id},
        )
    ).mappings().first()["c"]
    if int(confirmed or 0) > 0:
        raise ValidationAppError(
            "该叙事空间已有确认视频片段，请先反悔后再重新划分"
        )

    shots = (
        await shot_service.list_shots(
            session,
            tenant_id,
            project_id,
            narrative_space_id=narrative_space_id,
        )
    )["items"]
    if not shots:
        raise ValidationAppError("该叙事空间尚无分镜，请先规划分镜")

    # 片段重排会让旧提示词对不上镜头组，一并清掉 ai 提示词
    await session.execute(
        text(
            """
            DELETE FROM video_prompt
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": narrative_space_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM video_segment
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": narrative_space_id, "tenant_id": tenant_id},
    )

    groups = _group_shots(shots)
    space_title = space.get("title") or "叙事空间"
    created: list[dict[str, Any]] = []
    for ordinal, group in enumerate(groups, start=1):
        segment_id = new_id("svs")
        shot_ids = [s["id"] for s in group["shots"]]
        title = (
            space_title
            if len(groups) == 1
            else f"{space_title} 片段 {ordinal}"
        )
        await session.execute(
            text(
                """
                INSERT INTO video_segment
                  (id, tenant_id, project_id, narrative_space_id, ordinal,
                   title, summary, shot_ids, source_text, duration_sec,
                   status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :narrative_space_id, :ordinal,
                   :title, :summary, CAST(:shot_ids AS JSON), :source_text,
                   :duration_sec, 'draft', 'ai')
                """
            ),
            {
                "id": segment_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "narrative_space_id": narrative_space_id,
                "ordinal": ordinal,
                "title": title[:256],
                "summary": group["summary"],
                "shot_ids": json.dumps(shot_ids, ensure_ascii=False),
                "source_text": group["source_text"],
                "duration_sec": group["duration_sec"],
            },
        )
        created.append(
            {
                "id": segment_id,
                "ordinal": ordinal,
                "shot_count": len(shot_ids),
                "duration_sec": group["duration_sec"],
            }
        )

    if commit:
        await session.commit()
    return {
        "narrative_space_id": narrative_space_id,
        "items": created,
        "total": len(created),
    }


def _shot_duration(shot: dict[str, Any]) -> float:
    duration = shot.get("duration_sec")
    if duration is not None:
        try:
            value = float(duration)
        except (TypeError, ValueError):
            value = 0.0
        if value > 0:
            return value
    text_value = shot.get("scene_text") or shot.get("beat") or ""
    return structure_parser.estimate_duration_sec(text_value)


def _group_shots(shots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按分镜顺序累加时长分组，单组不超过模型上限。"""
    groups: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_sec = 0.0

    def flush() -> None:
        nonlocal current, current_sec
        if not current:
            return
        beats = [
            (s.get("beat") or s.get("scene_text") or "").strip() for s in current
        ]
        body = "\n".join(
            (s.get("scene_text") or s.get("beat") or "").strip() for s in current
        ).strip()
        groups.append(
            {
                "shots": current,
                "summary": " / ".join(b for b in beats if b)[:2000],
                "source_text": body,
                "duration_sec": round(min(current_sec, MAX_SEGMENT_DURATION_SEC), 2),
            }
        )
        current = []
        current_sec = 0.0

    for shot in shots:
        duration = _shot_duration(shot)
        # 单个分镜就超上限：独立成段，下游按上限截断
        if duration >= MAX_SEGMENT_DURATION_SEC:
            flush()
            current = [shot]
            current_sec = duration
            flush()
            continue
        if current and current_sec + duration > MAX_SEGMENT_DURATION_SEC:
            flush()
        current.append(shot)
        current_sec += duration
    flush()
    return groups


async def confirm_segment(
    session: AsyncSession,
    tenant_id: str,
    segment_id: str,
    *,
    created_by: str | None = None,
) -> dict:
    row = await require_segment(session, tenant_id, segment_id)
    public = _segment_public(row)
    if (row.get("record_status") or "ai") != "confirmed":
        await revision_service.save_revision(
            session,
            tenant_id=tenant_id,
            project_id=row["project_id"],
            target_type="video_segment",
            target_id=segment_id,
            snapshot=public,
            change_reason="pin",
            created_by=created_by,
        )
    await session.execute(
        text(
            """
            UPDATE video_segment
            SET record_status = 'confirmed', status = 'confirmed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": segment_id, "tenant_id": tenant_id},
    )
    await session.commit()
    refreshed = await require_segment(session, tenant_id, segment_id)
    return _segment_public(refreshed)
