from business.apps.script_workshop.spec import AgentSpec

SPEC = AgentSpec(
    agent_id="router",
    name="协调 Agent",
    role="coordinator",
    description="ReAct 路由，委派专业 Agent 完成任务。",
    tools=("inspect", "list-jobs", "confirm", "revert"),
    max_steps=16,
    thinking=True,
    sample_prompts=(
        "看看这个项目做到哪一步了，接下来该干啥",
        "从这场戏接着往下做，做到能出视频为止",
        "生图生视频的任务跑完了吗，队列里还有没有在做的",
    ),
)
