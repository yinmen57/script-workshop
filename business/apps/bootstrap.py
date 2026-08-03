"""业务应用注册入口：进程启动时调用，框架本身不 import 具体业务包。"""

from __future__ import annotations

from framework.agent_apps.registry import register_apps


def register_business_apps() -> None:
    """注册本仓库全部业务 Agent 应用。"""
    from business.apps.script_workshop import build_app_spec

    register_apps([build_app_spec])
