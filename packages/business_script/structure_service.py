"""四级结构：集 / 叙事空间 的落库与目录树。

结构来自 structure_parser 规则解析（D6），不依赖 LLM scenes。
重跑只清理 record_status=ai 的节点，confirmed 永不覆盖（D5）。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.business_script import keys, project_service, structure_parser
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id


def _ns_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "episode_id": row["episode_id"],
        "scene_space_id": row.get("scene_space_id"),
        "ordinal": int(row["ordinal"]),
        "title": row["title"] or "",
        "summary": row.get("summary") or "",
        "time_place": row.get("time_place") or "",
        "source_text": row.get("source_text") or "",
        "estimated_duration_sec": float(row["estimated_duration_sec"])
        if row.get("estimated_duration_sec") is not None
        else None,
        "beat_type": row.get("beat_type") or "",
        "mood": row.get("mood") or "",
        "boundary_reason": row.get("boundary_reason") or "",
        "segment_source": row.get("segment_source") or "rule",
        "status": row["status"],
        "record_status": row.get("record_status") or "ai",
    }


def _ep_public(row: dict[str, Any], spaces: list[dict[str, Any]] | None = None) -> dict:
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "ordinal": int(row["ordinal"]),
        "title": row["title"] or "",
        "status": row["status"],
        "record_status": row.get("record_status") or "ai",
        "narrative_spaces": spaces or [],
    }


async def list_structure(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
    episodes = (
        await session.execute(
            text(
                """
                SELECT * FROM episode
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    spaces = (
        await session.execute(
            text(
                """
                SELECT * FROM narrative_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                ORDER BY episode_id, ordinal ASC
                """
            ),
            {"project_id": project_id, "tenant_id": tenant_id},
        )
    ).mappings().all()
    by_ep: dict[str, list[dict[str, Any]]] = {}
    for row in spaces:
        by_ep.setdefault(row["episode_id"], []).append(_ns_public(dict(row)))
    items = [
        _ep_public(dict(ep), by_ep.get(ep["id"], [])) for ep in episodes
    ]
    return {"items": items, "total": len(items)}


async def parse_and_sync_structure(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    script_text: str,
) -> dict:
    """规则解析剧本结构并落库。"""
    await project_service.require_project(session, tenant_id, project_id)
    parsed = structure_parser.parse_script_structure(script_text)
    sync_result = await sync_from_parsed(session, tenant_id, project_id, parsed)
    return {
        "parsed": {
            "episode_count": parsed["episode_count"],
            "narrative_space_count": parsed["narrative_space_count"],
            "preamble": parsed.get("preamble") or "",
            # 供后续 LLM 资产抽取：含集元数据，不含大段正文
            "episodes": [
                {
                    "ordinal": ep["ordinal"],
                    "title": ep["title"],
                    "characters": ep.get("characters") or "",
                    "summary": ep.get("summary") or "",
                    "time": ep.get("time") or "",
                    "location": ep.get("location") or "",
                    "mood": ep.get("mood") or "",
                    "narrative_spaces": [
                        {
                            "ordinal": ns["ordinal"],
                            "title": ns.get("title") or "",
                            "time_place": ns.get("time_place") or "",
                            "estimated_duration_sec": ns.get(
                                "estimated_duration_sec"
                            ),
                            "summary": ns.get("summary") or "",
                        }
                        for ns in (ep.get("narrative_spaces") or [])
                    ],
                }
                for ep in (parsed.get("episodes") or [])
            ],
        },
        "sync": sync_result,
        "structure": await list_structure(session, tenant_id, project_id),
    }


async def sync_from_parsed(
    session: AsyncSession,
    tenant_id: str,
    project_id: str,
    parsed: dict[str, Any],
) -> dict:
    """把规则解析结果写入 episode / narrative_space（只动 ai 记录）。"""
    await _clear_ai_structure(session, tenant_id, project_id)

    # 已确认集，或集下仍有已确认叙事空间：整集跳过，避免重跑重复插入
    locked_ep_ordinals = {
        int(r["ordinal"])
        for r in (
            await session.execute(
                text(
                    """
                    SELECT DISTINCT e.ordinal
                    FROM episode e
                    WHERE e.project_id = :project_id AND e.tenant_id = :tenant_id
                      AND (
                        e.record_status = 'confirmed'
                        OR EXISTS (
                          SELECT 1 FROM narrative_space ns
                          WHERE ns.episode_id = e.id
                            AND ns.tenant_id = :tenant_id
                            AND ns.record_status = 'confirmed'
                        )
                      )
                    """
                ),
                {"project_id": project_id, "tenant_id": tenant_id},
            )
        ).mappings().all()
    }

    created_episodes: list[dict[str, Any]] = []
    created_spaces = 0

    for ep in parsed.get("episodes") or []:
        ordinal = int(ep["ordinal"])
        if ordinal in locked_ep_ordinals:
            ep_row = await _get_episode_by_ordinal(
                session, tenant_id, project_id, ordinal
            )
            created_episodes.append(
                {
                    "id": ep_row["id"] if ep_row else None,
                    "ordinal": ordinal,
                    "title": (ep_row or {}).get("title") or ep.get("title") or "",
                    "skipped_confirmed": True,
                    "narrative_spaces_added": 0,
                }
            )
            continue

        ep_id = new_id("sep")
        title = (ep.get("title") or f"第 {ordinal} 集").strip()
        await session.execute(
            text(
                """
                INSERT INTO episode
                  (id, tenant_id, project_id, ordinal, title, status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :ordinal, :title, 'draft', 'ai')
                """
            ),
            {
                "id": ep_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "ordinal": ordinal,
                "title": title,
            },
        )
        n = await _insert_spaces(
            session,
            tenant_id=tenant_id,
            project_id=project_id,
            episode_id=ep_id,
            spaces=ep.get("narrative_spaces") or [],
            start_ordinal=1,
        )
        created_spaces += n
        created_episodes.append(
            {
                "id": ep_id,
                "ordinal": ordinal,
                "title": title,
                "narrative_spaces_added": n,
            }
        )

    return {
        "episodes": created_episodes,
        "episode_count": len(created_episodes),
        "narrative_space_count": created_spaces,
    }


async def _clear_ai_structure(
    session: AsyncSession, tenant_id: str, project_id: str
) -> None:
    await session.execute(
        text(
            """
            DELETE FROM shot_plan
            WHERE tenant_id = :tenant_id AND project_id = :project_id
              AND record_status = 'ai'
              AND narrative_space_id IN (
                SELECT id FROM (
                  SELECT id FROM narrative_space
                  WHERE project_id = :project_id AND tenant_id = :tenant_id
                    AND record_status = 'ai'
                ) AS ai_ns
              )
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM video_prompt
            WHERE tenant_id = :tenant_id AND project_id = :project_id
              AND record_status = 'ai'
              AND narrative_space_id IN (
                SELECT id FROM (
                  SELECT id FROM narrative_space
                  WHERE project_id = :project_id AND tenant_id = :tenant_id
                    AND record_status = 'ai'
                ) AS ai_ns
              )
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM video_segment
            WHERE tenant_id = :tenant_id AND project_id = :project_id
              AND record_status = 'ai'
              AND narrative_space_id IN (
                SELECT id FROM (
                  SELECT id FROM narrative_space
                  WHERE project_id = :project_id AND tenant_id = :tenant_id
                    AND record_status = 'ai'
                ) AS ai_ns
              )
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM narrative_space
            WHERE project_id = :project_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )
    # 仍挂着叙事空间的集不删（可能是 confirmed 空间留在 ai 集下）
    await session.execute(
        text(
            """
            DELETE FROM episode
            WHERE project_id = :project_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
              AND id NOT IN (
                SELECT episode_id FROM (
                  SELECT DISTINCT episode_id FROM narrative_space
                  WHERE project_id = :project_id AND tenant_id = :tenant_id
                ) AS keep_ep
              )
            """
        ),
        {"project_id": project_id, "tenant_id": tenant_id},
    )


async def _get_episode_by_ordinal(
    session: AsyncSession, tenant_id: str, project_id: str, ordinal: int
) -> dict[str, Any] | None:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM episode
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                  AND ordinal = :ordinal
                LIMIT 1
                """
            ),
            {
                "project_id": project_id,
                "tenant_id": tenant_id,
                "ordinal": ordinal,
            },
        )
    ).mappings().first()
    return dict(row) if row else None


async def ensure_scene_space(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    location: str,
) -> str | None:
    """按地点名 get-or-create scene_space，返回 id。空地点返回 None。"""
    name = (location or "").strip()
    if not name:
        return None
    try:
        canonical = keys.scene_key(name)
    except ValueError:
        return None
    existing = (
        await session.execute(
            text(
                """
                SELECT id FROM scene_space
                WHERE project_id = :project_id AND tenant_id = :tenant_id
                  AND canonical_key = :canonical_key
                LIMIT 1
                """
            ),
            {
                "project_id": project_id,
                "tenant_id": tenant_id,
                "canonical_key": canonical,
            },
        )
    ).mappings().first()
    if existing:
        return existing["id"]
    space_id = new_id("ssc")
    await session.execute(
        text(
            """
            INSERT INTO scene_space
              (id, tenant_id, project_id, canonical_key, name, anchor,
               record_status)
            VALUES
              (:id, :tenant_id, :project_id, :canonical_key, :name, :anchor,
               'ai')
            """
        ),
        {
            "id": space_id,
            "tenant_id": tenant_id,
            "project_id": project_id,
            "canonical_key": canonical,
            "name": name[:128],
            "anchor": name,
        },
    )
    return space_id


async def list_scene_spaces(
    session: AsyncSession, tenant_id: str, project_id: str
) -> dict:
    await project_service.require_project(session, tenant_id, project_id)
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
    items = [
        {
            "id": r["id"],
            "project_id": r["project_id"],
            "canonical_key": r["canonical_key"],
            "name": r["name"],
            "anchor": r.get("anchor") or "",
            "reference_image_url": r.get("reference_image_url"),
            "record_status": r.get("record_status") or "ai",
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


async def _insert_spaces(
    session: AsyncSession,
    *,
    tenant_id: str,
    project_id: str,
    episode_id: str,
    spaces: list[Any],
    start_ordinal: int,
) -> int:
    count = 0
    for i, space in enumerate(spaces):
        if not isinstance(space, dict):
            continue
        ordinal = start_ordinal + i
        ns_id = new_id("sns")
        title = (space.get("title") or f"叙事空间 {ordinal}").strip()
        location = (space.get("location") or "").strip()
        scene_space_id = space.get("scene_space_id")
        if not scene_space_id:
            scene_space_id = await ensure_scene_space(
                session,
                tenant_id=tenant_id,
                project_id=project_id,
                location=location or title,
            )
        await session.execute(
            text(
                """
                INSERT INTO narrative_space
                  (id, tenant_id, project_id, episode_id, scene_space_id, ordinal, title,
                   summary, time_place, source_text, estimated_duration_sec,
                   beat_type, mood, boundary_reason, segment_source,
                   status, record_status)
                VALUES
                  (:id, :tenant_id, :project_id, :episode_id, :scene_space_id, :ordinal, :title,
                   :summary, :time_place, :source_text, :estimated_duration_sec,
                   :beat_type, :mood, :boundary_reason, :segment_source,
                   'draft', 'ai')
                """
            ),
            {
                "id": ns_id,
                "tenant_id": tenant_id,
                "project_id": project_id,
                "episode_id": episode_id,
                "scene_space_id": scene_space_id,
                "ordinal": ordinal,
                "title": title,
                "summary": space.get("summary") or "",
                "time_place": space.get("time_place") or "",
                "source_text": space.get("source_text") or "",
                "estimated_duration_sec": space.get("estimated_duration_sec"),
                "beat_type": space.get("beat_type"),
                "mood": space.get("mood"),
                "boundary_reason": space.get("boundary_reason"),
                "segment_source": space.get("segment_source") or "rule",
            },
        )
        count += 1
    return count


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


async def confirm_narrative_space(
    session: AsyncSession,
    tenant_id: str,
    space_id: str,
    *,
    created_by: str | None = None,
) -> dict:
    from packages.business_script import revision_service

    row = await _require_space(session, tenant_id, space_id)
    public = _ns_public(row)
    if (row.get("record_status") or "ai") != "confirmed":
        await revision_service.save_revision(
            session,
            tenant_id=tenant_id,
            project_id=row["project_id"],
            target_type="narrative_space",
            target_id=space_id,
            snapshot=public,
            change_reason="pin",
            created_by=created_by,
        )
    await session.execute(
        text(
            """
            UPDATE narrative_space
            SET record_status = 'confirmed'
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {"id": space_id, "tenant_id": tenant_id},
    )
    await session.commit()
    refreshed = await _require_space(session, tenant_id, space_id)
    return _ns_public(refreshed)


async def update_narrative_space(
    session: AsyncSession,
    tenant_id: str,
    space_id: str,
    payload: dict[str, Any],
    *,
    created_by: str | None = None,
) -> dict:
    """手工编辑叙事空间；已确认记录改前先快照。"""
    from packages.business_script import revision_service

    row = await _require_space(session, tenant_id, space_id)
    public = _ns_public(row)
    allowed = (
        "title",
        "summary",
        "time_place",
        "source_text",
        "estimated_duration_sec",
        "beat_type",
        "mood",
        "boundary_reason",
    )
    updates: dict[str, Any] = {}
    for key in allowed:
        if key in payload:
            updates[key] = payload[key]
    if "ordinal" in payload:
        try:
            updates["ordinal"] = int(payload["ordinal"])
        except (TypeError, ValueError) as exc:
            raise ValidationAppError("ordinal 必须是整数") from exc
    if not updates:
        raise ValidationAppError("没有可更新字段")

    if (row.get("record_status") or "ai") == "confirmed":
        await revision_service.save_revision(
            session,
            tenant_id=tenant_id,
            project_id=row["project_id"],
            target_type="narrative_space",
            target_id=space_id,
            snapshot=public,
            change_reason="manual_edit",
            created_by=created_by,
        )

    sets = ", ".join(f"{k} = :{k}" for k in updates)
    params = {"id": space_id, "tenant_id": tenant_id, **updates}
    await session.execute(
        text(
            f"""
            UPDATE narrative_space
            SET {sets}
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        params,
    )
    await session.commit()
    refreshed = await _require_space(session, tenant_id, space_id)
    return _ns_public(refreshed)


async def delete_narrative_space(
    session: AsyncSession, tenant_id: str, space_id: str
) -> dict:
    """仅删除 ai 态叙事空间及其 ai 分镜 / ai 视频提示词。"""
    row = await _require_space(session, tenant_id, space_id)
    if (row.get("record_status") or "ai") == "confirmed":
        raise ValidationAppError("已确认叙事空间不可删除，请先反悔")
    await session.execute(
        text(
            """
            DELETE FROM shot_plan
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": space_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM video_prompt
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": space_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM video_segment
            WHERE narrative_space_id = :ns_id AND tenant_id = :tenant_id
              AND record_status = 'ai'
            """
        ),
        {"ns_id": space_id, "tenant_id": tenant_id},
    )
    await session.execute(
        text(
            """
            DELETE FROM narrative_space
            WHERE id = :id AND tenant_id = :tenant_id AND record_status = 'ai'
            """
        ),
        {"id": space_id, "tenant_id": tenant_id},
    )
    await session.commit()
    return {"deleted": True, "id": space_id}
