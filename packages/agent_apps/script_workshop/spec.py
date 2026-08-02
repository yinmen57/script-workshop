"""Agent 声明结构。"""

from __future__ import annotations

from dataclasses import dataclass

from packages.agent_apps.script_workshop.paths import PROMPTS_ROOT, read_prompt


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    role: str
    description: str
    tools: tuple[str, ...]
    namespaces: tuple[str, ...] = ()
    max_steps: int = 8
    system_prompt_file: str = "system.md"

    @property
    def system_prompt_path(self) -> str:
        return f"prompts/{self.agent_id}/{self.system_prompt_file}"

    @property
    def system_prompt_content(self) -> str:
        return read_prompt(self.agent_id, self.system_prompt_file)

    @property
    def source_path(self) -> str:
        return f"packages/agent_apps/script_workshop/agents/{self.agent_id.replace('-', '_')}.py"

    def prompt_files(self) -> list[dict[str, str]]:
        """扫描该 Agent 下全部 md，供管理端展示。"""
        prompts_dir = PROMPTS_ROOT / self.agent_id
        if not prompts_dir.is_dir():
            return []
        items: list[dict[str, str]] = []
        for prompt_file in sorted(prompts_dir.rglob("*.md")):
            local = str(prompt_file.relative_to(prompts_dir)).replace("\\", "/")
            prompt_key = (
                "system"
                if local == self.system_prompt_file
                else local.removesuffix(".md").replace("/", ".")
            )
            items.append(
                {
                    "prompt_key": prompt_key,
                    "source_path": f"packages/agent_apps/script_workshop/prompts/{self.agent_id}/{local}",
                    "content": prompt_file.read_text(encoding="utf-8"),
                }
            )
        return items

    def to_runtime_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role,
            "description": self.description,
            "system_prompt_content": self.system_prompt_content,
            "system_prompt_path": self.system_prompt_path,
            "allowed_tools": list(self.tools),
            "namespaces": list(self.namespaces),
            "max_steps": self.max_steps,
            "prompts": self.prompt_files(),
            "source_path": self.source_path,
        }
