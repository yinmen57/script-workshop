from business.apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="narrative-segmenter",
    name="叙事切分 Agent",
    role="specialist",
    description="判定集内叙事空间语义边界并入库。",
    tools=(
        "inspect",
        "segment-narrative",
        "index-narrative-knowledge",
        "retrieve",
    ),
    namespaces=(
        "script/craft/prompting",
        "script/craft/cinematography",
    ),
    max_steps=6,
)
