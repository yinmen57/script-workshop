"""多 Agent 应用框架：LangGraph 运行时 + 应用注册表。

业务应用在 business.apps 下声明，启动时 register_apps 注入。
"""

from framework.agent_apps.registry import (
    clear_apps,
    get_runtime_app,
    get_workspace,
    list_workspaces,
    register_app,
    register_apps,
)
from framework.agent_apps.spec import AgentSpec

__all__ = [
    "AgentSpec",
    "clear_apps",
    "get_runtime_app",
    "get_workspace",
    "list_workspaces",
    "register_app",
    "register_apps",
]
