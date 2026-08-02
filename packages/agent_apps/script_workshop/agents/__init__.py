"""剧本工坊全部 Agent；顺序即管理端展示顺序。"""

from packages.agent_apps.script_workshop.agents.asset_planner import SPEC as asset_planner
from packages.agent_apps.script_workshop.agents.media import SPEC as media
from packages.agent_apps.script_workshop.agents.narrative_segmenter import (
    SPEC as narrative_segmenter,
)
from packages.agent_apps.script_workshop.agents.parser import SPEC as parser
from packages.agent_apps.script_workshop.agents.router import SPEC as router
from packages.agent_apps.script_workshop.agents.shot_planner import SPEC as shot_planner
from packages.agent_apps.script_workshop.agents.tool_selector import SPEC as tool_selector

ALL_AGENTS = (
    router,
    tool_selector,
    parser,
    narrative_segmenter,
    asset_planner,
    shot_planner,
    media,
)

__all__ = ["ALL_AGENTS"]
