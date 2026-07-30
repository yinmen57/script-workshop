"""业务侧提示词装配：检索工艺知识并注入 LLM 上下文。

与 Agent retrieve 共用 vector_namespace_service.search，
业务流水线不走 ReAct，但必须吃到同一套知识条目。
"""

from __future__ import annotations

from typing import Any

from packages.governance import vector_namespace_service

CRAFT_PROMPTING = "script/craft/prompting"
CRAFT_VISUAL = "script/craft/visual-style"
CRAFT_CINEMA = "script/craft/cinematography"


def format_citations(result: dict[str, Any], *, max_chars: int = 6000) -> str:
    """把检索结果压成可注入 prompt 的文本块。"""
    citations = result.get("citations") or []
    if not citations:
        return ""
    parts: list[str] = []
    used = 0
    for i, item in enumerate(citations, start=1):
        ns = item.get("namespace") or ""
        content = (item.get("content") or "").strip()
        if not content:
            continue
        block = f"[{i}] ({ns})\n{content}"
        if used + len(block) > max_chars:
            remain = max_chars - used
            if remain > 80:
                parts.append(block[:remain] + "…")
            break
        parts.append(block)
        used += len(block) + 2
    return "\n\n".join(parts)


async def retrieve_craft(
    *,
    tenant_id: str,
    namespaces: list[str],
    query: str,
    top_k: int = 5,
) -> str:
    """检索工艺知识。未登记命名空间时 search 返回空 citations，此处如实透传。"""
    result = await vector_namespace_service.search(
        tenant_id=tenant_id,
        namespaces=namespaces,
        query=query,
        top_k=top_k,
    )
    return format_citations(result)


async def assemble_parse_knowledge(*, tenant_id: str) -> str:
    """解析阶段：检索人物 / 道具提取口径。"""
    roles = await retrieve_craft(
        tenant_id=tenant_id,
        namespaces=[CRAFT_PROMPTING],
        query="roles 提取口径 人物合并 道具归属 去重",
        top_k=5,
    )
    if not roles:
        return ""
    return "## 资产提取口径\n" + roles


async def assemble_segment_knowledge(*, tenant_id: str) -> str:
    """叙事切分：场景边界与叙事结构口径。"""
    text = await retrieve_craft(
        tenant_id=tenant_id,
        namespaces=[CRAFT_PROMPTING, CRAFT_CINEMA],
        query="叙事结构 场景边界 换场 转场 情绪转折 一场戏的完整性",
        top_k=6,
    )
    if not text:
        return ""
    return "## 叙事切分规范\n" + text


async def assemble_material_knowledge(*, tenant_id: str) -> str:
    """物料提示词生成：prompting + visual-style。"""
    text = await retrieve_craft(
        tenant_id=tenant_id,
        namespaces=[CRAFT_PROMPTING, CRAFT_VISUAL],
        query="物料提示词 一致性锁定 三视图 视觉风格 分辨率 内容安全",
        top_k=6,
    )
    if not text:
        return ""
    return "## 物料生成规范\n" + text


async def assemble_shot_knowledge(*, tenant_id: str) -> str:
    """分镜规划：镜头语言 + 分镜模板节奏。"""
    text = await retrieve_craft(
        tenant_id=tenant_id,
        namespaces=[CRAFT_CINEMA, CRAFT_PROMPTING],
        query="分镜 景别 镜头语言 节奏 时长 分镜模板",
        top_k=6,
    )
    if not text:
        return ""
    return "## 分镜规范\n" + text


async def assemble_video_knowledge(*, tenant_id: str) -> str:
    """成片视频提示词：多镜合并写法 + 运镜与时长。"""
    text = await retrieve_craft(
        tenant_id=tenant_id,
        namespaces=[CRAFT_CINEMA, CRAFT_PROMPTING, CRAFT_VISUAL],
        query="镜头组 成片 视频提示词 运镜 切换 时长 一致性锁定",
        top_k=6,
    )
    if not text:
        return ""
    return "## 成片视频规范\n" + text
