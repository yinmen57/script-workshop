# -*- coding: utf-8 -*-
"""agent_apps.runtime：消息转换与 usage 累加（纯函数）。"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from framework.agent_apps import runtime as runtime_mod


def test_message_text_variants() -> None:
    assert runtime_mod._message_text(None) == ""
    assert runtime_mod._message_text("hi") == "hi"
    assert (
        runtime_mod._message_text(
            [{"type": "text", "text": "a"}, "b", {"type": "image"}]
        )
        == "ab"
    )
    assert runtime_mod._message_text(12) == "12"


def test_to_lc_messages_filters_roles() -> None:
    msgs = runtime_mod._to_lc_messages(
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "ignored"},
        ]
    )
    assert [type(m) for m in msgs] == [SystemMessage, HumanMessage, AIMessage]
    assert msgs[2].content == "a"


def test_accumulate_usage() -> None:
    total = {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}
    runtime_mod._accumulate_usage(
        total, {"prompt_tokens": 4, "completion_tokens": None, "total_tokens": 5}
    )
    assert total == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 8}
