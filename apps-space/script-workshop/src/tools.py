"""剧本工坊工具入口：透传调用 packages/business_script（与 /script-biz 共用服务）。

同进程内不走 HTTP 自调用，避免单 worker 死锁；租户由 agent_runtime 注入 tool_context。
"""

from __future__ import annotations

from typing import Any

from packages.business_script import material_service, parse_service
from packages.core.tool_context import require_tenant_id
from packages.infra.db import get_session_factory


async def parse_script(project_id: str, script_text: str) -> dict[str, Any]:
    """B0：解析剧本并创建人物、归属道具和场景资产。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        return await parse_service.parse_project(
            session,
            tenant_id,
            project_id,
            script_text=script_text,
        )


async def generate_material_prompts(project_id: str) -> dict[str, Any]:
    """B0：为人物和归属道具生成可编辑的物料提示词。"""
    tenant_id = require_tenant_id()
    async with get_session_factory()() as session:
        return await material_service.generate_material_prompts(
            session, tenant_id, project_id
        )


async def plan_shots(project_id: str) -> dict[str, Any]:
    """B1：根据已确认资产规划分镜。"""
    del project_id
    raise NotImplementedError("plan_shots 属于 B1，尚未实现")


async def render_material_image(material_prompt_id: str) -> dict[str, Any]:
    """B1：通过 SD 图像服务生成物料图。"""
    del material_prompt_id
    raise NotImplementedError("render_material_image 属于 B1，尚未实现")


async def render_video(video_prompt_id: str) -> dict[str, Any]:
    """B1：通过 SD 视频服务生成分镜视频。"""
    del video_prompt_id
    raise NotImplementedError("render_video 属于 B1，尚未实现")
