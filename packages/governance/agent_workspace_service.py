"""文件系统驱动的多 Agent 应用空间：进程内注册表 + mtime 热重载。

目录约定：
  apps-space/<app-slug>/
    app.yaml
    agents/<agent-id>/
      agent.yaml
      prompts/*.md
    tools/*.yaml
    knowledge/
      manifest.yaml
      <dir>/*.md
    src/
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from packages.domain.errors import NotFoundError, ValidationAppError
from packages.infra.config import get_settings

_AGENT_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VALID_ROLES = {"coordinator", "specialist"}
_SPLIT_RE = re.compile(r"^-{3,}\s*$", re.MULTILINE)

_lock = threading.RLock()
# slug -> 已加载快照（含 load_status / mtime）
_registry: dict[str, dict[str, Any]] = {}
_root_mtime: float | None = None


def _workspace_root() -> Path:
    settings = get_settings()
    root = Path(__file__).resolve().parents[2] / settings.agent_workspace_root
    return root.resolve()


def _dir_mtime(path: Path) -> float:
    """目录树最大 mtime，用于热重载检测。"""
    latest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            latest = max(latest, child.stat().st_mtime)
        except OSError:
            continue
    return latest


def _read_text(root: Path, relative_path: str) -> str:
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValidationAppError(f"文件路径越界：{relative_path}")
    if not candidate.is_file():
        raise ValidationAppError(f"文件不存在：{relative_path}")
    return candidate.read_text(encoding="utf-8")


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValidationAppError(f"缺少 {label}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValidationAppError(f"{label} 格式错误：{exc}") from exc
    if not isinstance(data, dict):
        raise ValidationAppError(f"{label} 顶层必须是对象")
    return data


def _count_knowledge_entries(corpus_dir: Path) -> int:
    """统计语料目录下按 --- 分隔的知识条目数。"""
    total = 0
    for md_file in sorted(corpus_dir.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        total += sum(1 for block in _SPLIT_RE.split(text) if block.strip())
    return total


def _load_knowledge(workspace: Path) -> list[dict[str, Any]]:
    """读取 knowledge/manifest.yaml；无 knowledge 目录时返回空列表。"""
    knowledge_dir = workspace / "knowledge"
    if not knowledge_dir.exists():
        return []
    if not knowledge_dir.is_dir():
        raise ValidationAppError("knowledge 必须是目录")
    manifest_path = knowledge_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValidationAppError("knowledge/ 存在时必须提供 manifest.yaml")
    manifest = _load_yaml(manifest_path, "knowledge/manifest.yaml")
    items = manifest.get("namespaces") or []
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
        if description is not None and not isinstance(description, str):
            raise ValidationAppError(
                f"knowledge namespaces[{index}] 的 description 必须是字符串"
            )
        result.append(
            {
                "namespace": namespace,
                "dir": sub_dir,
                "description": (description or "").strip(),
                "entry_count": _count_knowledge_entries(corpus_dir),
                "source_path": "knowledge/manifest.yaml",
            }
        )
    return result


def _load_tools(workspace: Path) -> list[dict[str, Any]]:
    tools_dir = workspace / "tools"
    tools: list[dict[str, Any]] = []
    if not tools_dir.exists():
        return tools
    if not tools_dir.is_dir():
        raise ValidationAppError("tools 必须是目录")
    for tool_file in sorted(tools_dir.glob("*.yaml")):
        tool = _load_yaml(tool_file, f"tools/{tool_file.name}")
        for field in ("id", "name", "entrypoint"):
            if not isinstance(tool.get(field), str) or not tool[field]:
                raise ValidationAppError(f"工具文件 {tool_file.name} 缺少 {field}")
        module_path = tool["entrypoint"].split(":", 1)[0]
        if not module_path.startswith("src/"):
            raise ValidationAppError(
                f"工具 {tool['id']} 的 entrypoint 必须位于 src/ 目录"
            )
        _read_text(workspace, module_path)
        tools.append(
            {
                "id": tool["id"],
                "name": tool["name"],
                "description": tool.get("description", ""),
                "risk_level": tool.get("risk_level", "low"),
                "entrypoint": tool["entrypoint"],
                "parameters": tool.get("parameters") or {},
                "source_path": str(tool_file.relative_to(workspace)).replace("\\", "/"),
            }
        )
    return tools


def _load_agent(
    workspace: Path, agent_dir: Path, tool_ids: set[str]
) -> dict[str, Any]:
    agent_id = agent_dir.name
    if not _AGENT_ID_RE.match(agent_id):
        raise ValidationAppError(f"非法 agent_id：{agent_id}")
    manifest = _load_yaml(agent_dir / "agent.yaml", f"agents/{agent_id}/agent.yaml")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationAppError(f"agents/{agent_id}/agent.yaml 必须设置 name")
    role = manifest.get("role", "specialist")
    if role not in _VALID_ROLES:
        raise ValidationAppError(
            f"agents/{agent_id} 的 role 必须是 coordinator 或 specialist"
        )
    prompt_path = manifest.get("system_prompt", "prompts/system.md")
    if not isinstance(prompt_path, str):
        raise ValidationAppError(f"agents/{agent_id} 的 system_prompt 必须是相对路径")
    agent_rel = f"agents/{agent_id}"
    full_prompt_path = f"{agent_rel}/{prompt_path}".replace("\\", "/")
    prompt_content = _read_text(workspace, full_prompt_path)

    prompts_dir = agent_dir / "prompts"
    if not prompts_dir.is_dir():
        raise ValidationAppError(f"agents/{agent_id}/prompts 目录缺失")
    prompts: list[dict[str, str]] = []
    for prompt_file in sorted(prompts_dir.rglob("*.md")):
        source_path = str(prompt_file.relative_to(workspace)).replace("\\", "/")
        local_path = str(prompt_file.relative_to(agent_dir)).replace("\\", "/")
        prompt_key = (
            "system"
            if local_path == prompt_path.replace("\\", "/")
            else local_path.removeprefix("prompts/").removesuffix(".md").replace("/", ".")
        )
        prompts.append(
            {
                "prompt_key": prompt_key,
                "source_path": source_path,
                "content": prompt_file.read_text(encoding="utf-8"),
            }
        )
    if not any(item["prompt_key"] == "system" for item in prompts):
        raise ValidationAppError(
            f"agents/{agent_id} 的 system_prompt 必须指向 prompts/ 中的 Markdown"
        )

    allowed_tools = manifest.get("tools") or []
    if not isinstance(allowed_tools, list) or not all(
        isinstance(item, str) for item in allowed_tools
    ):
        raise ValidationAppError(f"agents/{agent_id} 的 tools 必须是工具 ID 字符串数组")
    # retrieve 为平台内置工具，无需在 tools/*.yaml 声明
    unknown = [
        item for item in allowed_tools if item not in tool_ids and item != "retrieve"
    ]
    if unknown:
        raise ValidationAppError(
            f"agents/{agent_id} 引用了未声明工具：{', '.join(unknown)}"
        )

    namespaces = manifest.get("namespaces") or []
    if not isinstance(namespaces, list) or not all(
        isinstance(item, str) and item.strip() for item in namespaces
    ):
        raise ValidationAppError(
            f"agents/{agent_id} 的 namespaces 必须是非空字符串数组"
        )
    namespaces = [item.strip() for item in namespaces]
    # retrieve 与 namespaces 必须成对出现：无枚举可选时模型只能瞎猜命名空间
    if "retrieve" in allowed_tools and not namespaces:
        raise ValidationAppError(
            f"agents/{agent_id} 声明了 retrieve，必须同时声明 namespaces"
        )
    if namespaces and "retrieve" not in allowed_tools:
        raise ValidationAppError(
            f"agents/{agent_id} 声明了 namespaces，必须同时在 tools 中加入 retrieve"
        )

    return {
        "agent_id": agent_id,
        "name": name.strip(),
        "role": role,
        "description": manifest.get("description", ""),
        "system_prompt_path": full_prompt_path,
        "system_prompt_content": prompt_content,
        "allowed_tools": allowed_tools,
        "namespaces": namespaces,
        "max_steps": int(manifest.get("max_steps", 8)),
        "prompts": prompts,
        "source_path": f"{agent_rel}/agent.yaml",
    }


def _validate_workspace(workspace: Path) -> dict[str, Any]:
    manifest = _load_yaml(workspace / "app.yaml", "app.yaml")
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationAppError("app.yaml 必须设置 name")
    tenant_id = manifest.get("tenant_id", "ten_demo")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise ValidationAppError("tenant_id 必须是非空字符串")
    model = manifest.get("model") or {}
    if not isinstance(model, dict) or not model.get("primary"):
        raise ValidationAppError("model.primary 必填（逻辑名，如 default）")
    coordinator_id = manifest.get("coordinator")
    if not isinstance(coordinator_id, str) or not coordinator_id:
        raise ValidationAppError("app.yaml 必须设置 coordinator（协调 Agent ID）")

    tools = _load_tools(workspace)
    tool_ids = {item["id"] for item in tools}
    knowledge = _load_knowledge(workspace)
    knowledge_namespaces = {item["namespace"] for item in knowledge}

    agents_dir = workspace / "agents"
    if not agents_dir.is_dir():
        raise ValidationAppError("缺少 agents 目录")
    agents: list[dict[str, Any]] = []
    for child in sorted(agents_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        agents.append(_load_agent(workspace, child, tool_ids))
    if not agents:
        raise ValidationAppError("agents 下至少需要一个 Agent")

    agent_ids = {item["agent_id"] for item in agents}
    if coordinator_id not in agent_ids:
        raise ValidationAppError(f"coordinator={coordinator_id} 在 agents/ 中不存在")
    coordinators = [item for item in agents if item["role"] == "coordinator"]
    if len(coordinators) != 1:
        raise ValidationAppError("应用空间必须且只能有一个 role=coordinator 的 Agent")
    if coordinators[0]["agent_id"] != coordinator_id:
        raise ValidationAppError("app.yaml 的 coordinator 必须指向唯一的协调 Agent")

    # Agent 可访问的命名空间必须以本空间 knowledge/manifest 为唯一真源
    for agent in agents:
        agent_ns = agent.get("namespaces") or []
        if agent_ns and not knowledge:
            raise ValidationAppError(
                f"agents/{agent['agent_id']} 声明了 namespaces，"
                "但本空间未提供 knowledge/manifest.yaml"
            )
        unknown_ns = [ns for ns in agent_ns if ns not in knowledge_namespaces]
        if unknown_ns:
            raise ValidationAppError(
                f"agents/{agent['agent_id']} 引用了未在 knowledge/manifest.yaml "
                f"声明的命名空间：{', '.join(unknown_ns)}"
            )

    timeout_ms = int(model.get("timeout_ms") or get_settings().llm_timeout * 1000)
    return {
        "slug": workspace.name,
        "name": name.strip(),
        "description": manifest.get("description", ""),
        "tenant_id": tenant_id,
        "model": {"primary": str(model["primary"]), "timeout_ms": timeout_ms},
        "coordinator": coordinator_id,
        "max_steps": int(manifest.get("max_steps", 12)),
        "agents": agents,
        "tools": tools,
        "knowledge": knowledge,
        "workspace_path": str(workspace),
    }


def _error_snapshot(slug: str, workspace: Path, error: str, mtime: float) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "slug": slug,
        "name": slug,
        "description": "",
        "tenant_id": "ten_demo",
        "model": {"primary": "default", "timeout_ms": 60000},
        "coordinator": "",
        "max_steps": 0,
        "agents": [],
        "tools": [],
        "knowledge": [],
        "workspace_path": str(workspace),
        "load_status": "error",
        "validation_error": error,
        "loaded_at": now,
        "mtime": mtime,
        "collaboration_mode": "multi_agent_react",
    }


def _load_one(workspace: Path) -> dict[str, Any]:
    slug = workspace.name
    mtime = _dir_mtime(workspace)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        data = _validate_workspace(workspace)
        data["load_status"] = "ready"
        data["validation_error"] = None
        data["loaded_at"] = now
        data["mtime"] = mtime
        data["collaboration_mode"] = "multi_agent_react"
        data["coordinator_agent_id"] = data["coordinator"]
        return data
    except Exception as exc:  # noqa: BLE001
        snap = _error_snapshot(slug, workspace, str(exc), mtime)
        snap["coordinator_agent_id"] = ""
        return snap


def _invalidate_tools(slug: str) -> None:
    try:
        from packages.core.agent_runtime import invalidate_workspace_tools

        invalidate_workspace_tools(slug)
    except Exception:  # noqa: BLE001
        pass


def scan_all_workspaces() -> None:
    """启动时全量扫描。"""
    root = _workspace_root()
    with _lock:
        global _root_mtime, _registry
        _registry = {}
        if not root.is_dir():
            _root_mtime = None
            return
        _root_mtime = root.stat().st_mtime
        for child in sorted(root.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            snap = _load_one(child)
            _registry[child.name] = snap
            _invalidate_tools(child.name)


def _sync_root() -> None:
    """检测根目录增减与各空间 mtime，按需重载。"""
    root = _workspace_root()
    with _lock:
        global _root_mtime
        if not root.is_dir():
            _registry.clear()
            _root_mtime = None
            return

        current_root_mtime = root.stat().st_mtime
        slugs_on_disk = {
            child.name
            for child in root.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        }

        # 删除已不存在的空间
        for stale in list(_registry.keys()):
            if stale not in slugs_on_disk:
                _registry.pop(stale, None)
                _invalidate_tools(stale)

        for slug in slugs_on_disk:
            path = root / slug
            mtime = _dir_mtime(path)
            existing = _registry.get(slug)
            if existing is None or existing.get("mtime") != mtime:
                snap = _load_one(path)
                _registry[slug] = snap
                _invalidate_tools(slug)

        _root_mtime = current_root_mtime


def list_workspaces(tenant_id: str) -> dict[str, Any]:
    _sync_root()
    with _lock:
        items = []
        for snap in sorted(_registry.values(), key=lambda x: x["slug"]):
            if snap.get("tenant_id") and snap["tenant_id"] != tenant_id:
                # 校验失败的快照可能没有正确 tenant，仍展示以便排查
                if snap.get("load_status") == "ready":
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
    from packages.core.agent_runtime import resolve_tools

    _sync_root()
    with _lock:
        snap = _registry.get(slug)
        if snap is None:
            raise NotFoundError("workspace not found")
        if (
            snap.get("load_status") == "ready"
            and snap.get("tenant_id")
            and snap["tenant_id"] != tenant_id
        ):
            raise NotFoundError("workspace not found")
        specialists = [
            a for a in snap.get("agents") or [] if a.get("role") == "specialist"
        ]
        workspace_tools = list(snap.get("tools") or [])
        agents_out = []
        for a in snap.get("agents") or []:
            declared = list(a.get("allowed_tools") or [])
            if a.get("role") == "coordinator":
                effective = resolve_tools(
                    declared_tool_ids=declared,
                    workspace_tools=workspace_tools,
                    specialists=specialists,
                    namespaces=a.get("namespaces") or [],
                )
                tool_ids = [t["id"] for t in effective]
            else:
                tool_ids = declared
            agents_out.append(
                {
                    "agent_id": a["agent_id"],
                    "name": a["name"],
                    "role": a["role"],
                    "description": a.get("description") or "",
                    "system_prompt_path": a["system_prompt_path"],
                    "allowed_tools": tool_ids,
                    "namespaces": a.get("namespaces") or [],
                    "max_steps": a["max_steps"],
                    "source_path": a["source_path"],
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
    """供 chat / agent_runtime 使用的运行时视图。"""
    from packages.core.agent_runtime import resolve_tools

    _sync_root()
    with _lock:
        snap = _registry.get(slug)
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

        specialists = [
            dict(a) for a in snap.get("agents") or [] if a["role"] == "specialist"
        ]
        workspace_tools = list(snap.get("tools") or [])
        # 校验阶段允许声明 retrieve（内置）；YAML 工具表不含它
        declared = list(coordinator.get("allowed_tools") or [])
        allowed = resolve_tools(
            declared_tool_ids=declared,
            workspace_tools=workspace_tools,
            specialists=specialists,
            namespaces=coordinator.get("namespaces") or [],
        )
        return {
            "slug": snap["slug"],
            "tenant_id": snap["tenant_id"],
            "name": snap["name"],
            "status": "enabled",
            "workspace_path": snap["workspace_path"],
            "coordinator_agent_id": coordinator["agent_id"],
            "system_prompt": coordinator["system_prompt_content"],
            "system_prompt_path": coordinator["system_prompt_path"],
            "model": snap["model"],
            "max_steps": int(
                coordinator.get("max_steps") or snap.get("max_steps") or 8
            ),
            "allowed_tools": allowed,
            "all_tools": workspace_tools,
            "specialists": specialists,
        }
