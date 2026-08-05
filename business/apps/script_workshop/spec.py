"""剧本工坊 AgentSpec：绑定本包路径的框架 AgentSpec 工厂。"""

from __future__ import annotations

from framework.agent_apps.spec import AgentSpec as FrameworkAgentSpec
from business.apps.script_workshop.paths import PACKAGE_RELPATH, PACKAGE_ROOT


def AgentSpec(  # noqa: N802 与历史用法一致：AgentSpec(...)
    *,
    agent_id: str,
    name: str,
    role: str,
    description: str,
    tools: tuple[str, ...],
    namespaces: tuple[str, ...] = (),
    max_steps: int = 8,
    system_prompt_file: str = "system.md",
    thinking: bool = False,
    sample_prompts: tuple[str, ...] = (),
) -> FrameworkAgentSpec:
    return FrameworkAgentSpec(
        agent_id=agent_id,
        name=name,
        role=role,
        description=description,
        tools=tools,
        package_root=PACKAGE_ROOT,
        package_relpath=PACKAGE_RELPATH,
        namespaces=namespaces,
        max_steps=max_steps,
        system_prompt_file=system_prompt_file,
        thinking=thinking,
        sample_prompts=sample_prompts,
    )
