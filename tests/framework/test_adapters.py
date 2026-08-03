# -*- coding: utf-8 -*-
"""adapters：HTTP / Qdrant 行为（MockTransport）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

from framework.adapters.embedding_openai import OpenAICompatibleEmbeddingAdapter
from framework.adapters.llm_openai import OpenAICompatibleChatAdapter
from framework.adapters.rerank_xinference import XinferenceRerankAdapter
from framework.adapters.vector_qdrant import QdrantVectorStoreAdapter


@pytest.mark.asyncio
async def test_chat_adapter_chat_and_ping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200,
            json={
                "model": "m",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            },
        )

    transport = httpx.MockTransport(handler)
    adapter = OpenAICompatibleChatAdapter(
        "https://example.com/v1/", "key", "m", timeout_ms=5000
    )
    assert adapter.base_url == "https://example.com/v1"

    # 替换 AsyncClient，使适配器走 MockTransport
    real_client = httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    import framework.adapters.llm_openai as mod

    original = mod.httpx.AsyncClient
    mod.httpx.AsyncClient = PatchedClient  # type: ignore[misc,assignment]
    try:
        ping = await adapter.ping()
        assert ping["ok"] is True
        result = await adapter.chat([{"role": "user", "content": "q"}])
        assert result["content"] == "hi"
        assert result["usage"]["total_tokens"] == 3
    finally:
        mod.httpx.AsyncClient = original  # type: ignore[misc]


@pytest.mark.asyncio
async def test_chat_adapter_stream() -> None:
    body = (
        b'data: {"choices":[{"delta":{"content":"A"}}]}\n\n'
        b"data: not-json\n\n"
        b'data: {"usage":{"prompt_tokens":1,"completion_tokens":1,"total_tokens":2}}\n\n'
        b"data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    transport = httpx.MockTransport(handler)
    adapter = OpenAICompatibleChatAdapter("https://example.com/v1", "k", "m")

    import framework.adapters.llm_openai as mod

    real_client = mod.httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = PatchedClient  # type: ignore[misc,assignment]
    try:
        events = [event async for event in adapter.stream_chat([{"role": "user", "content": "q"}])]
    finally:
        mod.httpx.AsyncClient = real_client  # type: ignore[misc]
    assert events[0] == {"type": "delta", "text": "A"}
    assert events[1]["type"] == "usage"
    assert events[1]["usage"]["total_tokens"] == 2


@pytest.mark.asyncio
async def test_embedding_adapter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
        )

    transport = httpx.MockTransport(handler)
    adapter = OpenAICompatibleEmbeddingAdapter("https://example.com/", "k", "emb")
    import framework.adapters.embedding_openai as mod

    real_client = mod.httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = PatchedClient  # type: ignore[misc,assignment]
    try:
        vectors = await adapter.embed(["a", "b"])
        ping = await adapter.ping()
    finally:
        mod.httpx.AsyncClient = real_client  # type: ignore[misc]
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert ping == {"ok": True, "dimension": 2}


@pytest.mark.asyncio
async def test_rerank_adapter() -> None:
    assert await XinferenceRerankAdapter("https://x", "r").rerank("q", []) == []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.9},
                ]
            },
        )

    transport = httpx.MockTransport(handler)
    adapter = XinferenceRerankAdapter("https://example.com/", "rerank", api_key="k")
    import framework.adapters.rerank_xinference as mod

    real_client = mod.httpx.AsyncClient

    class PatchedClient(real_client):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    mod.httpx.AsyncClient = PatchedClient  # type: ignore[misc,assignment]
    try:
        ranked = await adapter.rerank("q", ["doc0", "doc1"], top_n=1)
    finally:
        mod.httpx.AsyncClient = real_client  # type: ignore[misc]
    assert ranked == [{"index": 0, "score": 0.9, "document": "doc0"}]


def test_qdrant_vector_adapter() -> None:
    client = MagicMock()
    client.get_collections.return_value = SimpleNamespace(
        collections=[SimpleNamespace(name="exists")]
    )
    adapter = QdrantVectorStoreAdapter(client)
    adapter.ensure_collection("exists", 8)
    client.create_collection.assert_not_called()

    adapter.ensure_collection("new", 16)
    client.create_collection.assert_called_once()
    adapter.delete_by_doc("exists", "t1", "kb1", "d1")
    client.delete.assert_called_once()
