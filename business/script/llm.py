"""剧本业务用的 Chat 调用与 JSON 解析。凭证来自 AI Key 配置页。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from framework.adapters.llm_openai import OpenAICompatibleChatAdapter
from framework.core.tool_context import require_tenant_id
from framework.domain.errors import ValidationAppError
from framework.governance.model_service import load_runtime_model

# 统一走业务 Agent 应用包内 prompts/
_PROMPTS_ROOT = (
    Path(__file__).resolve().parents[1]
    / "apps"
    / "script_workshop"
    / "prompts"
)

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def load_prompt(relative_path: str) -> str:
    """relative_path 形如 parser/system.md、shot-planner/plan-shots.md。"""
    path = _PROMPTS_ROOT / relative_path
    if not path.is_file():
        raise ValidationAppError(f"提示词文件不存在：{relative_path}")
    return path.read_text(encoding="utf-8")


def render_prompt(template: str, **kwargs: Any) -> str:
    text = template
    for key, value in kwargs.items():
        token = "{" + key + "}"
        if isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, indent=2)
        else:
            rendered = "" if value is None else str(value)
        text = text.replace(token, rendered)
    return text


async def chat_adapter() -> OpenAICompatibleChatAdapter:
    tenant_id = require_tenant_id()
    creds = await load_runtime_model(tenant_id, "chat")
    return OpenAICompatibleChatAdapter(
        creds["base_url"],
        creds["api_key"],
        creds["model_name"],
        timeout_ms=int(creds["timeout_seconds"] * 1000),
    )


def extract_json_object(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise ValidationAppError("模型未返回内容")
    match = _FENCE_RE.search(text)
    if match:
        text = match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValidationAppError("模型输出不是合法 JSON") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValidationAppError(f"模型 JSON 解析失败：{exc}") from exc
    if not isinstance(data, dict):
        raise ValidationAppError("模型输出顶层必须是对象")
    return data


async def chat_json(messages: list[dict[str, Any]]) -> dict[str, Any]:
    adapter = await chat_adapter()
    result = await adapter.chat(messages)
    return extract_json_object(result.get("content") or "")
