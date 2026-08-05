"""剧本工坊全部 Agent；顺序即管理端展示顺序。"""

from business.apps.script_workshop.agents.asset_planner import SPEC as asset_planner
from business.apps.script_workshop.agents.media import SPEC as media
from business.apps.script_workshop.agents.narrative_segmenter import (
    SPEC as narrative_segmenter,
)
from business.apps.script_workshop.agents.parser import SPEC as parser
from business.apps.script_workshop.agents.router import SPEC as router
from business.apps.script_workshop.agents.shot_planner import SPEC as shot_planner

ALL_AGENTS = (
    router,
    parser,
    narrative_segmenter,
    asset_planner,
    shot_planner,
    media,
)

__all__ = ["ALL_AGENTS"]
