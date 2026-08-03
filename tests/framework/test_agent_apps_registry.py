# -*- coding: utf-8 -*-
"""agent_apps.registry：注册、校验、租户隔离、error 快照。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from framework.agent_apps.registry import (
    clear_apps,
    get_runtime_app,
    get_workspace,
    list_workspaces,
    register_app,
    register_apps,
)
from framework.domain.errors import NotFoundError, ValidationAppError


def _write_workspace(
    root: Path,
    *,
    with_knowledge: bool = True,
    namespaces: list[dict[str, str]] | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if with_knowledge:
        knowledge = root / "knowledge"
        knowledge.mkdir()
        ns_list = namespaces or [
            {"namespace": "craft.demo", "dir": "demo", "description": "demo"}
        ]
        for item in ns_list:
            corpus = knowledge / item["dir"]
            corpus.mkdir(parents=True, exist_ok=True)
            (corpus / "a.md").write_text("条目一\n---\n条目二\n", encoding="utf-8")
        (knowledge / "manifest.yaml").write_text(
            yaml.safe_dump({"namespaces": ns_list}, allow_unicode=True),
            encoding="utf-8",
        )
    return root


def _valid_spec(
    workspace: Path,
    *,
    slug: str = "demo-app",
    tenant_id: str = "tenant-a",
    agent_namespaces: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": "Demo",
        "description": "测试应用",
        "tenant_id": tenant_id,
        "workspace_path": str(workspace),
        "coordinator": "router",
        "collaboration_mode": "handoff",
        "max_steps": 6,
        "model": {"provider": "openai"},
        "agents": [
            {
                "agent_id": "router",
                "name": "Router",
                "role": "coordinator",
                "description": "协调",
                "system_prompt_content": "coord",
                "system_prompt_path": "prompts/router/system.md",
                "allowed_tools": [],
                "namespaces": [],
                "max_steps": 6,
                "source_path": "agents/router.py",
                "prompts": [],
            },
            {
                "agent_id": "parser",
                "name": "Parser",
                "role": "specialist",
                "description": "解析",
                "system_prompt_content": "parse",
                "system_prompt_path": "prompts/parser/system.md",
                "allowed_tools": ["echo"],
                "namespaces": agent_namespaces
                if agent_namespaces is not None
                else ["craft.demo"],
                "max_steps": 4,
                "source_path": "agents/parser.py",
                "prompts": [],
            },
        ],
        "tools": [
            {
                "id": "echo",
                "description": "echo",
                "entrypoint": "tests.framework._fake_tools:echo_text",
            }
        ],
    }


def test_register_success_and_workspace_views(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "app")
    register_app(_valid_spec(ws))
    listed = list_workspaces("tenant-a")
    assert listed["total"] == 1
    assert listed["items"][0]["load_status"] == "ready"

    detail = get_workspace("tenant-a", "demo-app")
    router = next(a for a in detail["agents"] if a["agent_id"] == "router")
    assert "delegate_to_parser" in router["allowed_tools"]
    knowledge = detail["knowledge"]
    assert knowledge[0]["namespace"] == "craft.demo"
    assert knowledge[0]["entry_count"] == 2
    assert "parser" in knowledge[0]["used_by_agents"]

    runtime = get_runtime_app("tenant-a", "demo-app")
    assert runtime["coordinator_agent_id"] == "router"
    assert "echo" in runtime["tool_catalog"]


def test_tenant_isolation(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "app")
    register_app(_valid_spec(ws, tenant_id="tenant-a"))
    assert list_workspaces("tenant-b")["total"] == 0
    with pytest.raises(NotFoundError):
        get_workspace("tenant-b", "demo-app")
    with pytest.raises(NotFoundError):
        get_runtime_app("tenant-b", "demo-app")


def test_missing_coordinator_writes_error_snapshot(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "app", with_knowledge=False)
    spec = _valid_spec(ws, agent_namespaces=[])
    spec["agents"] = [a for a in spec["agents"] if a["role"] != "coordinator"]
    register_app(spec)
    items = list_workspaces("tenant-a")["items"]
    assert items[0]["load_status"] == "error"
    assert "coordinator" in (items[0]["validation_error"] or "").lower()


def test_undeclared_namespace_error(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "app")
    register_app(_valid_spec(ws, agent_namespaces=["craft.missing"]))
    err = list_workspaces("tenant-a")["items"][0]["validation_error"]
    assert "未声明命名空间" in (err or "")


def test_knowledge_without_manifest(tmp_path: Path) -> None:
    ws = tmp_path / "app"
    ws.mkdir()
    (ws / "knowledge").mkdir()
    register_app(_valid_spec(ws, agent_namespaces=[]))
    err = list_workspaces("tenant-a")["items"][0]["validation_error"]
    assert "manifest.yaml" in (err or "")


def test_register_apps_rebuilds(tmp_path: Path) -> None:
    ws1 = _write_workspace(tmp_path / "a")
    ws2 = _write_workspace(tmp_path / "b")
    register_apps(
        [
            lambda: _valid_spec(ws1, slug="a"),
            lambda: _valid_spec(ws2, slug="b"),
        ]
    )
    assert list_workspaces("tenant-a")["total"] == 2
    clear_apps()
    with pytest.raises(RuntimeError, match="register_apps"):
        list_workspaces("tenant-a")


def test_slug_required(tmp_path: Path) -> None:
    ws = _write_workspace(tmp_path / "app", with_knowledge=False)
    spec = _valid_spec(ws, agent_namespaces=[])
    spec["slug"] = ""
    with pytest.raises(ValidationAppError, match="slug"):
        register_app(spec)
