"""剧本业务用的 Chat 调用与 JSON 解析。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from packages.adapters.llm_openai import OpenAICompatibleChatAdapter
from packages.domain.errors import ValidationAppError
from packages.infra.config import get_settings

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKSHOP = _REPO_ROOT / "apps-space" / "script-workshop"

_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def load_prompt(relative_path: str) -> str:
    path = _WORKSHOP / relative_path
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


def chat_adapter() -> OpenAICompatibleChatAdapter:
    settings = get_settings()
    return OpenAICompatibleChatAdapter(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
        timeout_ms=int(settings.llm_timeout * 1000),
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
    result = await chat_adapter().chat(messages)
    return extract_json_object(result.get("content") or "")
