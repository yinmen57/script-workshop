"""知识库与文档服务（P0 骨架）。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.adapters.vector_qdrant import QdrantVectorStoreAdapter
from packages.domain.errors import NotFoundError, ValidationAppError
from packages.domain.ids import new_id
from packages.infra.qdrant_client import get_qdrant


async def create_kb(session: AsyncSession, tenant_id: str, payload: dict) -> dict:
    emb = (
        await session.execute(
            text(
                """
                SELECT id, model_type, dimension, status
                FROM model_config
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": payload["embedding_model_id"], "tenant_id": tenant_id},
        )
    ).mappings().first()
    if emb is None or emb["model_type"] != "embedding":
        raise ValidationAppError("embedding_model_id must reference an embedding model")
    if emb["status"] != "enabled":
        raise ValidationAppError("embedding model disabled")

    dimension = int(payload.get("dimension") or emb["dimension"] or 0)
    if not dimension:
        raise ValidationAppError("dimension required")
    if emb["dimension"] and int(emb["dimension"]) != dimension:
        raise ValidationAppError("dimension must match embedding model")

    kb_id = new_id("kb")
    collection = f"kb_{kb_id}"
    adapter = QdrantVectorStoreAdapter(get_qdrant())
    adapter.ensure_collection(collection, dimension)

    await session.execute(
        text(
            """
            INSERT INTO knowledge_base
              (id, tenant_id, name, embedding_model_id, dimension, vector_store,
               vector_collection, chunk_size, chunk_overlap, status)
            VALUES
              (:id, :tenant_id, :name, :embedding_model_id, :dimension, :vector_store,
               :vector_collection, :chunk_size, :chunk_overlap, :status)
            """
        ),
        {
            "id": kb_id,
            "tenant_id": tenant_id,
            "name": payload["name"],
            "embedding_model_id": payload["embedding_model_id"],
            "dimension": dimension,
            "vector_store": payload.get("vector_store", "qdrant"),
            "vector_collection": collection,
            "chunk_size": payload.get("chunk_size", 800),
            "chunk_overlap": payload.get("chunk_overlap", 100),
            "status": "enabled",
        },
    )
    await session.commit()
    return await get_kb(session, tenant_id, kb_id)


async def list_kbs(
    session: AsyncSession,
    tenant_id: str,
    *,
    keyword: str | None,
    page: int,
    page_size: int,
) -> dict:
    where = ["tenant_id = :tenant_id"]
    params: dict[str, Any] = {"tenant_id": tenant_id}
    if keyword:
        where.append("name LIKE :keyword")
        params["keyword"] = f"%{keyword}%"
    where_sql = " AND ".join(where)
    total = (
        await session.execute(
            text(f"SELECT COUNT(1) AS c FROM knowledge_base WHERE {where_sql}"),
            params,
        )
    ).mappings().first()["c"]
    params["limit"] = page_size
    params["offset"] = (page - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"""
                SELECT * FROM knowledge_base
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [_kb_public(dict(r)) for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def get_kb(session: AsyncSession, tenant_id: str, kb_id: str) -> dict:
    row = await _get_kb_raw(session, tenant_id, kb_id)
    return _kb_public(row)


async def update_kb(
    session: AsyncSession, tenant_id: str, kb_id: str, payload: dict
) -> dict:
    current = await _get_kb_raw(session, tenant_id, kb_id)
    if "dimension" in payload and payload["dimension"] != current["dimension"]:
        raise ValidationAppError("dimension is immutable")
    if "embedding_model_id" in payload and payload["embedding_model_id"] != current["embedding_model_id"]:
        raise ValidationAppError("embedding_model_id is immutable")

    await session.execute(
        text(
            """
            UPDATE knowledge_base SET
              name = :name,
              chunk_size = :chunk_size,
              chunk_overlap = :chunk_overlap,
              status = :status
            WHERE id = :id AND tenant_id = :tenant_id
            """
        ),
        {
            "id": kb_id,
            "tenant_id": tenant_id,
            "name": payload.get("name", current["name"]),
            "chunk_size": payload.get("chunk_size", current["chunk_size"]),
            "chunk_overlap": payload.get("chunk_overlap", current["chunk_overlap"]),
            "status": payload.get("status", current["status"]),
        },
    )
    await session.commit()
    return await get_kb(session, tenant_id, kb_id)


async def delete_kb(
    session: AsyncSession, tenant_id: str, kb_id: str, *, confirm: bool
) -> None:
    if not confirm:
        raise ValidationAppError("confirm=true required")
    current = await _get_kb_raw(session, tenant_id, kb_id)
    docs = (
        await session.execute(
            text("SELECT id FROM document WHERE tenant_id = :tenant_id AND kb_id = :kb_id"),
            {"tenant_id": tenant_id, "kb_id": kb_id},
        )
    ).mappings().all()
    adapter = QdrantVectorStoreAdapter(get_qdrant())
    for doc in docs:
        adapter.delete_by_doc(
            current["vector_collection"], tenant_id, kb_id, doc["id"]
        )
    await session.execute(
        text("DELETE FROM document_chunk WHERE tenant_id = :tenant_id AND kb_id = :kb_id"),
        {"tenant_id": tenant_id, "kb_id": kb_id},
    )
    await session.execute(
        text("DELETE FROM document WHERE tenant_id = :tenant_id AND kb_id = :kb_id"),
        {"tenant_id": tenant_id, "kb_id": kb_id},
    )
    await session.execute(
        text("DELETE FROM knowledge_base WHERE id = :id AND tenant_id = :tenant_id"),
        {"id": kb_id, "tenant_id": tenant_id},
    )
    await session.commit()


async def create_text_document(
    session: AsyncSession, tenant_id: str, kb_id: str, title: str, content: str
) -> dict:
    await _get_kb_raw(session, tenant_id, kb_id)
    doc_id = new_id("doc")
    job_id = new_id("job")
    await session.execute(
        text(
            """
            INSERT INTO document
              (id, tenant_id, kb_id, title, source_type, status, meta)
            VALUES
              (:id, :tenant_id, :kb_id, :title, 'text', 'pending', :meta)
            """
        ),
        {
            "id": doc_id,
            "tenant_id": tenant_id,
            "kb_id": kb_id,
            "title": title,
            "meta": json.dumps({"content": content}, ensure_ascii=False),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO ingest_job
              (id, tenant_id, doc_id, job_type, status)
            VALUES
              (:id, :tenant_id, :doc_id, 'embed', 'pending')
            """
        ),
        {"id": job_id, "tenant_id": tenant_id, "doc_id": doc_id},
    )
    await session.commit()
    # P0：同步简易切分入库，后续改异步 worker
    try:
        await process_text_ingest(session, tenant_id, doc_id, job_id)
        status = "ready"
    except Exception:  # noqa: BLE001
        status = "failed"
    return {"doc_id": doc_id, "status": status, "job_id": job_id}


async def process_text_ingest(
    session: AsyncSession, tenant_id: str, doc_id: str, job_id: str
) -> None:
    from packages.infra.crypto import decrypt_secret
    from packages.adapters.embedding_openai import OpenAICompatibleEmbeddingAdapter

    doc = (
        await session.execute(
            text(
                """
                SELECT d.*, k.embedding_model_id, k.dimension, k.vector_collection,
                       k.chunk_size, k.chunk_overlap
                FROM document d
                JOIN knowledge_base k ON k.id = d.kb_id
                WHERE d.id = :doc_id AND d.tenant_id = :tenant_id
                """
            ),
            {"doc_id": doc_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if doc is None:
        raise NotFoundError("document not found")

    await session.execute(
        text("UPDATE document SET status = 'processing' WHERE id = :id"),
        {"id": doc_id},
    )
    await session.execute(
        text("UPDATE ingest_job SET status = 'processing', attempts = attempts + 1 WHERE id = :id"),
        {"id": job_id},
    )
    await session.commit()

    try:
        meta = doc["meta"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        content = (meta or {}).get("content") or ""
        chunk_size = int(doc["chunk_size"] or 800)
        chunks = [
            content[i : i + chunk_size]
            for i in range(0, max(len(content), 1), chunk_size)
            if content[i : i + chunk_size].strip()
        ]
        if not chunks:
            raise ValidationAppError("empty content")

        model = (
            await session.execute(
                text(
                    """
                    SELECT * FROM model_config
                    WHERE id = :id AND tenant_id = :tenant_id
                    """
                ),
                {"id": doc["embedding_model_id"], "tenant_id": tenant_id},
            )
        ).mappings().first()
        if model is None:
            raise ValidationAppError("embedding model missing")

        api_key = (
            decrypt_secret(model["api_key_cipher"]) if model["api_key_cipher"] else ""
        )
        adapter = OpenAICompatibleEmbeddingAdapter(
            model["base_url"] or "", api_key, model["model_name"]
        )
        vectors = await adapter.embed(chunks)

        from qdrant_client.http import models as qm

        client = get_qdrant()
        points = []
        import uuid

        for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            # Qdrant 点 ID 使用 UUID
            chunk_id = str(uuid.uuid4())
            await session.execute(
                text(
                    """
                    INSERT INTO document_chunk
                      (id, tenant_id, kb_id, doc_id, ordinal, content, token_estimate)
                    VALUES
                      (:id, :tenant_id, :kb_id, :doc_id, :ordinal, :content, :token_estimate)
                    """
                ),
                {
                    "id": chunk_id,
                    "tenant_id": tenant_id,
                    "kb_id": doc["kb_id"],
                    "doc_id": doc_id,
                    "ordinal": idx,
                    "content": chunk,
                    "token_estimate": len(chunk),
                },
            )
            points.append(
                qm.PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "tenant_id": tenant_id,
                        "kb_id": doc["kb_id"],
                        "doc_id": doc_id,
                        "content": chunk,
                    },
                )
            )
        client.upsert(collection_name=doc["vector_collection"], points=points)
        await session.execute(
            text(
                """
                UPDATE document SET status = 'ready', chunk_count = :n, error_message = NULL
                WHERE id = :id
                """
            ),
            {"id": doc_id, "n": len(chunks)},
        )
        await session.execute(
            text("UPDATE ingest_job SET status = 'succeeded', last_error = NULL WHERE id = :id"),
            {"id": job_id},
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.execute(
            text(
                """
                UPDATE document SET status = 'failed', error_message = :err
                WHERE id = :id
                """
            ),
            {"id": doc_id, "err": str(exc)[:1000]},
        )
        await session.execute(
            text("UPDATE ingest_job SET status = 'failed', last_error = :err WHERE id = :id"),
            {"id": job_id, "err": str(exc)[:1000]},
        )
        await session.commit()
        raise


async def list_documents(
    session: AsyncSession, tenant_id: str, kb_id: str, page: int, page_size: int
) -> dict:
    await _get_kb_raw(session, tenant_id, kb_id)
    total = (
        await session.execute(
            text(
                """
                SELECT COUNT(1) AS c FROM document
                WHERE tenant_id = :tenant_id AND kb_id = :kb_id
                """
            ),
            {"tenant_id": tenant_id, "kb_id": kb_id},
        )
    ).mappings().first()["c"]
    rows = (
        await session.execute(
            text(
                """
                SELECT id, title, source_type, status, chunk_count, error_message, created_at, updated_at
                FROM document
                WHERE tenant_id = :tenant_id AND kb_id = :kb_id
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "tenant_id": tenant_id,
                "kb_id": kb_id,
                "limit": page_size,
                "offset": (page - 1) * page_size,
            },
        )
    ).mappings().all()
    return {
        "items": [dict(r) | {
            "created_at": str(r["created_at"]) if r.get("created_at") else None,
            "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
        } for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


async def rag_search(
    session: AsyncSession,
    tenant_id: str,
    *,
    kb_ids: list[str],
    query: str,
    top_k: int = 5,
) -> dict:
    if not kb_ids:
        raise ValidationAppError("knowledge_base_ids required")
    from packages.infra.crypto import decrypt_secret
    from packages.adapters.embedding_openai import OpenAICompatibleEmbeddingAdapter
    from qdrant_client.http import models as qm

    kb = await _get_kb_raw(session, tenant_id, kb_ids[0])
    model = (
        await session.execute(
            text(
                """
                SELECT * FROM model_config
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": kb["embedding_model_id"], "tenant_id": tenant_id},
        )
    ).mappings().first()
    if model is None:
        raise ValidationAppError("embedding model missing")
    api_key = decrypt_secret(model["api_key_cipher"]) if model["api_key_cipher"] else ""
    adapter = OpenAICompatibleEmbeddingAdapter(
        model["base_url"] or "", api_key, model["model_name"]
    )
    vector = (await adapter.embed([query]))[0]
    client = get_qdrant()
    query_filter = qm.Filter(
        must=[
            qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
            qm.FieldCondition(key="kb_id", match=qm.MatchValue(value=kb["id"])),
        ]
    )
    # 兼容新旧 qdrant-client
    if hasattr(client, "query_points"):
        resp = client.query_points(
            collection_name=kb["vector_collection"],
            query=vector,
            limit=top_k,
            query_filter=query_filter,
        )
        hits = resp.points
    else:
        hits = client.search(
            collection_name=kb["vector_collection"],
            query_vector=vector,
            limit=top_k,
            query_filter=query_filter,
        )
    citations = [
        {
            "doc_id": (hit.payload or {}).get("doc_id"),
            "chunk_id": str(hit.id),
            "score": hit.score,
            "content": (hit.payload or {}).get("content"),
            "source": (hit.payload or {}).get("doc_id"),
        }
        for hit in hits
    ]
    return {"query": query, "citations": citations}


def _kb_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "tenant_id": row["tenant_id"],
        "name": row["name"],
        "embedding_model_id": row["embedding_model_id"],
        "dimension": row["dimension"],
        "vector_store": row["vector_store"],
        "vector_collection": row["vector_collection"],
        "chunk_size": row["chunk_size"],
        "chunk_overlap": row["chunk_overlap"],
        "status": row["status"],
        "created_at": str(row["created_at"]) if row.get("created_at") else None,
        "updated_at": str(row["updated_at"]) if row.get("updated_at") else None,
    }


async def _get_kb_raw(session: AsyncSession, tenant_id: str, kb_id: str) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM knowledge_base
                WHERE id = :id AND tenant_id = :tenant_id
                """
            ),
            {"id": kb_id, "tenant_id": tenant_id},
        )
    ).mappings().first()
    if row is None:
        raise NotFoundError("knowledge_base not found")
    return dict(row)
