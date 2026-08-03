"""剧本工坊应用包：Agent / Prompt / 工具 / 知识库统一管理。"""

from __future__ import annotations

from typing import Any

from business.apps.script_workshop.agents import ALL_AGENTS
from business.apps.script_workshop.app import APP
from business.apps.script_workshop.paths import PACKAGE_ROOT
from business.apps.script_workshop.tool_meta import TOOL_META


def build_app_spec() -> dict[str, Any]:
    """组装 registry / runtime 所需的应用规格。"""
    agents = [spec.to_runtime_dict() for spec in ALL_AGENTS]
    tools = [
        {
            "id": tool_id,
            "name": tool_id,
            "description": desc,
            "entrypoint": f"business.apps.script_workshop.tools:{func_name}",
            "risk_level": "low",
            "parameters": {},
            "source_path": "business/apps/script_workshop/tools.py",
        }
        for tool_id, (func_name, desc) in TOOL_META.items()
    ]
    return {
        **APP,
        "agents": agents,
        "tools": tools,
        "workspace_path": str(PACKAGE_ROOT),
    }


__all__ = ["build_app_spec", "ALL_AGENTS", "APP", "PACKAGE_ROOT"]
