"""视频片段：叙事空间内的成片生成单元，单段不超过模型上限。

叙事空间按语义切，长度不设限；能不能一次生成出来是模型的物理约束。
片段边界由 LLM 按分镜内容判定：哪几个连续分镜是一次运镜能连贯拍完的，
就编成一个片段。时长上限只作硬校验，不用来机械累加分组。
LLM 只回答镜号区间，正文与时长由服务端按镜号重算。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import (
    knowledge_context,
    llm,
    project_service,
    revision_service,
    shot_service,
    structure_parser,
)
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id

# 视频模型单次生成上限（秒）
MAX_SEGMENT_DURATION_SEC = 15.0
# 逐空间并发编组的上限，避免打爆 LLM 网关
_MAX_CONCURRENCY = 4
# 浮点累加误差容忍
_DURATION_EPSILON = 0.01


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
    if not spaces:
        return {"spaces": [], "space_count": 0, "total": 0}

    prepared: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for row in spaces:
        prepared.append(await _prepare_space(session, tenant_id, row["id"]))

    system_prompt, template = await _load_prompts(tenant_id)
    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def run_space(
        space: dict[str, Any], shots: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        async with semaphore:
            return await _group_shots_by_llm(
                space, shots, system_prompt=system_prompt, template=template
            )

    grouped = await asyncio.gather(
        *(run_space(space, shots) for space, shots in prepared)
    )
    results: list[dict[str, Any]] = []
    for (space, _), groups in zip(prepared, grouped, strict=True):
        results.append(
            await _persist_groups(session, tenant_id, space, groups)
        )
    await session.commit()
    return {
        "spaces": results,
        "space_count": len(results),
        "total": sum(int(r.get("total") or 0) for r in results),
    }


async def plan_segments_for_space(
    session: AsyncSession, tenant_id: str, narrative_space_id: str
) -> dict:
    space, shots = await _prepare_space(session, tenant_id, narrative_space_id)
    system_prompt, template = await _load_prompts(tenant_id)
    groups = await _group_shots_by_llm(
        space, shots, system_prompt=system_prompt, template=template
    )
    result = await _persist_groups(session, tenant_id, space, groups)
    await session.commit()
    return result


async def _prepare_space(
    session: AsyncSession, tenant_id: str, narrative_space_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """取出叙事空间与其分镜，并挡住已确认片段的重排。"""
    space = await _require_space(session, tenant_id, narrative_space_id)

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
            space["project_id"],
            narrative_space_id=narrative_space_id,
        )
    )["items"]
    if not shots:
        raise ValidationAppError("该叙事空间尚无分镜，请先规划分镜")
    return space, shots


async def _persist_groups(
    session: AsyncSession,
    tenant_id: str,
    space: dict[str, Any],
    groups: list[dict[str, Any]],
) -> dict:
    narrative_space_id = space["id"]
    project_id = space["project_id"]

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

    space_title = space.get("title") or "叙事空间"
    created: list[dict[str, Any]] = []
    for ordinal, group in enumerate(groups, start=1):
        segment_id = new_id("svs")
        shot_ids = [s["id"] for s in group["shots"]]
        title = group["title"] or (
            space_title if len(groups) == 1 else f"{space_title} 片段 {ordinal}"
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


async def _load_prompts(tenant_id: str) -> tuple[str, str]:
    """编组用的 system / user 模板，附带检索到的镜头组工艺规范。"""
    craft = await knowledge_context.assemble_video_knowledge(tenant_id=tenant_id)
    system_prompt = llm.load_prompt("shot-planner/system.md")
    if craft:
        system_prompt += (
            "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n" + craft
        )
    system_prompt += "\n\n只输出 JSON，不要 markdown 说明。"
    template = llm.load_prompt("shot-planner/group-video-segments.md")
    return system_prompt, template


async def _group_shots_by_llm(
    space: dict[str, Any],
    shots: list[dict[str, Any]],
    *,
    system_prompt: str,
    template: str,
) -> list[dict[str, Any]]:
    """让 LLM 按分镜内容判定片段边界，只接受镜号区间。"""
    user_prompt = llm.render_prompt(
        template,
        narrative_space={
            "id": space["id"],
            "title": space.get("title") or "",
            "summary": space.get("summary") or "",
            "time_place": space.get("time_place") or "",
            "beat_type": space.get("beat_type") or "",
            "mood": space.get("mood") or "",
        },
        shots=[
            {
                "no": i,
                "beat": shot.get("beat") or "",
                "scene_text": shot.get("scene_text") or "",
                "camera": shot.get("camera"),
                "duration_sec": round(_shot_duration(shot), 2),
            }
            for i, shot in enumerate(shots, start=1)
        ],
        shot_count=len(shots),
        max_duration=MAX_SEGMENT_DURATION_SEC,
    )
    data = await llm.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return _build_groups(data, space=space, shots=shots)


def _build_groups(
    data: dict[str, Any],
    *,
    space: dict[str, Any],
    shots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验 LLM 镜号区间并按镜号重组片段；不合法直接失败，不做兜底分组。"""
    raw = data.get("segments")
    if not isinstance(raw, list) or not raw:
        raise ValidationAppError(
            f"叙事空间 {space['id']} 的视频片段编组结果为空"
        )

    total = len(shots)
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        start = _to_int(entry.get("start_shot"))
        end = _to_int(entry.get("end_shot"))
        if start is None or end is None:
            raise ValidationAppError(
                f"叙事空间 {space['id']} 的片段编组缺少镜号"
            )
        if start < 1 or end > total or start > end:
            raise ValidationAppError(
                f"叙事空间 {space['id']} 片段镜号越界：{start}-{end}，共 {total} 镜"
            )
        items.append({**entry, "start": start, "end": end})

    items.sort(key=lambda x: x["start"])
    cursor = 0
    for item in items:
        if item["start"] != cursor + 1:
            raise ValidationAppError(
                f"叙事空间 {space['id']} 片段镜号不连续：第 {cursor + 1} 镜未被覆盖"
            )
        cursor = item["end"]
    if cursor != total:
        raise ValidationAppError(
            f"叙事空间 {space['id']} 片段镜号未覆盖到结尾：止于第 {cursor} 镜，共 {total} 镜"
        )

    groups: list[dict[str, Any]] = []
    for item in items:
        members = shots[item["start"] - 1 : item["end"]]
        duration = sum(_shot_duration(s) for s in members)
        # 单镜本身超上限只能独立成段，由下游按上限截断；多镜超上限说明编组无效
        if duration > MAX_SEGMENT_DURATION_SEC + _DURATION_EPSILON and len(members) > 1:
            raise ValidationAppError(
                f"叙事空间 {space['id']} 第 {item['start']}-{item['end']} 镜合计 "
                f"{duration:.1f} 秒，超过单段上限 {MAX_SEGMENT_DURATION_SEC:.0f} 秒"
            )
        body = "\n".join(
            (s.get("scene_text") or s.get("beat") or "").strip() for s in members
        ).strip()
        summary = (item.get("summary") or "").strip()
        if not summary:
            beats = [
                (s.get("beat") or s.get("scene_text") or "").strip() for s in members
            ]
            summary = " / ".join(b for b in beats if b)
        groups.append(
            {
                "shots": members,
                "title": (item.get("title") or "").strip()[:256],
                "summary": summary[:2000],
                "group_reason": (item.get("group_reason") or "").strip(),
                "source_text": body,
                "duration_sec": round(
                    min(duration, MAX_SEGMENT_DURATION_SEC), 2
                ),
            }
        )
    return groups


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
