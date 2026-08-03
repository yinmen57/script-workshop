# -*- coding: utf-8 -*-
"""governance：model / chat / vector 纯函数。"""

from __future__ import annotations

import pytest

from framework.domain.errors import ValidationAppError
from framework.governance import chat_service, model_service, vector_namespace_service


def test_validate_model_fields() -> None:
    model_service._validate_model_fields(model_type="chat", dimension=None)
    model_service._validate_model_fields(model_type="embedding", dimension=1024)
    with pytest.raises(ValidationAppError):
        model_service._validate_model_fields(model_type="embedding", dimension=None)
    with pytest.raises(ValidationAppError):
        model_service._validate_model_fields(model_type="rerank", dimension=8)
    with pytest.raises(ValidationAppError, match="provider"):
        model_service._validate_model_fields(
            model_type="image", dimension=None, provider="unknown"
        )
    model_service._validate_model_fields(
        model_type="image", dimension=None, provider="volcengine_ark"
    )
    model_service._validate_model_fields(
        model_type="audio", dimension=None, provider="openai_compatible"
    )


def test_compress_history_excerpt() -> None:
    from framework.governance import chat_service

    text = chat_service._compress_history_excerpt(
        [
            {"role": "user", "content": "把第 1 集语义切分"},
            {"role": "assistant", "content": "已完成叙事空间切分"},
            {"role": "system", "content": "忽略"},
        ],
        prior_summary="更早：解析过剧本",
    )
    assert "更早：解析过剧本" in text
    assert "用户: 把第 1 集语义切分" in text
    assert "助手: 已完成叙事空间切分" in text
    assert "忽略" not in text


def test_normalize_base_url() -> None:
    assert (
        model_service._normalize_base_url("https://ark.example.com/api/v3/")
        == "https://ark.example.com/api/v3"
    )
    with pytest.raises(ValidationAppError, match="http:// 或 https://"):
        model_service._normalize_base_url("ark.example.com/api/v3")
    with pytest.raises(ValidationAppError, match="不能为空"):
        model_service._normalize_base_url("  ")


def test_parse_extra_and_row_to_public() -> None:
    assert model_service._parse_extra('{"a": 1}') == {"a": 1}
    assert model_service._parse_extra({"b": 2}) == {"b": 2}
    assert model_service._parse_extra(None) == {}
    public = model_service._row_to_public(
        {
            "id": "m1",
            "tenant_id": "t1",
            "name": "chat",
            "provider": "openai",
            "model_type": "chat",
            "model_name": "gpt",
            "base_url": "https://x",
            "dimension": None,
            "extra": {"is_default": True, "temperature": 0.2},
            "status": "enabled",
            "api_key_cipher": "cipher",
            "created_at": None,
            "updated_at": None,
        }
    )
    assert public["has_api_key"] is True
    assert public["is_default"] is True
    assert "is_default" not in public["extra"]
    assert public["extra"]["temperature"] == 0.2


def test_merge_extra() -> None:
    merged = model_service._merge_extra(
        {"extra": {"a": 1}, "is_default": True},
        {"a": 0, "b": 2},
    )
    assert merged == {"a": 1, "b": 2, "is_default": True}


def test_format_selection_block() -> None:
    assert chat_service._format_selection_block(None) == ""
    text = chat_service._format_selection_block(
        {
            "project_id": "p1",
            "selection": {"type": "shot", "id": "s1", "title": "开场"},
        }
    )
    assert "project_id: p1" in text
    assert "id: s1" in text
    assert "title: 开场" in text


def test_resolve_run_agent() -> None:
    app = {
        "agents": [
            {"agent_id": "router", "role": "coordinator"},
            {"agent_id": "parser", "role": "specialist"},
        ]
    }
    assert chat_service._resolve_run_agent(app, None) == (None, None)
    agent_id, agent = chat_service._resolve_run_agent(app, "parser")
    assert agent_id == "parser"
    assert agent["role"] == "specialist"
    with pytest.raises(ValidationAppError, match="不存在"):
        chat_service._resolve_run_agent(app, "missing")


def test_collection_name_stable() -> None:
    a = vector_namespace_service._collection_name("tenant:ns")
    b = vector_namespace_service._collection_name("tenant:ns")
    c = vector_namespace_service._collection_name("other")
    assert a == b
    assert a.startswith("ns_")
    assert a != c


def test_safe_metadata_strips_reserved() -> None:
    safe = vector_namespace_service._safe_metadata(
        {
            "tenant_id": "hack",
            "content": "hack",
            "title": "ok",
            1: "bad-key",
        }
    )
    assert safe == {"title": "ok"}


def test_chunk_text() -> None:
    assert vector_namespace_service._chunk_text("  ", 10, 2) == []
    assert vector_namespace_service._chunk_text("short", 10, 2) == ["short"]
    chunks = vector_namespace_service._chunk_text("abcdefghijKLMN", chunk_size=5, overlap=2)
    assert chunks[0] == "abcde"
    assert chunks[1] == "defgh"
    assert "".join(c[0] for c in chunks)  # 非空
    assert len(chunks) >= 3
