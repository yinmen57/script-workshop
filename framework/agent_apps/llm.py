"""从 model_config（AI Key 配置页）构建 LangChain ChatOpenAI。"""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from framework.domain.errors import ValidationAppError
from framework.governance.model_service import load_runtime_model


async def build_chat_model(
    *,
    tenant_id: str,
    primary: str = "default",
    timeout_ms: int | None = None,
) -> ChatOpenAI:
    if primary != "default":
        raise ValidationAppError(f"未知模型逻辑名：{primary}（当前仅支持 default）")
    creds = await load_runtime_model(tenant_id, "chat")
    timeout = (timeout_ms or int(creds["timeout_seconds"] * 1000)) / 1000.0
    return ChatOpenAI(
        model=creds["model_name"],
        api_key=creds["api_key"],
        base_url=creds["base_url"],
        timeout=timeout,
        temperature=0,
        # 开启 token 流，供 callback 推 SSE delta
        streaming=True,
    )
