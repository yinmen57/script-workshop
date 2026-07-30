"""资产唯一键规范化。"""

from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")


def normalize_key(name: str) -> str:
    text = _WS_RE.sub("", (name or "").strip().lower())
    if not text:
        raise ValueError("名称不能为空")
    return text


def character_key(name: str) -> str:
    return normalize_key(name)


def scene_key(name: str) -> str:
    """地点身份业务键：剧本内唯一。"""
    return normalize_key(name)


def prop_key(owner_key: str | None, prop_type: str, prop_name: str) -> str:
    owner = owner_key or "_scene"
    return f"{owner}::{normalize_key(prop_type)}::{normalize_key(prop_name)}"
