"""视频片段画布快照：布局 / 视口持久化。

画布单位 = 视频片段（≤15s，D1/D2）；节点生成走既有 /script-biz 工具，本模块只存布局。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from business.script import parse_service, project_service, shot_service
from business.script.video_segment_service import require_segment
from framework.domain.errors import ValidationAppError
from framework.domain.ids import new_id


def _snapshot_public(row: dict[str, Any]) -> dict[str, Any]:
    nodes = row.get("nodes")
    if isinstance(nodes, str):
        nodes = json.loads(nodes)
    edges = row.get("edges")
    if isinstance(edges, str):
        edges = json.loads(edges)
    viewport = row.get("viewport")
    if isinstance(viewport, str):
        viewport = json.loads(viewport)
    return {
        "id": row["id"],
        "video_segment_id": row["video_segment_id"],
        "nodes": nodes or [],
        "edges": edges or [],
        "viewport": viewport,
        "version": int(row["version"]),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


async def get_latest_snapshot(
    session: AsyncSession, tenant_id: str, video_segment_id: str
) -> dict | None:
    await require_segment(session, tenant_id, video_segment_id)
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM canvas_snapshot
                WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"seg_id": video_segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    return _snapshot_public(dict(row)) if row else None


def _sanitize_graph(nodes: list[Any], edges: list[Any]) -> tuple[list[Any], list[Any]]:
    """落库前去掉前端运行时字段（如 onAction）。"""
    clean_nodes: list[Any] = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        data = n.get("data")
        if isinstance(data, dict):
            data = {
                k: v
                for k, v in data.items()
                if k not in {"onAction"} and not callable(v)
            }
        clean_nodes.append({**n, "data": data})
    clean_edges = [e for e in edges if isinstance(e, dict)]
    return clean_nodes, clean_edges


async def save_snapshot(
    session: AsyncSession,
    tenant_id: str,
    video_segment_id: str,
    *,
    nodes: list[Any],
    edges: list[Any],
    viewport: dict[str, Any] | None = None,
) -> dict:
    segment = await require_segment(session, tenant_id, video_segment_id)
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValidationAppError("nodes / edges 必须是数组")

    nodes, edges = _sanitize_graph(nodes, edges)
    latest = await get_latest_snapshot(session, tenant_id, video_segment_id)
    # 自动保存就地更新；version 自增作乐观并发标记，不堆历史行
    if latest:
        next_version = int(latest["version"]) + 1
        await session.execute(
            text(
                """
                UPDATE canvas_snapshot
                SET nodes = CAST(:nodes AS JSON),
                    edges = CAST(:edges AS JSON),
                    viewport = CAST(:viewport AS JSON),
                    version = :version,
                    updated_at = CURRENT_TIMESTAMP(3)
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {
                "id": latest["id"],
                "tenant_id": tenant_id,
                "nodes": json.dumps(nodes, ensure_ascii=False),
                "edges": json.dumps(edges, ensure_ascii=False),
                "viewport": json.dumps(viewport, ensure_ascii=False)
                if viewport is not None
                else None,
                "version": next_version,
            },
        )
        await session.commit()
        row = (
            await session.execute(
                text("SELECT * FROM canvas_snapshot WHERE id = :id"),
                {"id": latest["id"]},
            )
        ).mappings().first()
    else:
        snap_id = new_id("scvs")
        await session.execute(
            text(
                """
                INSERT INTO canvas_snapshot
                  (id, tenant_id, video_segment_id, nodes, edges, viewport, version)
                VALUES
                  (:id, :tenant_id, :video_segment_id,
                   CAST(:nodes AS JSON), CAST(:edges AS JSON),
                   CAST(:viewport AS JSON), :version)
                """
            ),
            {
                "id": snap_id,
                "tenant_id": tenant_id,
                "video_segment_id": video_segment_id,
                "nodes": json.dumps(nodes, ensure_ascii=False),
                "edges": json.dumps(edges, ensure_ascii=False),
                "viewport": json.dumps(viewport, ensure_ascii=False)
                if viewport is not None
                else None,
                "version": 1,
            },
        )
        await session.commit()
        row = (
            await session.execute(
                text("SELECT * FROM canvas_snapshot WHERE id = :id"),
                {"id": snap_id},
            )
        ).mappings().first()
    public = _snapshot_public(dict(row))
    public["project_id"] = segment["project_id"]
    public["narrative_space_id"] = segment["narrative_space_id"]
    return public


def _default_layout(
    *,
    segment: dict[str, Any],
    characters: list[dict[str, Any]],
    props: list[dict[str, Any]],
    shots: list[dict[str, Any]],
    video_prompt: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按依赖图生成初始节点与边：人物/道具 → 本片段分镜 → 成片。"""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    y = 0
    char_ids: list[str] = []
    for i, c in enumerate(characters):
        nid = f"character:{c['id']}"
        char_ids.append(nid)
        nodes.append(
            {
                "id": nid,
                "type": "character",
                "position": {"x": 40, "y": y + i * 120},
                "data": {
                    "kind": "character",
                    "entity_id": c["id"],
                    "label": c.get("name") or c.get("character_key"),
                    "record_status": c.get("record_status"),
                    "status": "idle",
                },
            }
        )
    prop_ids: list[str] = []
    for i, p in enumerate(props):
        nid = f"prop:{p['id']}"
        prop_ids.append(nid)
        nodes.append(
            {
                "id": nid,
                "type": "prop",
                "position": {"x": 40, "y": y + (len(characters) + i) * 120},
                "data": {
                    "kind": "prop",
                    "entity_id": p["id"],
                    "label": p.get("prop_name") or p.get("prop_key"),
                    "record_status": p.get("record_status"),
                    "status": "idle",
                },
            }
        )
    shot_ids: list[str] = []
    for i, s in enumerate(shots):
        nid = f"shot:{s['id']}"
        shot_ids.append(nid)
        nodes.append(
            {
                "id": nid,
                "type": "shot",
                "position": {"x": 360, "y": 40 + i * 140},
                "data": {
                    "kind": "shot",
                    "entity_id": s["id"],
                    "label": f"镜 {s.get('ordinal')}",
                    "beat": s.get("beat") or "",
                    "record_status": s.get("record_status"),
                    "status": "idle",
                },
            }
        )
        for cid in s.get("character_ids") or []:
            src = f"character:{cid}"
            if src in char_ids:
                edges.append(
                    {
                        "id": f"e:{src}->{nid}",
                        "source": src,
                        "target": nid,
                        "type": "canvas",
                    }
                )
        for pid in s.get("prop_ids") or []:
            src = f"prop:{pid}"
            if src in prop_ids:
                edges.append(
                    {
                        "id": f"e:{src}->{nid}",
                        "source": src,
                        "target": nid,
                        "type": "canvas",
                    }
                )

    video_id = "video_out"
    duration = segment.get("duration_sec")
    duration_label = (
        f"{float(duration):.1f}s" if duration is not None else "≤15s"
    )
    nodes.append(
        {
            "id": video_id,
            "type": "video_out",
            "position": {"x": 700, "y": 80},
            "data": {
                "kind": "video_out",
                "video_segment_id": segment["id"],
                "narrative_space_id": segment["narrative_space_id"],
                "video_prompt_id": (video_prompt or {}).get("id"),
                "label": "成片视频",
                "title": segment.get("title") or f"片段 {segment.get('ordinal')}",
                "beat": duration_label,
                "record_status": (video_prompt or {}).get("record_status"),
                "status": "idle",
            },
        }
    )
    for sid in shot_ids:
        edges.append(
            {
                "id": f"e:{sid}->{video_id}",
                "source": sid,
                "target": video_id,
                "type": "canvas",
            }
        )
    return nodes, edges


async def get_or_bootstrap(
    session: AsyncSession, tenant_id: str, video_segment_id: str
) -> dict:
    """读取最新快照；若无则按本片段分镜/资产自动铺节点。"""
    segment = await require_segment(session, tenant_id, video_segment_id)
    project_id = segment["project_id"]
    narrative_space_id = segment["narrative_space_id"]
    await project_service.require_project(session, tenant_id, project_id)
    raw_shot_ids = segment.get("shot_ids")
    if isinstance(raw_shot_ids, str):
        raw_shot_ids = json.loads(raw_shot_ids)
    segment_shot_ids = list(raw_shot_ids or [])

    latest = await get_latest_snapshot(session, tenant_id, video_segment_id)
    segment_meta = {
        "id": segment["id"],
        "title": segment.get("title") or f"片段 {segment.get('ordinal')}",
        "ordinal": int(segment["ordinal"]),
        "duration_sec": float(segment["duration_sec"])
        if segment.get("duration_sec") is not None
        else None,
        "narrative_space_id": narrative_space_id,
    }
    if latest and latest.get("nodes"):
        latest["project_id"] = project_id
        latest["narrative_space_id"] = narrative_space_id
        latest["segment"] = segment_meta
        return latest

    assets = await parse_service.get_assets(session, tenant_id, project_id)
    shots_bundle = await shot_service.list_shots(
        session,
        tenant_id,
        project_id,
        narrative_space_id=narrative_space_id,
    )
    allowed_shot_ids = set(segment_shot_ids)
    segment_shots = [
        s for s in shots_bundle["items"] if s["id"] in allowed_shot_ids
    ]
    # 仅保留本片段分镜引用到的人物/道具
    used_chars: set[str] = set()
    used_props: set[str] = set()
    for s in segment_shots:
        used_chars.update(s.get("character_ids") or [])
        used_props.update(s.get("prop_ids") or [])
    characters = [
        c for c in assets["characters"] if not used_chars or c["id"] in used_chars
    ]
    props = [p for p in assets["props"] if not used_props or p["id"] in used_props]
    if not segment_shots:
        characters = assets["characters"]
        props = assets["props"]

    vp_row = (
        await session.execute(
            text(
                """
                SELECT * FROM video_prompt
                WHERE video_segment_id = :seg_id AND tenant_id = :tenant_id
                ORDER BY version DESC
                LIMIT 1
                """
            ),
            {"seg_id": video_segment_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    video_prompt = dict(vp_row) if vp_row else None

    nodes, edges = _default_layout(
        segment=segment,
        characters=characters,
        props=props,
        shots=segment_shots,
        video_prompt=video_prompt,
    )
    saved = await save_snapshot(
        session,
        tenant_id,
        video_segment_id,
        nodes=nodes,
        edges=edges,
        viewport={"x": 0, "y": 0, "zoom": 1},
    )
    saved["project_id"] = project_id
    saved["narrative_space_id"] = narrative_space_id
    saved["segment"] = segment_meta
    saved["bootstrapped"] = True
    return saved
