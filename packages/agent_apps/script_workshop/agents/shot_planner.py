from packages.agent_apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="shot-planner",
    name="分镜规划 Agent",
    role="specialist",
    description="规划分镜、划分视频片段并生成成片提示词。",
    tools=(
        "inspect",
        "plan-shots",
        "plan-video-segments",
        "generate-video-prompts",
        "retrieve",
    ),
    namespaces=(
        "script/craft/prompting",
        "script/craft/cinematography",
        "script/craft/visual-style",
    ),
    max_steps=10,
)
