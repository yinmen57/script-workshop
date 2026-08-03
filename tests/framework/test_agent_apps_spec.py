# -*- coding: utf-8 -*-
"""agent_apps.spec：AgentSpec 路径与 prompt 读取。"""

from __future__ import annotations

from pathlib import Path

from framework.agent_apps.spec import AgentSpec


def _make_spec(tmp_path: Path) -> AgentSpec:
    agent_dir = tmp_path / "prompts" / "router"
    agent_dir.mkdir(parents=True)
    (agent_dir / "system.md").write_text("你是协调者", encoding="utf-8")
    (agent_dir / "extra.md").write_text("附加说明", encoding="utf-8")
    return AgentSpec(
        agent_id="router",
        name="Router",
        role="coordinator",
        description="协调",
        tools=(),
        package_root=tmp_path,
        package_relpath="tests/fake_app",
    )


def test_agent_spec_paths_and_content(tmp_path: Path) -> None:
    spec = _make_spec(tmp_path)
    assert spec.system_prompt_path == "prompts/router/system.md"
    assert spec.system_prompt_content == "你是协调者"
    assert spec.source_path == "tests/fake_app/agents/router.py"


def test_agent_spec_prompt_files_and_runtime(tmp_path: Path) -> None:
    spec = _make_spec(tmp_path)
    files = spec.prompt_files()
    keys = {item["prompt_key"] for item in files}
    assert keys == {"system", "extra"}
    runtime = spec.to_runtime_dict()
    assert runtime["agent_id"] == "router"
    assert runtime["system_prompt_content"] == "你是协调者"
    assert runtime["allowed_tools"] == []
