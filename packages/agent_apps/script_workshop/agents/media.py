from packages.agent_apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="media",
    name="媒体生成 Agent",
    role="specialist",
    description="提交生图/生视频任务并查询状态。",
    tools=(
        "inspect",
        "render-material-image",
        "render-video",
        "retrieve",
    ),
    namespaces=("script/craft/visual-style",),
    max_steps=8,
)
