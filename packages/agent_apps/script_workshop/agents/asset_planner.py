from packages.agent_apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="asset-planner",
    name="物料规划 Agent",
    role="specialist",
    description="为人物与归属道具生成一致性物料提示词。",
    tools=("inspect", "generate-material-prompts", "retrieve"),
    namespaces=(
        "script/craft/prompting",
        "script/craft/visual-style",
    ),
    max_steps=8,
)
