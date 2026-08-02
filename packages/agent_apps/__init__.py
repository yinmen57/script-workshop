"""多 Agent 应用框架：LangGraph 运行时 + 应用注册表。

各业务应用见子包，例如 packages.agent_apps.script_workshop。
"""

from packages.agent_apps.registry import (
    get_runtime_app,
    get_workspace,
    list_workspaces,
    register_builtin_apps,
)

__all__ = [
    "get_runtime_app",
    "get_workspace",
    "list_workspaces",
    "register_builtin_apps",
]
