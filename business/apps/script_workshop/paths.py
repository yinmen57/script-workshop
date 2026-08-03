"""剧本工坊包内路径。"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PACKAGE_RELPATH = "business/apps/script_workshop"
PROMPTS_ROOT = PACKAGE_ROOT / "prompts"
KNOWLEDGE_ROOT = PACKAGE_ROOT / "knowledge"


def read_prompt(agent_id: str, filename: str = "system.md") -> str:
    path = PROMPTS_ROOT / agent_id / filename
    return path.read_text(encoding="utf-8")
