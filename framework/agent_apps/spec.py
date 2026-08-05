"""框架通用 Agent 声明结构；业务包传入 package_root / package_relpath。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    role: str
    description: str
    tools: tuple[str, ...]
    package_root: Path
    package_relpath: str
    namespaces: tuple[str, ...] = ()
    max_steps: int = 8
    system_prompt_file: str = "system.md"
    # 方舟 DeepSeek 等：是否开启深度思考（thinking.type）
    thinking: bool = False
    # 调试台单测内置触发提示词
    sample_prompts: tuple[str, ...] = ()

    @property
    def prompts_root(self) -> Path:
        return self.package_root / "prompts"

    @property
    def system_prompt_path(self) -> str:
        return f"prompts/{self.agent_id}/{self.system_prompt_file}"

    @property
    def system_prompt_content(self) -> str:
        path = self.prompts_root / self.agent_id / self.system_prompt_file
        return path.read_text(encoding="utf-8")

    @property
    def source_path(self) -> str:
        return (
            f"{self.package_relpath}/agents/"
            f"{self.agent_id.replace('-', '_')}.py"
        )

    def prompt_files(self) -> list[dict[str, str]]:
        """扫描该 Agent 下全部 md，供管理端展示。"""
        prompts_dir = self.prompts_root / self.agent_id
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
                    "source_path": (
                        f"{self.package_relpath}/prompts/{self.agent_id}/{local}"
                    ),
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
            "thinking": self.thinking,
            "sample_prompts": list(self.sample_prompts),
            "prompts": self.prompt_files(),
            "source_path": self.source_path,
        }
