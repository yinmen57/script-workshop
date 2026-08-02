from packages.agent_apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="router",
    name="协调 Agent",
    role="coordinator",
    description="ReAct 路由，委派专业 Agent 完成任务。",
    tools=("inspect", "confirm", "revert"),
    max_steps=16,
)
