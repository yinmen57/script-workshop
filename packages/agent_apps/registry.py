"""应用注册表：代码声明的 App，替代 YAML 扫描运行时。"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from packages.domain.errors import NotFoundError, ValidationAppError

_SPLIT_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)
_apps: dict[str, dict[str, Any]] = {}
_loaded = False


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _count_knowledge_entries(corpus_dir: Path) -> int:
    total = 0
    for md_file in sorted(corpus_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        total += sum(1 for block in _SPLIT_RE.split(text) if block.strip())
    return total


def _load_knowledge(workspace: Path) -> list[dict[str, Any]]:
    """读取 knowledge/manifest.yaml；无目录则空列表。"""
    knowledge_dir = workspace / "knowledge"
    if not knowledge_dir.is_dir():
        return []
    manifest_path = knowledge_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValidationAppError("knowledge/ 存在时必须提供 manifest.yaml")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValidationAppError("knowledge/manifest.yaml 顶层必须是对象")
    items = data.get("namespaces") or []
    if not isinstance(items, list) or not items:
        raise ValidationAppError("knowledge/manifest.yaml 必须声明 namespaces 列表")

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValidationAppError(f"knowledge namespaces[{index}] 必须是对象")
        namespace = item.get("namespace")
        sub_dir = item.get("dir")
        if not isinstance(namespace, str) or not namespace.strip():
            raise ValidationAppError(f"knowledge namespaces[{index}] 缺少 namespace")
        if not isinstance(sub_dir, str) or not sub_dir.strip():
            raise ValidationAppError(f"knowledge namespaces[{index}] 缺少 dir")
        namespace = namespace.strip()
        sub_dir = sub_dir.strip().replace("\\", "/")
        if namespace in seen:
            raise ValidationAppError(f"knowledge namespace 重复：{namespace}")
        seen.add(namespace)
        corpus_dir = knowledge_dir / sub_dir
        if not corpus_dir.is_dir():
            raise ValidationAppError(f"知识库语料目录不存在：knowledge/{sub_dir}")
        description = item.get("description") or ""
        result.append(
            {
                "namespace": namespace,
                "dir": sub_dir,
                "description": (description or "").strip()
                if isinstance(description, str)
                else "",
                "entry_count": _count_knowledge_entries(corpus_dir),
                "source_path": "knowledge/manifest.yaml",
            }
        )
    return result


def _finalize_app(spec: dict[str, Any]) -> dict[str, Any]:
    workspace = Path(spec["workspace_path"])
    if not workspace.is_dir():
        raise ValidationAppError(f"应用工作区不存在：{workspace}")
    knowledge = _load_knowledge(workspace)
    knowledge_ns = {item["namespace"] for item in knowledge}
    agents = []
    for raw in spec["agents"]:
        agent = dict(raw)
        for ns in agent.get("namespaces") or []:
            if ns not in knowledge_ns:
                raise ValidationAppError(
                    f"agents/{agent['agent_id']} 引用了未声明命名空间：{ns}"
                )
        # prompts / source_path 由各 AgentSpec 自带
        agent.setdefault("prompts", [])
        agents.append(agent)

    coordinators = [a for a in agents if a["role"] == "coordinator"]
    if len(coordinators) != 1:
        raise ValidationAppError("应用必须且只能有一个 coordinator")
    if coordinators[0]["agent_id"] != spec["coordinator"]:
        raise ValidationAppError("coordinator 必须指向唯一协调 Agent")

    return {
        **spec,
        "agents": agents,
        "knowledge": knowledge,
        "load_status": "ready",
        "validation_error": None,
        "loaded_at": _now(),
        "coordinator_agent_id": spec["coordinator"],
    }


def register_builtin_apps() -> None:
    """启动时注册内置应用。"""
    global _loaded
    from packages.agent_apps.script_workshop import build_app_spec

    apps = [build_app_spec()]
    registry: dict[str, dict[str, Any]] = {}
    for spec in apps:
        try:
            registry[spec["slug"]] = _finalize_app(spec)
        except Exception as exc:  # noqa: BLE001
            registry[spec["slug"]] = {
                **spec,
                "agents": [],
                "tools": [],
                "knowledge": [],
                "load_status": "error",
                "validation_error": str(exc),
                "loaded_at": _now(),
                "coordinator_agent_id": "",
            }
    _apps.clear()
    _apps.update(registry)
    _loaded = True


def _ensure_loaded() -> None:
    if not _loaded:
        register_builtin_apps()


def list_workspaces(tenant_id: str) -> dict[str, Any]:
    _ensure_loaded()
    items = []
    for snap in sorted(_apps.values(), key=lambda x: x["slug"]):
        if snap.get("load_status") == "ready" and snap.get("tenant_id") != tenant_id:
            continue
        items.append(
            {
                "slug": snap["slug"],
                "name": snap["name"],
                "description": snap.get("description") or "",
                "workspace_path": snap["workspace_path"],
                "coordinator_agent_id": snap.get("coordinator_agent_id") or "",
                "agent_count": len(snap.get("agents") or []),
                "load_status": snap["load_status"],
                "validation_error": snap.get("validation_error"),
                "loaded_at": snap.get("loaded_at"),
            }
        )
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": max(len(items), 1),
    }


def get_workspace(tenant_id: str, slug: str) -> dict[str, Any]:
    _ensure_loaded()
    snap = _apps.get(slug)
    if snap is None:
        raise NotFoundError("workspace not found")
    if (
        snap.get("load_status") == "ready"
        and snap.get("tenant_id")
        and snap["tenant_id"] != tenant_id
    ):
        raise NotFoundError("workspace not found")

    agents_out = []
    for a in snap.get("agents") or []:
        tool_ids = list(a.get("allowed_tools") or [])
        if a.get("role") == "coordinator":
            for s in snap.get("agents") or []:
                if s.get("role") == "specialist":
                    tool_ids.append(f"delegate_to_{s['agent_id']}")
        agents_out.append(
            {
                "agent_id": a["agent_id"],
                "name": a["name"],
                "role": a["role"],
                "description": a.get("description") or "",
                "system_prompt_path": a.get("system_prompt_path") or "",
                "allowed_tools": tool_ids,
                "namespaces": a.get("namespaces") or [],
                "max_steps": a.get("max_steps") or 8,
                "source_path": a.get("source_path") or "",
                "prompts": a.get("prompts") or [],
            }
        )
    knowledge_out = []
    for item in snap.get("knowledge") or []:
        used_by = [
            a["agent_id"]
            for a in agents_out
            if item["namespace"] in (a.get("namespaces") or [])
        ]
        knowledge_out.append({**item, "used_by_agents": used_by})
    return {
        "slug": snap["slug"],
        "name": snap["name"],
        "description": snap.get("description") or "",
        "workspace_path": snap["workspace_path"],
        "coordinator_agent_id": snap.get("coordinator_agent_id") or "",
        "collaboration_mode": snap.get("collaboration_mode"),
        "load_status": snap["load_status"],
        "validation_error": snap.get("validation_error"),
        "loaded_at": snap.get("loaded_at"),
        "max_steps": snap.get("max_steps"),
        "model": snap.get("model") or {},
        "agents": agents_out,
        "tools": snap.get("tools") or [],
        "knowledge": knowledge_out,
    }


def get_runtime_app(tenant_id: str, slug: str) -> dict[str, Any]:
    """供 chat / LangGraph 运行时使用。"""
    _ensure_loaded()
    snap = _apps.get(slug)
    if snap is None or snap.get("load_status") != "ready":
        raise NotFoundError("workspace not found or not ready")
    if snap.get("tenant_id") != tenant_id:
        raise NotFoundError("workspace not found or not ready")
    coordinator = next(
        (a for a in snap["agents"] if a["role"] == "coordinator"),
        None,
    )
    if coordinator is None:
        raise ValidationAppError("coordinator agent missing")
    return {
        "slug": snap["slug"],
        "tenant_id": snap["tenant_id"],
        "name": snap["name"],
        "status": "enabled",
        "workspace_path": snap["workspace_path"],
        "coordinator_agent_id": coordinator["agent_id"],
        "system_prompt": coordinator["system_prompt_content"],
        "system_prompt_path": coordinator.get("system_prompt_path") or "",
        "model": snap["model"],
        "max_steps": int(coordinator.get("max_steps") or snap.get("max_steps") or 8),
        "agents": list(snap["agents"]),
        "tools": list(snap.get("tools") or []),
        "collaboration_mode": snap.get("collaboration_mode"),
    }
