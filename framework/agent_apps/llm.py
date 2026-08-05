"""从 model_config（AI Key 配置页）构建 LangChain ChatOpenAI。"""

from __future__ import annotations

from typing import Any, Mapping

from langchain_core.messages import AIMessageChunk, BaseMessageChunk
from langchain_openai import ChatOpenAI
from langchain_openai.chat_models import base as openai_chat_base

from framework.domain.errors import ValidationAppError
from framework.governance.model_service import load_runtime_model

# LangChain ChatOpenAI 官方不保留第三方 reasoning_content；方舟 DeepSeek 需要它做思考流式。
_ORIG_CONVERT_DELTA = openai_chat_base._convert_delta_to_message_chunk


def _convert_delta_to_message_chunk_with_reasoning(
    _dict: Mapping[str, Any], default_class: type[BaseMessageChunk]
) -> BaseMessageChunk:
    chunk = _ORIG_CONVERT_DELTA(_dict, default_class)
    if not isinstance(chunk, AIMessageChunk):
        return chunk
    for key in ("reasoning_content", "reasoning"):
        val = _dict.get(key)
        if isinstance(val, str) and val:
            # 写入 additional_kwargs，供 runtime callback 读取
            chunk.additional_kwargs[key] = val
            break
    return chunk


# 进程内打一次补丁即可
if (
    openai_chat_base._convert_delta_to_message_chunk
    is not _convert_delta_to_message_chunk_with_reasoning
):
    openai_chat_base._convert_delta_to_message_chunk = (
        _convert_delta_to_message_chunk_with_reasoning
    )


async def build_chat_model(
    *,
    tenant_id: str,
    primary: str = "default",
    timeout_ms: int | None = None,
    thinking: bool = False,
) -> ChatOpenAI:
    if primary != "default":
        raise ValidationAppError(f"未知模型逻辑名：{primary}（当前仅支持 default）")
    creds = await load_runtime_model(tenant_id, "chat")
    timeout = (timeout_ms or int(creds["timeout_seconds"] * 1000)) / 1000.0
    # 方舟 DeepSeek：显式开关深度思考，避免默认思考挤空 content
    thinking_type = "enabled" if thinking else "disabled"
    return ChatOpenAI(
        model=creds["model_name"],
        api_key=creds["api_key"],
        base_url=creds["base_url"],
        timeout=timeout,
        temperature=0,
        # 开启 token 流，供 callback 推 WebSocket reasoning / delta
        streaming=True,
        extra_body={"thinking": {"type": thinking_type}},
    )
