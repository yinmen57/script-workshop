from business.apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="media",
    name="媒体生成 Agent",
    role="specialist",
    description="提交生图/生视频任务并查询状态。",
    tools=(
        "inspect",
        "list-jobs",
        "render-material-image",
        "render-video",
        "retrieve",
    ),
    namespaces=("script/craft/visual-style",),
    max_steps=8,
    sample_prompts=(
        "看看生图生视频队列现在啥情况",
        "哪些物料已经定版了、可以拿去出图",
        "成片提示词定版以后，怎么提交生视频（先说清楚再入队）",
    ),
)
