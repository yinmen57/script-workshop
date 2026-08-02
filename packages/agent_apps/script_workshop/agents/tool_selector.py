from packages.agent_apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="tool-selector",
    name="工具选择 Agent",
    role="specialist",
    description="只读巡检并判断下一步工具/Agent，不执行写操作。",
    tools=("inspect",),
    max_steps=4,
)
