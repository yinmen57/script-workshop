from business.apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="parser",
    name="剧本解析 Agent",
    role="specialist",
    description="提取风格圣经、人物、归属道具与场景结构。",
    tools=("inspect", "parse-script", "parse-structure", "retrieve"),
    namespaces=("script/craft/prompting",),
    max_steps=6,
    sample_prompts=(
        "把这份剧本拆开，把人物、道具和整体风格抠出来",
        "先别用大模型，按规则把集和场次粗切一下就行",
        "看看解析弄好了没有，人物道具齐不齐",
    ),
)
