from business.apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="parser",
    name="剧本解析 Agent",
    role="specialist",
    description="提取风格圣经、人物、归属道具与场景结构。",
    tools=("inspect", "parse-script", "parse-structure", "retrieve"),
    namespaces=("script/craft/prompting",),
    max_steps=6,
)
