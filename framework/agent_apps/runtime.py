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

from framework.agent_apps.llm import build_chat_model
from framework.agent_apps.tooling import build_business_tools


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
    # 是否已通过 callback 推送过 token delta（避免结束时整段重复）
    streamed_text: list[str] = field(default_factory=list)
    # 工具报错后请求中止整图；由 runner_task.cancel() 跳出 ReAct
    abort: dict[str, str] | None = None
    runner_task: asyncio.Task | None = None

    def next_step_no(self) -> int:
        self.counter[0] += 1
        return self.counter[0]

    def mark_delta(self, text: str) -> None:
        if text:
            self.streamed_text.append(text)

    def request_abort(self, tool_id: str, message: str) -> None:
        """工具失败：只记录首个错误并取消执行任务。"""
        if self.abort is not None:
            return
        self.abort = {"tool_id": str(tool_id), "message": str(message)}
        task = self.runner_task
        if task is not None and not task.done():
            task.cancel()


class _StepHandler(AsyncCallbackHandler):
    """把 LangChain 回调转成调试台 step / delta 事件。"""

    def __init__(self, sink: _RunSink, agent_id: str) -> None:
        super().__init__()
        self.sink = sink
        self.agent_id = agent_id
        self._tool_started_at: dict[str, float] = {}
        self._tool_inputs: dict[str, Any] = {}

    async def _emit_delta(self, text: str) -> None:
        if not text:
            return
        self.sink.mark_delta(text)
        await self.sink.queue.put(
            {"_delta": True, "text": text, "agent_id": self.agent_id}
        )

    async def _emit_reasoning(self, text: str) -> None:
        """方舟 DeepSeek 等把思考写在 reasoning_content，单独推送。"""
        if not text:
            return
        await self.sink.queue.put(
            {"_reasoning": True, "text": text, "agent_id": self.agent_id}
        )

    @staticmethod
    def _chunk_reasoning(chunk: Any) -> str:
        """从 AIMessageChunk / dict 提取 reasoning_content。"""
        extra = getattr(chunk, "additional_kwargs", None) or {}
        if isinstance(extra, dict):
            for key in ("reasoning_content", "reasoning"):
                val = extra.get(key)
                if isinstance(val, str) and val:
                    return val
        # 部分适配器挂在顶层属性
        for key in ("reasoning_content", "reasoning"):
            val = getattr(chunk, key, None)
            if isinstance(val, str) and val:
                return val
        return ""

    async def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list[Any], **kwargs: Any
    ) -> None:
        # 每轮 LLM 重置，避免上一轮的 chat stream 标记挡住后续 token
        self._stream_via_chat = False

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        """ainvoke + streaming 时主路径：token 多为正文，reasoning 在 chunk.message。"""
        if getattr(self, "_stream_via_chat", False):
            return
        gen_chunk = kwargs.get("chunk")
        message = getattr(gen_chunk, "message", None) if gen_chunk is not None else None
        if message is not None:
            reasoning = self._chunk_reasoning(message)
            if reasoning:
                await self._emit_reasoning(reasoning)
            content = _message_text(getattr(message, "content", None))
            if content:
                await self._emit_delta(content)
                return
        # 无 chunk 时退回纯 token
        await self._emit_delta(token)

    async def on_chat_model_stream(self, chunk: Any, **kwargs: Any) -> None:
        """部分调用栈走 chat_model_stream：正文 + reasoning。"""
        self._stream_via_chat = True
        reasoning = self._chunk_reasoning(chunk)
        if reasoning:
            await self._emit_reasoning(reasoning)
        content = getattr(chunk, "content", None)
        if isinstance(content, str):
            await self._emit_delta(content)
        elif isinstance(content, list):
            await self._emit_delta(_message_text(content))

    async def on_chat_model_end(self, response: Any, **kwargs: Any) -> None:
        """结束回调：兼容 LLMResult 与 AIMessage 两种形态。"""
        usage: dict[str, Any] = {}
        # 已流式推送正文时不再整段 thought，避免重复刷屏
        if self.sink.streamed_text:
            meta = getattr(response, "usage_metadata", None)
            if isinstance(meta, dict):
                usage = {
                    "prompt_tokens": meta.get("input_tokens") or 0,
                    "completion_tokens": meta.get("output_tokens") or 0,
                    "total_tokens": meta.get("total_tokens") or 0,
                }
            elif isinstance(response, LLMResult) and response.llm_output:
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
            _accumulate_usage(self.sink.usage, usage)
            return

        contents: list[str] = []
        if isinstance(response, LLMResult):
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
                    content = _message_text(
                        getattr(msg, "content", None) if msg else None
                    )
                    if not content:
                        content = _message_text(getattr(gen, "text", None))
                    if content:
                        contents.append(content)
        else:
            meta = getattr(response, "usage_metadata", None)
            if isinstance(meta, dict):
                usage = {
                    "prompt_tokens": meta.get("input_tokens") or 0,
                    "completion_tokens": meta.get("output_tokens") or 0,
                    "total_tokens": meta.get("total_tokens") or 0,
                }
            content = _message_text(getattr(response, "content", None))
            if content:
                contents.append(content)

        for content in contents:
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
        tool_id = (
            (serialized or {}).get("name")
            or kwargs.get("name")
            or "tool"
        )
        # 工具一开始就推送，避免界面长时间只有「…」
        await self.sink.queue.put(
            {
                "step_no": self.sink.next_step_no(),
                "agent_id": self.agent_id,
                "type": "tool_start",
                "tool_id": str(tool_id),
                "args": self._tool_inputs[key],
                "output": "执行中…",
                "duration_ms": None,
                "error": None,
            }
        )

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
        # 工具报错立即跳出 ReAct，禁止继续空转 inspect / 重试
        if error:
            self.sink.request_abort(str(tool_id), error)


def _build_handoff_tool(
    *,
    specialist: dict[str, Any],
    workspace_path: str,
    tenant_id: str,
    model: Any,
    sink: _RunSink,
    tool_catalog: dict[str, dict[str, Any]],
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
            tool_catalog=tool_catalog,
        )
        prompt = specialist.get("system_prompt_content") or f"你是 {specialist['name']}"
        graph = create_react_agent(model, tools, prompt=prompt, name=agent_id)
        handler = _StepHandler(sink, agent_id)
        max_steps = int(specialist.get("max_steps") or 8)
        try:
            result = await graph.ainvoke(
                {"messages": [HumanMessage(content=task)]},
                config={
                    "callbacks": [handler],
                    "recursion_limit": max(max_steps * 2, 8),
                },
            )
        except asyncio.CancelledError:
            # 子 Agent 工具失败触发的中止，向上抛出由外层收尾
            raise
        if sink.abort:
            return json.dumps(
                {
                    "error": (
                        f"工具 {sink.abort['tool_id']} 失败："
                        f"{sink.abort['message']}"
                    )
                },
                ensure_ascii=False,
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
    tool_catalog: dict[str, dict[str, Any]] | None = None,
    specialist_models: dict[str, Any] | None = None,
):
    """组装单个 Agent 的 LangGraph ReAct 图。"""
    catalog = tool_catalog or {}
    models = specialist_models or {}
    tools = build_business_tools(
        tool_ids=list(agent.get("allowed_tools") or []),
        workspace_path=workspace_path,
        tenant_id=tenant_id,
        namespaces=list(agent.get("namespaces") or []),
        tool_catalog=catalog,
    )
    if specialists:
        for spec in specialists:
            sid = spec["agent_id"]
            tools.append(
                _build_handoff_tool(
                    specialist=spec,
                    workspace_path=workspace_path,
                    tenant_id=tenant_id,
                    model=models[sid],
                    sink=sink,
                    tool_catalog=catalog,
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
    agent_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """执行 Agent：默认跑 coordinator+handoff；指定 specialist 时仅单 Agent。"""
    agents = list(app.get("agents") or [])
    coordinator = next((a for a in agents if a.get("role") == "coordinator"), None)
    if coordinator is None:
        raise RuntimeError("应用缺少 coordinator Agent")

    target_id = (agent_id or "").strip() or None
    if target_id:
        entry = next((a for a in agents if a.get("agent_id") == target_id), None)
        if entry is None:
            raise RuntimeError(f"应用中不存在 Agent：{target_id}")
    else:
        entry = coordinator

    # specialist 单测：不挂 delegate_to_*；coordinator / 全链路：挂全部 specialist
    if entry.get("role") == "specialist":
        specialists: list[dict[str, Any]] | None = None
    else:
        specialists = [a for a in agents if a.get("role") == "specialist"]

    tool_catalog = dict(app.get("tool_catalog") or {})
    model_cfg = app.get("model") or {}
    model_kwargs = {
        "tenant_id": app["tenant_id"],
        "primary": str(model_cfg.get("primary") or "default"),
        "timeout_ms": model_cfg.get("timeout_ms"),
    }
    # 主 Agent 与各 specialist 按各自 thinking 建模型
    model = await build_chat_model(
        **model_kwargs,
        thinking=bool(entry.get("thinking")),
    )
    specialist_models: dict[str, Any] = {}
    if specialists:
        for spec in specialists:
            sid = spec["agent_id"]
            specialist_models[sid] = await build_chat_model(
                **model_kwargs,
                thinking=bool(spec.get("thinking")),
            )
    sink = _RunSink(queue=asyncio.Queue())
    graph = build_agent_graph(
        agent=entry,
        workspace_path=app["workspace_path"],
        tenant_id=app["tenant_id"],
        model=model,
        specialists=specialists,
        sink=sink,
        tool_catalog=tool_catalog,
        specialist_models=specialist_models,
    )
    steps = int(max_steps or entry.get("max_steps") or app.get("max_steps") or 8)
    lc_messages = _to_lc_messages(messages)
    # system 已由 create_react_agent 的 prompt 注入；去掉消息里的 system 避免重复
    lc_messages = [m for m in lc_messages if not isinstance(m, SystemMessage)]
    # prepare_completion 已把 system+selection 拼进第一条；若仅剩 user/assistant 则直接用
    # 若原 messages 的 system 含 selection 上下文，需并入 prompt——见下方补丁
    selection_system = next(
        (m.get("content") for m in messages if m.get("role") == "system"),
        None,
    )
    if selection_system and selection_system != entry.get("system_prompt_content"):
        # 工作台 selection 等动态前缀：重建带完整 system 的图
        patched = dict(entry)
        patched["system_prompt_content"] = selection_system
        graph = build_agent_graph(
            agent=patched,
            workspace_path=app["workspace_path"],
            tenant_id=app["tenant_id"],
            model=model,
            specialists=specialists,
            sink=sink,
            tool_catalog=tool_catalog,
            specialist_models=specialist_models,
        )

    handler = _StepHandler(sink, entry["agent_id"])
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
            # 子图已 abort 但尚未 cancel 到此处时，仍按中止收尾
            if sink.abort:
                msg = (
                    f"已中止：工具 {sink.abort['tool_id']} 失败 — "
                    f"{sink.abort['message']}"
                )
                await sink.queue.put(
                    {
                        "_done": True,
                        "result": {"messages": [AIMessage(content=msg)]},
                        "aborted": True,
                    }
                )
                return
            await sink.queue.put({"_done": True, "result": result})
        except asyncio.CancelledError:
            if sink.abort:
                msg = (
                    f"已中止：工具 {sink.abort['tool_id']} 失败 — "
                    f"{sink.abort['message']}"
                )
                await sink.queue.put(
                    {
                        "_done": True,
                        "result": {"messages": [AIMessage(content=msg)]},
                        "aborted": True,
                    }
                )
                return
            raise
        except Exception as exc:  # noqa: BLE001
            await sink.queue.put({"_error": exc})

    task = asyncio.create_task(_runner())
    sink.runner_task = task
    answer = ""
    aborted = False
    try:
        while True:
            item = await sink.queue.get()
            if item.get("_error"):
                raise item["_error"]
            if item.get("_done"):
                final_holder["result"] = item.get("result") or {}
                aborted = bool(item.get("aborted") or sink.abort)
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
            try:
                await task
            except asyncio.CancelledError:
                pass

    messages_out = (final_holder.get("result") or {}).get("messages") or []
    for msg in reversed(messages_out):
        if isinstance(msg, AIMessage):
            text = _message_text(msg.content)
            if text:
                answer = text
                break
    if aborted and sink.abort and not answer:
        answer = (
            f"已中止：工具 {sink.abort['tool_id']} 失败 — "
            f"{sink.abort['message']}"
        )

    yield {
        "_final": True,
        "messages": messages,
        "answer": answer,
        "tool_trace": sink.tool_trace,
        "usage": sink.usage,
        "streamed": bool(sink.streamed_text),
        "aborted": aborted,
    }
