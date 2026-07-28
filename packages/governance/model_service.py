"""模型配置服务。"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.adapters.embedding_openai import OpenAICompatibleEmbeddingAdapter
from packages.adapters.llm_openai import OpenAICompatibleChatAdapter
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id
from packages.infra.crypto import decrypt_secret, encrypt_secret


def _validate_model_fields(
    *,
    model_type: str,
    dimension: int | None,
) -> None:
    if model_type not in {"chat", "embedding", "rerank"}:
        raise ValidationAppError("model_type must be chat/embedding/rerank")
    if model_type == "embedding" and not dimension:
        raise ValidationAppError("embedding model requires dimension")
    if model_type == "rerank" and dimension is not None:
        raise ValidationAppError("rerank model must not set dimension")


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    extra = row.get("extra")
    if isinstance(extra, str):
        extra = json.loads(extra)
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "provider": row["provider"],
        "model_type": row["model_type"],
        "model_name": row["model_name"],
        "base_url": row["base_url"],
        "dimension": row["dimension"],
        "extra": extra or {},
        "status": row["status"],
        "has_api_key": bool(row.get("api_key_cipher")),
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


async def create_model(session: AsyncSession, tenant_id: str, payload: dict) -> dict:
    model_type = payload["model_type"]
    dimension = payload.get("dimension")
    _validate_model_fields(model_type=model_type, dimension=dimension)

    model_id = new_id("mdl")
    cipher = encrypt_secret(payload["api_key"]) if payload.get("api_key") else None
    await session.execute(
        text(
            """
            INSERT INTO model_config
              (id, tenant_id, name, provider, model_type, model_name, base_url,
               api_key_cipher, dimension, extra, status)
            VALUES
              (:id, :tenant_id, :name, :provider, :model_type, :model_name, :base_url,
               :api_key_cipher, :dimension, :extra, :status)
            """
        ),
        {
            "id": model_id,
            "tenant_id": tenant_id,
            "name": payload["name"],
            "provider": payload.get("provider", "openai_compatible"),
            "model_type": model_type,
            "model_name": payload["model_name"],
            "base_url": payload.get("base_url"),
            "api_key_cipher": cipher,
            "dimension": dimension,
            "extra": json.dumps(payload.get("extra") or {}, ensure_ascii=False),
            "status": payload.get("status", "enabled"),
        },
    )
    await session.commit()
    return await get_model(session, tenant_id, model_id)


async def list_models(
    session: AsyncSession,
    tenant_id: str,
    *,
    model_type: str | None,
    status: str | None,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict:
    where = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": tenant_id}
    if model_type:
        where.append("model_type = :model_type")
        params["model_type"] = model_type
    if status:
        where.append("status = :status")
        params["status"] = status
    if keyword:
        where.append("name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"

    where_sql = " AND ".join(where)
    total = (
        await session.execute(
            text(f"SELECT COUNT(1) AS c FROM model_config WHERE {where_sql}"),
            params,
        )
    ).mappings().first()["c"]

    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"""
                SELECT * FROM model_config
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [_row_to_public(dict(r)) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def get_model(session: AsyncSession, tenant_id: str, model_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM model_config
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": model_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("model not found")
    return _row_to_public(dict(row))


async def update_model(
    session: AsyncSession, tenant_id: str, model_id: str, payload: dict
) -> dict:
    current = await _get_raw(session, tenant_id, model_id)
    model_type = payload.get("model_type", current["model_type"])
    dimension = payload["dimension"] if "dimension" in payload else current["dimension"]
    _validate_model_fields(model_type=model_type, dimension=dimension)

    cipher = current["api_key_cipher"]
    if payload.get("api_key"):
        cipher = encrypt_secret(payload["api_key"])

    await session.execute(
        text(
            """
            UPDATE model_config SET
              name = :name,
              provider = :provider,
              model_type = :model_type,
              model_name = :model_name,
              base_url = :base_url,
              api_key_cipher = :api_key_cipher,
              dimension = :dimension,
              extra = :extra,
              status = :status
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "id": model_id,
            "tenant_id": tenant_id,
            "name": payload.get("name", current["name"]),
            "provider": payload.get("provider", current["provider"]),
            "model_type": model_type,
            "model_name": payload.get("model_name", current["model_name"]),
            "base_url": payload.get("base_url", current["base_url"]),
            "api_key_cipher": cipher,
            "dimension": dimension,
            "extra": json.dumps(
                payload.get("extra")
                if "extra" in payload
                else (
                    json.loads(current["extra"])
                    if isinstance(current["extra"], str)
                    else (current["extra"] or {})
                ),
                ensure_ascii=False,
            ),
            "status": payload.get("status", current["status"]),
        },
    )
    await session.commit()
    return await get_model(session, tenant_id, model_id)


async def delete_model(session: AsyncSession, tenant_id: str, model_id: str) -> None:
    await _get_raw(session, tenant_id, model_id)
    used_kb = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM knowledge_base
                WHERE tenant_id = :tenant_id AND embedding_model_id = :model_id
                """
            ),
            {"tenant_id": tenant_id, "model_id": model_id},
        )
    ).mappings().first()["c"]
    used_app = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM app
                WHERE tenant_id = :tenant_id
                  AND (primary_model_id = :model_id OR fallback_model_id = :model_id)
                """
            ),
            {"tenant_id": tenant_id, "model_id": model_id},
        )
    ).mappings().first()["c"]
    if used_kb or used_app:
        raise ValidationAppError("model is referenced by knowledge_base or app")

    await session.execute(
        text("DELETE FROM model_config WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": model_id, "tenant_id": tenant_id},
    )
    await session.commit()


async def test_model(session: AsyncSession, tenant_id: str, model_id: str) -> dict:
    row = await _get_raw(session, tenant_id, model_id)
    api_key = decrypt_secret(row["api_key_cipher"]) if row["api_key_cipher"] else ""
    base_url = row["base_url"] or ""
    started = time.perf_counter()
    try:
        if row["model_type"] == "chat":
            adapter = OpenAICompatibleChatAdapter(base_url, api_key, row["model_name"])
            detail = await adapter.ping()
        elif row["model_type"] == "embedding":
            adapter = OpenAICompatibleEmbeddingAdapter(
                base_url, api_key, row["model_name"]
            )
            detail = await adapter.ping()
            if row["dimension"] and detail.get("dimension") != row["dimension"]:
                raise ValidationAppError(
                    f"dimension mismatch: expected {row['dimension']}, got {detail.get('dimension')}"
                )
        else:
            # rerank：仅检查 base_url 可达性（P0）
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(base_url.rstrip("/") + "/models")
                detail = {"ok": resp.status_code < 500, "status_code": resp.status_code}
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": True,
            "model_id": model_id,
            "model_type": row["model_type"],
            "latency_ms": latency_ms,
            "detail": detail,
        }
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "model_id": model_id,
            "model_type": row["model_type"],
            "latency_ms": latency_ms,
            "detail": {"error": str(exc)},
        }


async def _get_raw(session: AsyncSession, tenant_id: str, model_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM model_config
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": model_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("model not found")
    return dict(row)
