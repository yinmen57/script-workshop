"""剧本结构规则解析（D6）：集 + 叙事空间，不调用 LLM。

集边界：稿面标记如「剧集 [N]」「第 N 集」。
叙事空间边界（04 §2.1）：
- 场景变化（地点切换）
- 画面转场信号
- 累计成片时长将超过 15 秒

禁止用 Hook / Escalation / Cliffhanger 作为叙事空间边界（仅跳过标签行）。
"""

from __future__ import annotations

import re
from typing import Any

# 视频模型单次生成上限（秒）
MAX_NS_DURATION_SEC = 15.0

_EPISODE_RE = re.compile(
    r"^(?:剧集\s*\[(\d+)\]|第\s*(\d+)\s*集)\s*$"
)
_META_RE = re.compile(
    r"^(现身角色|时间|位置|氛围|情节梗概)\s*[:：]\s*(.*)$"
)
# 节奏标签：保留正文，标签行本身丢弃
_PACE_LABEL_RE = re.compile(
    r"^\[(?:开头Hook\s*First|中间Escalation|结尾Cliffhanger|"
    r"Hook\s*First|Escalation|Cliffhanger)\]\s*$",
    re.IGNORECASE,
)
_TRANSITION_RE = re.compile(
    r"(?i)\b(?:cut to|smash cut|fade (?:in|out|to)|dissolve to|"
    r"meanwhile|later that|the next (?:morning|day|night)|"
    r"back (?:at|in)|elsewhere)\b|"
    r"(?:转场|切至|淡入|淡出|叠化|与此同时|与此同时|另一边)"
)
_LOC_SPLIT_RE = re.compile(r"[；;|/／]+")
_WORD_RE = re.compile(r"[A-Za-z0-9']+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def estimate_duration_sec(text: str) -> float:
    """按口播密度粗估成片秒数：英文约 2.5 词/秒，中文约 4 字/秒。"""
    raw = (text or "").strip()
    if not raw:
        return 0.0
    words = len(_WORD_RE.findall(raw))
    cjk = len(_CJK_RE.findall(raw))
    sec = words / 2.5 + cjk / 4.0
    return max(0.5, sec) if (words or cjk) else 0.0


def parse_script_structure(script_text: str) -> dict[str, Any]:
    """把剧本文本解析为集 / 叙事空间树（纯规则）。"""
    lines = [ln.strip() for ln in (script_text or "").splitlines()]
    lines = [ln for ln in lines if ln]

    preamble: list[str] = []
    episodes_raw: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in lines:
        ep_m = _EPISODE_RE.match(line)
        if ep_m:
            if current is not None:
                episodes_raw.append(current)
            ordinal = int(ep_m.group(1) or ep_m.group(2))
            current = {
                "ordinal": ordinal,
                "title": f"第 {ordinal} 集",
                "meta": {},
                "body_lines": [],
            }
            continue
        if current is None:
            preamble.append(line)
            continue
        if _PACE_LABEL_RE.match(line):
            continue
        meta_m = _META_RE.match(line)
        if meta_m and not current["body_lines"]:
            current["meta"][meta_m.group(1)] = meta_m.group(2).strip()
            continue
        # 元数据区结束后若再出现同类键值，并入正文，避免误伤
        current["body_lines"].append(line)

    if current is not None:
        episodes_raw.append(current)

    if not episodes_raw:
        # 无集标记：整篇作为第 1 集
        episodes_raw = [
            {
                "ordinal": 1,
                "title": "第 1 集",
                "meta": {},
                "body_lines": lines,
            }
        ]
        preamble = []

    episodes: list[dict[str, Any]] = []
    for ep in episodes_raw:
        spaces = _split_narrative_spaces(ep)
        episodes.append(
            {
                "ordinal": ep["ordinal"],
                "title": ep["title"],
                "characters": ep["meta"].get("现身角色") or "",
                "summary": ep["meta"].get("情节梗概") or "",
                "time": ep["meta"].get("时间") or "",
                "location": ep["meta"].get("位置") or "",
                "mood": ep["meta"].get("氛围") or "",
                "narrative_spaces": spaces,
            }
        )

    return {
        "preamble": "\n".join(preamble).strip(),
        "episodes": episodes,
        "episode_count": len(episodes),
        "narrative_space_count": sum(len(e["narrative_spaces"]) for e in episodes),
    }


def _split_locations(location_field: str) -> list[str]:
    parts = [p.strip() for p in _LOC_SPLIT_RE.split(location_field or "") if p.strip()]
    return parts or []


def _location_aliases(loc: str) -> list[str]:
    """地点匹配用的关键词（原文 + 常见英文对应）。"""
    aliases = [loc]
    mapping = {
        "公寓": ["apartment", "flat"],
        "酒店": ["hotel", "suite"],
        "套房": ["suite", "hotel"],
        "办公室": ["office"],
        "会议室": ["conference", "meeting room", "meeting"],
        "洗手间": ["restroom", "bathroom", "washroom"],
        "后门外": ["alley", "back door", "outside"],
        "车库": ["garage", "parking"],
        "工位": ["desk", "cubicle"],
    }
    for key, en_list in mapping.items():
        if key in loc:
            aliases.extend(en_list)
    return aliases


def _detect_location_index(paragraph: str, locations: list[str], current: int) -> int:
    """若段落明显指向另一地点则返回新索引，否则保持 current。"""
    if len(locations) <= 1:
        return current
    lower = paragraph.lower()
    hits: list[tuple[int, int]] = []
    for i, loc in enumerate(locations):
        for alias in _location_aliases(loc):
            token = alias.lower()
            if token and token in lower:
                hits.append((i, len(token)))
                break
    if not hits:
        return current
    # 取最长匹配，避免短词误伤
    hits.sort(key=lambda x: x[1], reverse=True)
    return hits[0][0]


def _has_transition_cue(paragraph: str) -> bool:
    return bool(_TRANSITION_RE.search(paragraph or ""))


def _split_narrative_spaces(episode: dict[str, Any]) -> list[dict[str, Any]]:
    meta = episode["meta"]
    time_s = meta.get("时间") or ""
    loc_field = meta.get("位置") or ""
    summary = meta.get("情节梗概") or ""
    locations = _split_locations(loc_field)
    body_lines: list[str] = list(episode["body_lines"])

    if not body_lines:
        loc = locations[0] if locations else "主场景"
        return [
            {
                "ordinal": 1,
                "title": loc,
                "summary": summary,
                "time_place": _join_time_place(time_s, loc),
                "source_text": "",
                "estimated_duration_sec": 0.0,
                "location": loc,
            }
        ]

    # 先按场景 / 转场切成粗段，再按 15 秒硬拆
    rough_segments: list[dict[str, Any]] = []
    buf: list[str] = []
    loc_idx = 0

    def flush() -> None:
        nonlocal buf
        if not buf:
            return
        text = "\n".join(buf).strip()
        loc = locations[loc_idx] if locations else (loc_field or "主场景")
        rough_segments.append({"location": loc, "text": text})
        buf = []

    for line in body_lines:
        next_loc = _detect_location_index(line, locations, loc_idx)
        transition = _has_transition_cue(line)
        if buf and (next_loc != loc_idx or transition):
            flush()
            loc_idx = next_loc
        elif next_loc != loc_idx:
            loc_idx = next_loc
        buf.append(line)
    flush()

    spaces: list[dict[str, Any]] = []
    for seg in rough_segments:
        spaces.extend(
            _split_by_duration(
                text=seg["text"],
                location=seg["location"],
                time_s=time_s,
                episode_summary=summary if not spaces else "",
            )
        )

    # 编号与标题去重后缀
    for i, ns in enumerate(spaces, start=1):
        ns["ordinal"] = i
        same = [s for s in spaces if s["location"] == ns["location"]]
        if len(same) > 1:
            part = same.index(ns) + 1
            ns["title"] = f"{ns['location']} ({part})"
        else:
            ns["title"] = ns["location"] or f"叙事空间 {i}"
    return spaces


def _split_by_duration(
    *,
    text: str,
    location: str,
    time_s: str,
    episode_summary: str,
) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    if not paragraphs:
        return []

    chunks: list[list[str]] = []
    current: list[str] = []
    current_sec = 0.0

    for para in paragraphs:
        para_sec = estimate_duration_sec(para)
        # 单段已超上限：独立成块（不再继续粘）
        if para_sec >= MAX_NS_DURATION_SEC and not current:
            chunks.append([para])
            continue
        if current and current_sec + para_sec > MAX_NS_DURATION_SEC:
            chunks.append(current)
            current = [para]
            current_sec = para_sec
        else:
            current.append(para)
            current_sec += para_sec
    if current:
        chunks.append(current)

    out: list[dict[str, Any]] = []
    for i, paras in enumerate(chunks):
        body = "\n".join(paras).strip()
        dur = estimate_duration_sec(body)
        out.append(
            {
                "location": location,
                "title": location,
                "summary": episode_summary if i == 0 else "",
                "time_place": _join_time_place(time_s, location),
                "source_text": body,
                "estimated_duration_sec": round(dur, 2),
            }
        )
    return out


def _join_time_place(time_s: str, location: str) -> str:
    parts = [p for p in (time_s.strip(), location.strip()) if p]
    return " / ".join(parts)
