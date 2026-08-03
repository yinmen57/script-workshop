"""叙事空间语义切分：规则粗切 + LLM 判定边界。

规则解析器只按集标记与地点 / 转场信号给出粗切基线，字面信号常把一场戏切开
或把两场戏粘在一起。本服务逐集把编号段落交给 LLM，让它回答「哪里该断」，
并只接受段号，正文由服务端按段号重组，杜绝模型改写原文。

时长不参与本层切分：叙事空间是语义单元，成片切分由 video_segment_service 负责。
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from business.script import (
    knowledge_context,
    llm,
    project_service,
    structure_parser,
    structure_service,
)
from framework.domain.errors import ValidationAppError

# 逐集并发切分的上限，避免打爆 LLM 网关
_MAX_CONCURRENCY = 4
_BEAT_TYPES = {
    "hook",
    "setup",
    "escalation",
    "turn",
    "climax",
    "cliffhanger",
}


async def segment_and_sync(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    script_text: str,
) -> dict:
    """语义切分剧本结构并落库（复用 structure_service 的 ai / confirmed 保护）。"""
    await project_service.require_project(session, tenant_id, project_id)
    parsed = structure_parser.parse_script_structure(script_text)
    episodes = parsed.get("episodes") or []
    if not episodes:
        raise ValidationAppError("剧本未解析出任何集，无法语义切分")

    craft = await knowledge_context.assemble_segment_knowledge(tenant_id=tenant_id)
    system_prompt = llm.load_prompt("narrative-segmenter/system.md")
    if craft:
        system_prompt += (
            "\n\n以下是已检索到的工艺规范（硬性约束，冲突时以之为准）：\n" + craft
        )
    system_prompt += "\n\n只输出 JSON，不要 markdown 说明。"
    template = llm.load_prompt("narrative-segmenter/segment-episode.md")

    semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def run_episode(episode: dict[str, Any]) -> list[dict[str, Any]]:
        async with semaphore:
            return await _segment_episode(
                episode,
                system_prompt=system_prompt,
                template=template,
            )

    results = await asyncio.gather(
        *(run_episode(ep) for ep in episodes)
    )
    for episode, spaces in zip(episodes, results, strict=True):
        episode["narrative_spaces"] = spaces

    parsed["narrative_space_count"] = sum(
        len(ep.get("narrative_spaces") or []) for ep in episodes
    )
    sync_result = await structure_service.sync_from_parsed(
        session, tenant_id, project_id, parsed
    )
    await session.commit()
    return {
        "parsed": {
            "episode_count": parsed["episode_count"],
            "narrative_space_count": parsed["narrative_space_count"],
            "episodes": [
                {
                    "ordinal": ep["ordinal"],
                    "title": ep["title"],
                    "narrative_space_count": len(ep.get("narrative_spaces") or []),
                }
                for ep in episodes
            ],
        },
        "sync": sync_result,
        "structure": await structure_service.list_structure(
            session, tenant_id, project_id
        ),
    }


async def _segment_episode(
    episode: dict[str, Any],
    *,
    system_prompt: str,
    template: str,
) -> list[dict[str, Any]]:
    paragraphs: list[str] = list(episode.get("body_paragraphs") or [])
    rough: list[dict[str, Any]] = list(episode.get("narrative_spaces") or [])
    if not paragraphs:
        return rough

    user_prompt = llm.render_prompt(
        template,
        episode={
            "ordinal": episode["ordinal"],
            "title": episode.get("title") or "",
            "characters": episode.get("characters") or "",
            "summary": episode.get("summary") or "",
            "time": episode.get("time") or "",
            "location": episode.get("location") or "",
            "mood": episode.get("mood") or "",
        },
        rough_spaces=[
            {
                "ordinal": s.get("ordinal"),
                "title": s.get("title") or "",
                "location": s.get("location") or "",
                "paragraph_range": s.get("paragraph_range") or [],
            }
            for s in rough
        ],
        paragraphs=[
            {"no": i, "text": text}
            for i, text in enumerate(paragraphs, start=1)
        ],
        paragraph_count=len(paragraphs),
    )
    data = await llm.chat_json(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
    )
    return _build_spaces(
        data,
        episode=episode,
        paragraphs=paragraphs,
    )


def _build_spaces(
    data: dict[str, Any],
    *,
    episode: dict[str, Any],
    paragraphs: list[str],
) -> list[dict[str, Any]]:
    """校验 LLM 段号并按段号重组正文；不合法直接失败，不做兜底切分。"""
    raw = data.get("spaces")
    if not isinstance(raw, list) or not raw:
        raise ValidationAppError(
            f"第 {episode['ordinal']} 集语义切分结果为空"
        )

    total = len(paragraphs)
    items: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        start = _to_int(entry.get("start_paragraph"))
        end = _to_int(entry.get("end_paragraph"))
        if start is None or end is None:
            raise ValidationAppError(
                f"第 {episode['ordinal']} 集切分结果缺少段号"
            )
        if start < 1 or end > total or start > end:
            raise ValidationAppError(
                f"第 {episode['ordinal']} 集段号越界：{start}-{end}，正文共 {total} 段"
            )
        items.append({**entry, "start": start, "end": end})

    items.sort(key=lambda x: x["start"])
    cursor = 0
    for item in items:
        if item["start"] != cursor + 1:
            raise ValidationAppError(
                f"第 {episode['ordinal']} 集段号不连续：第 {cursor + 1} 段未被覆盖"
            )
        cursor = item["end"]
    if cursor != total:
        raise ValidationAppError(
            f"第 {episode['ordinal']} 集段号未覆盖到结尾：止于第 {cursor} 段，共 {total} 段"
        )

    ep_location = (episode.get("location") or "").strip()
    ep_time = (episode.get("time") or "").strip()
    spaces: list[dict[str, Any]] = []
    for ordinal, item in enumerate(items, start=1):
        body = "\n".join(paragraphs[item["start"] - 1 : item["end"]]).strip()
        location = (item.get("location") or "").strip() or ep_location or "主场景"
        title = (item.get("title") or "").strip() or location
        time_place = (item.get("time_place") or "").strip()
        if not time_place:
            time_place = " / ".join(p for p in (ep_time, location) if p)
        beat_type = (item.get("beat_type") or "").strip().lower()
        spaces.append(
            {
                "ordinal": ordinal,
                "title": title[:256],
                "location": location,
                "summary": (item.get("summary") or "").strip(),
                "time_place": time_place[:512],
                "source_text": body,
                "estimated_duration_sec": round(
                    structure_parser.estimate_duration_sec(body), 2
                ),
                "beat_type": beat_type if beat_type in _BEAT_TYPES else None,
                "mood": (item.get("mood") or "").strip()[:128] or None,
                "boundary_reason": (item.get("boundary_reason") or "").strip()[:512]
                or None,
                "segment_source": "llm",
            }
        )
    return spaces


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
