"""LangGraph ReAct 运行时：产出与旧版兼容的 step / _final 事件。"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import LLMResult
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from packages.agent_apps.llm import build_chat_model
from packages.agent_apps.tooling import build_business_tools


def _message_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content)


def _to_lc_messages(messages: list[dict[str, Any]]) -> list[BaseMessage]:
    """把 OpenAI 风格 messages 转成 LangChain messages（忽略历史 tool 轮）。"""
    result: list[BaseMessage] = []
    for item in messages:
        role = item.get("role")
        content = item.get("content") or ""
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            # 历史里若带 tool_calls，仅保留文本以免污染新一轮图状态
            result.append(AIMessage(content=content))
    return result


def _accumulate_usage(total: dict[str, int], usage: dict[str, Any] | None) -> None:
    usage = usage or {}
    for key in total:
        total[key] += int(usage.get(key) or 0)


@dataclass
class _RunSink:
    """跨 coordinator / specialist 共享的步骤汇聚点。"""

    queue: asyncio.Queue
    counter: list[int] = field(default_factory=lambda: [0])
    usage: dict[str, int] = field(
        default_factory=lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
    )
    tool_trace: list[dict[str, Any]] = field(default_factory=list)

    def next_step_no(self) -> int:
        self.counter[0] += 1
        return self.counter[0]


class _StepHandler(AsyncCallbackHandler):
    """把 LangChain 回调转成调试台 step 事件。"""

    def __init__(self, sink: _RunSink, agent_id: str) -> None:
        super().__init__()
        self.sink = sink
        self.agent_id = agent_id
        self._tool_started_at: dict[str, float] = {}
        self._tool_inputs: dict[str, Any] = {}

    async def on_chat_model_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = {}
        if response.llm_output and isinstance(response.llm_output, dict):
            raw = response.llm_output.get("token_usage") or response.llm_output.get(
                "usage"
            )
            if isinstance(raw, dict):
                usage = {
                    "prompt_tokens": raw.get("prompt_tokens")
                    or raw.get("input_tokens")
                    or 0,
                    "completion_tokens": raw.get("completion_tokens")
                    or raw.get("output_tokens")
                    or 0,
                    "total_tokens": raw.get("total_tokens") or 0,
                }
        # 新版 usage 也可能挂在 generation.message 上
        for gen_list in response.generations or []:
            for gen in gen_list:
                msg = getattr(gen, "message", None)
                meta = getattr(msg, "usage_metadata", None) if msg is not None else None
                if isinstance(meta, dict):
                    usage = {
                        "prompt_tokens": meta.get("input_tokens") or 0,
                        "completion_tokens": meta.get("output_tokens") or 0,
                        "total_tokens": meta.get("total_tokens") or 0,
                    }
                content = _message_text(getattr(msg, "content", None) if msg else None)
                if not content:
                    content = _message_text(getattr(gen, "text", None))
                if content:
                    await self.sink.queue.put(
                        {
                            "step_no": self.sink.next_step_no(),
                            "agent_id": self.agent_id,
                            "type": "thought",
                            "tool_id": None,
                            "args": None,
                            "output": content,
                            "duration_ms": None,
                            "error": None,
                        }
                    )
        _accumulate_usage(self.sink.usage, usage)

    async def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: Any = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        key = str(run_id or id(serialized))
        self._tool_started_at[key] = time.perf_counter()
        if isinstance(inputs, dict):
            self._tool_inputs[key] = inputs
        else:
            try:
                self._tool_inputs[key] = json.loads(input_str) if input_str else {}
            except json.JSONDecodeError:
                self._tool_inputs[key] = {"input": input_str}

    async def on_tool_end(
        self,
        output: Any,
        *,
        run_id: Any = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        key = str(run_id or "")
        started = self._tool_started_at.pop(key, time.perf_counter())
        arguments = self._tool_inputs.pop(key, {})
        duration_ms = int((time.perf_counter() - started) * 1000)
        tool_id = name or (kwargs.get("name") if kwargs else None) or "tool"
        if hasattr(output, "content"):
            observation = _message_text(output.content)
        else:
            observation = output if isinstance(output, str) else json.dumps(
                output, ensure_ascii=False, default=str
            )
        error = None
        try:
            parsed = json.loads(observation) if observation.startswith("{") else None
            if isinstance(parsed, dict) and parsed.get("error"):
                error = str(parsed["error"])
        except json.JSONDecodeError:
            pass
        self.sink.tool_trace.append(
            {
                "tool_id": tool_id,
                "arguments": arguments,
                "observation": observation,
                "duration_ms": duration_ms,
                "error": error,
            }
        )
        await self.sink.queue.put(
            {
                "step_no": self.sink.next_step_no(),
                "agent_id": self.agent_id,
                "type": "tool",
                "tool_id": tool_id,
                "args": arguments,
                "output": observation,
                "duration_ms": duration_ms,
                "error": error,
            }
        )


def _build_handoff_tool(
    *,
    specialist: dict[str, Any],
    workspace_path: str,
    tenant_id: str,
    model: Any,
    sink: _RunSink,
) -> StructuredTool:
    agent_id = specialist["agent_id"]
    tool_name = f"delegate_to_{agent_id}"

    class HandoffArgs(BaseModel):
        task: str = Field(description="交给该专业 Agent 的任务说明")

    async def _delegate(task: str) -> str:
        tools = build_business_tools(
            tool_ids=list(specialist.get("allowed_tools") or []),
            workspace_path=workspace_path,
            tenant_id=tenant_id,
            namespaces=list(specialist.get("namespaces") or []),
        )
        prompt = specialist.get("system_prompt_content") or f"你是 {specialist['name']}"
        graph = create_react_agent(model, tools, prompt=prompt, name=agent_id)
        handler = _StepHandler(sink, agent_id)
        max_steps = int(specialist.get("max_steps") or 8)
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=task)]},
            config={
                "callbacks": [handler],
                "recursion_limit": max(max_steps * 2, 8),
            },
        )
        messages = result.get("messages") or []
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                text = _message_text(msg.content)
                if text:
                    return text
        return json.dumps({"error": "专业 Agent 未返回结论"}, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=_delegate,
        name=tool_name,
        description=(
            f"将子任务交给专业 Agent「{specialist['name']}」"
            f"（{specialist.get('description') or agent_id}）。"
            "传入清晰的任务说明，返回该 Agent 的结论。"
        ),
        args_schema=HandoffArgs,
    )


def build_agent_graph(
    *,
    agent: dict[str, Any],
    workspace_path: str,
    tenant_id: str,
    model: Any,
    specialists: list[dict[str, Any]] | None,
    sink: _RunSink,
):
    """组装单个 Agent 的 LangGraph ReAct 图。"""
    tools = build_business_tools(
        tool_ids=list(agent.get("allowed_tools") or []),
        workspace_path=workspace_path,
        tenant_id=tenant_id,
        namespaces=list(agent.get("namespaces") or []),
    )
    if specialists:
        for spec in specialists:
            tools.append(
                _build_handoff_tool(
                    specialist=spec,
                    workspace_path=workspace_path,
                    tenant_id=tenant_id,
                    model=model,
                    sink=sink,
                )
            )
    prompt = agent.get("system_prompt_content") or f"你是 {agent.get('name')}"
    return create_react_agent(
        model, tools, prompt=prompt, name=agent.get("agent_id") or "agent"
    )


async def iter_agent_run(
    *,
    app: dict[str, Any],
    messages: list[dict[str, Any]],
    max_steps: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """执行协调 Agent，逐步 yield step，最后 yield _final。"""
    coordinator = next(
        (a for a in app["agents"] if a["role"] == "coordinator"),
        None,
    )
    if coordinator is None:
        raise RuntimeError("应用缺少 coordinator Agent")
    specialists = [a for a in app["agents"] if a.get("role") == "specialist"]
    model_cfg = app.get("model") or {}
    model = await build_chat_model(
        tenant_id=app["tenant_id"],
        primary=str(model_cfg.get("primary") or "default"),
        timeout_ms=model_cfg.get("timeout_ms"),
    )
    sink = _RunSink(queue=asyncio.Queue())
    graph = build_agent_graph(
        agent=coordinator,
        workspace_path=app["workspace_path"],
        tenant_id=app["tenant_id"],
        model=model,
        specialists=specialists,
        sink=sink,
    )
    steps = int(max_steps or coordinator.get("max_steps") or app.get("max_steps") or 8)
    lc_messages = _to_lc_messages(messages)
    # system 已由 create_react_agent 的 prompt 注入；去掉消息里的 system 避免重复
    lc_messages = [m for m in lc_messages if not isinstance(m, SystemMessage)]
    # prepare_completion 已把 system+selection 拼进第一条；若仅剩 user/assistant 则直接用
    # 若原 messages 的 system 含 selection 上下文，需并入 prompt——见下方补丁
    selection_system = next(
        (m.get("content") for m in messages if m.get("role") == "system"),
        None,
    )
    if selection_system and selection_system != coordinator.get("system_prompt_content"):
        # 工作台 selection 等动态前缀：重建带完整 system 的图
        patched = dict(coordinator)
        patched["system_prompt_content"] = selection_system
        graph = build_agent_graph(
            agent=patched,
            workspace_path=app["workspace_path"],
            tenant_id=app["tenant_id"],
            model=model,
            specialists=specialists,
            sink=sink,
        )

    handler = _StepHandler(sink, coordinator["agent_id"])
    final_holder: dict[str, Any] = {}

    async def _runner() -> None:
        try:
            result = await graph.ainvoke(
                {"messages": lc_messages},
                config={
                    "callbacks": [handler],
                    "recursion_limit": max(steps * 2, 16),
                },
            )
            await sink.queue.put({"_done": True, "result": result})
        except Exception as exc:  # noqa: BLE001
            await sink.queue.put({"_error": exc})

    task = asyncio.create_task(_runner())
    answer = ""
    try:
        while True:
            item = await sink.queue.get()
            if item.get("_error"):
                raise item["_error"]
            if item.get("_done"):
                final_holder["result"] = item.get("result") or {}
                break
            yield item
    finally:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        else:
            await task

    messages_out = (final_holder.get("result") or {}).get("messages") or []
    for msg in reversed(messages_out):
        if isinstance(msg, AIMessage):
            text = _message_text(msg.content)
            if text:
                answer = text
                break

    yield {
        "_final": True,
        "messages": messages,
        "answer": answer,
        "tool_trace": sink.tool_trace,
        "usage": sink.usage,
    }
