"""向量命名空间：索引与检索能力（非产品化知识库）。"""

from __future__ import annotations

import hashlib
from typing import Any

from qdrant_client.http import models as qm
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from packages.adapters.embedding_openai import OpenAICompatibleEmbeddingAdapter
from packages.adapters.rerank_xinference import XinferenceRerankAdapter
from packages.adapters.vector_qdrant import QdrantVectorStoreAdapter
from packages.domain.errors import ValidationAppError
from packages.infra.config import get_settings
from packages.infra.db import get_session_factory
from packages.infra.qdrant_client import get_qdrant


def _collection_name(namespace: str) -> str:
    digest = hashlib.sha1(namespace.encode("utf-8")).hexdigest()[:16]
    return f"ns_{digest}"


def _embedding_adapter() -> OpenAICompatibleEmbeddingAdapter:
    settings = get_settings()
    return OpenAICompatibleEmbeddingAdapter(
        settings.xinference_base_url,
        "",
        settings.xinference_embedding_model_uid,
    )


def _rerank_adapter() -> XinferenceRerankAdapter:
    settings = get_settings()
    return XinferenceRerankAdapter(
        settings.xinference_base_url,
        settings.xinference_rerank_model_uid,
    )


async def ensure_namespace_table(session: AsyncSession) -> None:
    await session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS vector_namespace (
              namespace VARCHAR(256) NOT NULL,
              tenant_id VARCHAR(32) NOT NULL,
              collection VARCHAR(128) NOT NULL,
              dimension INT NOT NULL,
              chunk_count INT NOT NULL DEFAULT 0,
              created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
              updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                ON UPDATE CURRENT_TIMESTAMP(3),
              PRIMARY KEY (tenant_id, namespace)
            ) ENGINE=InnoDB
            """
        )
    )
    await session.commit()


async def _get_or_create_ns(
    session: AsyncSession, tenant_id: str, namespace: str, dimension: int
) -> dict:
    row = (
        await session.execute(
            text(
                """
                SELECT * FROM vector_namespace
                WHERE tenant_id = :tenant_id AND namespace = :namespace
                """
            ),
            {"tenant_id": tenant_id, "namespace": namespace},
        )
    ).mappings().first()
    if row:
        if int(row["dimension"]) != dimension:
            raise ValidationAppError(
                f"namespace {namespace} 维度为 {row['dimension']}，与当前 embedding 维度 {dimension} 不一致"
            )
        return dict(row)

    collection = _collection_name(f"{tenant_id}:{namespace}")
    adapter = QdrantVectorStoreAdapter(get_qdrant())
    adapter.ensure_collection(collection, dimension)
    await session.execute(
        text(
            """
            INSERT INTO vector_namespace
              (namespace, tenant_id, collection, dimension, chunk_count)
            VALUES
              (:namespace, :tenant_id, :collection, :dimension, 0)
            """
        ),
        {
            "namespace": namespace,
            "tenant_id": tenant_id,
            "collection": collection,
            "dimension": dimension,
        },
    )
    await session.commit()
    return {
        "namespace": namespace,
        "tenant_id": tenant_id,
        "collection": collection,
        "dimension": dimension,
        "chunk_count": 0,
    }


_RESERVED_PAYLOAD_KEYS = {"tenant_id", "namespace", "content", "ordinal"}


def _safe_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """metadata 扁平写入 payload 以便按字段过滤，保留键不允许被覆盖。"""
    return {
        k: v
        for k, v in meta.items()
        if isinstance(k, str) and k not in _RESERVED_PAYLOAD_KEYS
    }


def _chunk_text(text_value: str, chunk_size: int, overlap: int) -> list[str]:
    text_value = text_value.strip()
    if not text_value:
        return []
    if len(text_value) <= chunk_size:
        return [text_value]
    chunks: list[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)
    while start < len(text_value):
        chunks.append(text_value[start : start + chunk_size])
        start += step
    return chunks


async def replace_texts(
    session: AsyncSession,
    tenant_id: str,
    *,
    namespace: str,
    texts: list[str] | list[dict[str, Any]],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> dict:
    """清空命名空间后重新索引，用于剧本上传覆盖写入。"""
    namespace = namespace.strip()
    if not namespace:
        raise ValidationAppError("namespace required")
    row = (
        await session.execute(
            text(
                """
                SELECT collection FROM vector_namespace
                WHERE tenant_id = :tenant_id AND namespace = :namespace
                """
            ),
            {"tenant_id": tenant_id, "namespace": namespace},
        )
    ).mappings().first()
    if row:
        client = get_qdrant()
        client.delete(
            collection_name=row["collection"],
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(
                            key="tenant_id", match=qm.MatchValue(value=tenant_id)
                        ),
                        qm.FieldCondition(
                            key="namespace", match=qm.MatchValue(value=namespace)
                        ),
                    ]
                )
            ),
        )
        await session.execute(
            text(
                """
                UPDATE vector_namespace
                SET chunk_count = 0
                WHERE tenant_id = :tenant_id AND namespace = :namespace
                """
            ),
            {"tenant_id": tenant_id, "namespace": namespace},
        )
        await session.commit()
    return await index_texts(
        session,
        tenant_id,
        namespace=namespace,
        texts=texts,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


async def index_texts(
    session: AsyncSession,
    tenant_id: str,
    *,
    namespace: str,
    texts: list[str] | list[dict[str, Any]],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> dict:
    namespace = namespace.strip()
    if not namespace:
        raise ValidationAppError("namespace required")
    if not texts:
        raise ValidationAppError("texts required")

    blocks: list[tuple[str, dict[str, Any]]] = []
    for item in texts:
        if isinstance(item, dict):
            content = str(item.get("text") or item.get("content") or "")
            meta = item.get("metadata")
            blocks.append((content, meta if isinstance(meta, dict) else {}))
        elif isinstance(item, str):
            blocks.append((item, {}))
        else:
            blocks.append((str(item), {}))
    blocks = [(t, m) for t, m in blocks if t.strip()]
    if not blocks:
        raise ValidationAppError("texts empty after normalize")

    # 同一来源被切成多块时共享 metadata，检索命中后可回溯到原始记录
    chunks: list[tuple[str, dict[str, Any]]] = []
    for block, meta in blocks:
        parts = _chunk_text(block, chunk_size, chunk_overlap)
        for part_index, part in enumerate(parts):
            chunks.append(
                (
                    part,
                    {
                        **_safe_metadata(meta),
                        "chunk_index": part_index,
                        "chunk_total": len(parts),
                    },
                )
            )
    if not chunks:
        raise ValidationAppError("no chunks produced")

    embedder = _embedding_adapter()
    vectors = await embedder.embed([c for c, _ in chunks])
    dimension = len(vectors[0])
    ns = await _get_or_create_ns(session, tenant_id, namespace, dimension)

    client = get_qdrant()
    # qdrant point id 用稳定整数哈希
    points = []
    for i, ((chunk, meta), vector) in enumerate(zip(chunks, vectors, strict=True)):
        pid = int(
            hashlib.sha1(
                f"{tenant_id}:{namespace}:{i}:{chunk[:64]}".encode()
            ).hexdigest()[:15],
            16,
        )
        points.append(
            qm.PointStruct(
                id=pid,
                vector=vector,
                payload={
                    "tenant_id": tenant_id,
                    "namespace": namespace,
                    "content": chunk,
                    "ordinal": i,
                    **meta,
                },
            )
        )
    client.upsert(collection_name=ns["collection"], points=points)

    await session.execute(
        text(
            """
            UPDATE vector_namespace
            SET chunk_count = chunk_count + :n
            WHERE tenant_id = :tenant_id AND namespace = :namespace
            """
        ),
        {"n": len(points), "tenant_id": tenant_id, "namespace": namespace},
    )
    await session.commit()
    return {
        "namespace": namespace,
        "collection": ns["collection"],
        "indexed": len(points),
        "dimension": dimension,
    }


async def search(
    *,
    tenant_id: str,
    namespaces: list[str],
    query: str,
    top_k: int = 5,
    recall_n: int = 30,
    rerank: bool = True,
) -> dict:
    """多 namespace 召回 + 可选 rerank。供 retrieve 工具与 API 使用。"""
    if not namespaces:
        raise ValidationAppError("namespaces required")
    query = query.strip()
    if not query:
        raise ValidationAppError("query required")

    factory = get_session_factory()
    async with factory() as session:
        placeholders = ", ".join(f":ns{i}" for i in range(len(namespaces)))
        params: dict[str, Any] = {"tenant_id": tenant_id}
        for i, ns in enumerate(namespaces):
            params[f"ns{i}"] = ns
        rows = (
            await session.execute(
                text(
                    f"""
                    SELECT namespace, collection, dimension
                    FROM vector_namespace
                    WHERE tenant_id = :tenant_id AND namespace IN ({placeholders})
                    """
                ),
                params,
            )
        ).mappings().all()

    if not rows:
        return {
            "query": query,
            "citations": [],
            "recall_count": 0,
            "reranked": False,
        }

    embedder = _embedding_adapter()
    vector = (await embedder.embed([query]))[0]
    client = get_qdrant()
    recall_limit = max(int(recall_n), int(top_k))
    candidates: list[dict] = []

    for row in rows:
        query_filter = qm.Filter(
            must=[
                qm.FieldCondition(
                    key="tenant_id", match=qm.MatchValue(value=tenant_id)
                ),
                qm.FieldCondition(
                    key="namespace", match=qm.MatchValue(value=row["namespace"])
                ),
            ]
        )
        if hasattr(client, "query_points"):
            resp = client.query_points(
                collection_name=row["collection"],
                query=vector,
                limit=recall_limit,
                query_filter=query_filter,
            )
            hits = resp.points
        else:
            hits = client.search(
                collection_name=row["collection"],
                query_vector=vector,
                limit=recall_limit,
                query_filter=query_filter,
            )
        for hit in hits:
            payload = hit.payload or {}
            candidates.append(
                {
                    "namespace": payload.get("namespace") or row["namespace"],
                    "chunk_id": str(hit.id),
                    "score": float(hit.score or 0),
                    "content": payload.get("content") or "",
                    "metadata": {
                        k: v
                        for k, v in payload.items()
                        if k not in _RESERVED_PAYLOAD_KEYS
                    },
                    "recall_score": float(hit.score or 0),
                }
            )

    candidates.sort(key=lambda x: x["score"], reverse=True)
    recall_count = len(candidates)
    reranked = False

    if rerank and candidates:
        # 开启 rerank 后不做降级：静默退回向量分数会让排序质量无声变差且无法察觉
        docs = [c["content"] for c in candidates]
        ranked = await _rerank_adapter().rerank(query, docs, top_n=top_k)
        candidates = [
            {
                **candidates[item["index"]],
                "score": item["score"],
                "rerank_score": item["score"],
            }
            for item in ranked
        ]
        reranked = True
    else:
        candidates = candidates[:top_k]

    return {
        "query": query,
        "citations": candidates,
        "recall_count": recall_count,
        "reranked": reranked,
    }


async def list_namespaces(session: AsyncSession, tenant_id: str) -> dict:
    rows = (
        await session.execute(
            text(
                """
                SELECT namespace, collection, dimension, chunk_count, updated_at
                FROM vector_namespace
                WHERE tenant_id = :tenant_id
                ORDER BY updated_at DESC
                """
            ),
            {"tenant_id": tenant_id},
        )
    ).mappings().all()
    return {
        "items": [
            {
                **dict(r),
                "updated_at": str(r["updated_at"]) if r.get("updated_at") else None,
            }
            for r in rows
        ]
    }
