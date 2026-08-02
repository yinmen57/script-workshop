"""工具 ID -> (Python 函数名, 描述)。"""

TOOL_META: dict[str, tuple[str, str]] = {
    "inspect": (
        "inspect",
        "只读巡检项目进度与产物状态；模糊目标时先查 scope=progress。",
    ),
    "parse-script": (
        "parse_script",
        "解析剧本为风格圣经、人物与归属道具，并顺带规则切结构。",
    ),
    "parse-structure": (
        "parse_structure",
        "按规则粗切集与叙事空间，不调用 LLM。",
    ),
    "segment-narrative": (
        "segment_narrative",
        "用 LLM 判定叙事空间语义边界并落库。",
    ),
    "index-narrative-knowledge": (
        "index_narrative_knowledge",
        "从工作台事实重建项目知识库检索副本。",
    ),
    "generate-material-prompts": (
        "generate_material_prompts",
        "为人物与归属道具生成物料提示词。",
    ),
    "plan-shots": (
        "plan_shots",
        "按叙事空间规划分镜；可指定 narrative_space_id。",
    ),
    "plan-video-segments": (
        "plan_video_segments",
        "把叙事空间分镜编成视频片段（单段不超过 15 秒）。",
    ),
    "generate-video-prompts": (
        "generate_video_prompts",
        "按视频片段生成成片视频提示词。",
    ),
    "render-material-image": (
        "render_material_image",
        "为已确认物料提示词生图（赏舞，产生费用）。",
    ),
    "render-video": (
        "render_video",
        "为已确认成片提示词生成视频（赏舞，产生费用）。",
    ),
    "confirm": (
        "confirm",
        "将产物标记为 confirmed（定版）。",
    ),
    "revert": (
        "revert",
        "按 revision_id 反悔写回历史快照。",
    ),
}
