"""Qdrant VectorStore Adapter 骨架。"""

from __future__ import annotations

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm


class QdrantVectorStoreAdapter:
    def __init__(self, client: QdrantClient) -> None:
        self.client = client

    def ensure_collection(self, collection: str, dimension: int) -> None:
        names = {c.name for c in self.client.get_collections().collections}
        if collection in names:
            return
        self.client.create_collection(
            collection_name=collection,
            vectors_config=qm.VectorParams(size=dimension, distance=qm.Distance.COSINE),
        )

    def delete_by_doc(self, collection: str, tenant_id: str, kb_id: str, doc_id: str) -> None:
        self.client.delete(
            collection_name=collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[
                        qm.FieldCondition(key="tenant_id", match=qm.MatchValue(value=tenant_id)),
                        qm.FieldCondition(key="kb_id", match=qm.MatchValue(value=kb_id)),
                        qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id)),
                    ]
                )
            ),
        )
