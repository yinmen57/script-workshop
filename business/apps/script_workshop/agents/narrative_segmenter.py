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
    sample_prompts=(
        "按剧情把每一集切成一段段戏，存进库里",
        "切完之后，把项目知识库也建一下",
        "看看各集场次切好了没有",
    ),
)
