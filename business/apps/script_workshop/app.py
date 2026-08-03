"""应用级元数据。"""

from __future__ import annotations

APP = {
    "slug": "script-workshop",
    "name": "剧本工坊",
    "description": "多 Agent 协作：协调 Agent 调度解析、物料、分镜与媒体生成能力。",
    "tenant_id": "ten_demo",
    "model": {"primary": "default", "timeout_ms": 60000},
    "coordinator": "router",
    "max_steps": 16,
    "collaboration_mode": "langgraph_multi_agent",
}
