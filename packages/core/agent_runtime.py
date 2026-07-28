"""Agent 工具执行循环：加载 entrypoint、内置工具、handoff、逐步事件。"""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import threading
import time
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

from packages.adapters.llm_openai import OpenAICompatibleChatAdapter

_lock = threading.RLock()
_module_cache: dict[tuple[str, str], Any] = {}

StepCallback = Callable[[dict[str, Any]], Awaitable[None] | None]

def build_retrieve_tool(namespaces: list[str]) -> dict[str, Any]:
    """内置 retrieve 工具：namespace 取值由 agent.yaml 的 namespaces 限定为枚举。

    枚举而非自由文本，避免模型凭 system prompt 猜命名空间导致空召回。
    """
    if not namespaces:
        raise ValueError("retrieve 工具需要至少一个 namespace")
    return {
        "id": "retrieve",
        "name": "检索知识",
        "description": (
            "在下列知识库命名空间中检索相关文本片段，返回带分数的结果："
            + "、".join(namespaces)
        ),
        "entrypoint": "__builtin__:retrieve",
        "risk_level": "low",
        "parameters": {
            "type": "object",
            "properties": {
                "namespace": {
                    "type": "string",
                    "description": "要检索的知识库命名空间，只能取枚举值之一",
                    "enum": list(namespaces),
                },
                "query": {"type": "string", "description": "检索问题"},
                "top_k": {
                    "type": "integer",
                    "description": "返回条数，默认 5",
                },
            },
            "required": ["namespace", "query"],
        },
        "source_path": "builtin:retrieve",
        "allowed_namespaces": list(namespaces),
    }


def invalidate_workspace_tools(slug: str) -> None:
    """空间热重载时清除该 slug 的模块缓存。"""
    with _lock:
        for key in list(_module_cache.keys()):
            if key[0] == slug:
                mod = _module_cache.pop(key)
                name = getattr(mod, "__name__", None)
                if name and name in sys.modules:
                    del sys.modules[name]


def _load_callable(slug: str, workspace_path: str, entrypoint: str) -> Callable[..., Any]:
    if ":" not in entrypoint:
        raise ValueError(f"非法 entrypoint：{entrypoint}")
    module_rel, func_name = entrypoint.split(":", 1)
    module_rel = module_rel.replace("\\", "/")
    key = (slug, module_rel)
    with _lock:
        mod = _module_cache.get(key)
        if mod is None:
            file_path = Path(workspace_path) / module_rel
            if not file_path.is_file():
                raise FileNotFoundError(f"工具模块不存在：{module_rel}")
            mod_name = (
                f"appspace_{slug}_{module_rel.replace('/', '_').removesuffix('.py')}"
            )
            spec = importlib.util.spec_from_file_location(mod_name, file_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"无法加载模块：{module_rel}")
            mod = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = mod
            spec.loader.exec_module(mod)
            _module_cache[key] = mod
    func = getattr(mod, func_name, None)
    if func is None or not callable(func):
        raise AttributeError(f"entrypoint 函数不存在：{entrypoint}")
    return func


def tools_to_openai_schema(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for tool in tools:
        params = tool.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        result.append(
            {
                "type": "function",
                "function": {
                    "name": tool["id"],
                    "description": tool.get("description")
                    or tool.get("name")
                    or tool["id"],
                    "parameters": params,
                },
            }
        )
    return result


def build_handoff_tools(specialists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为每个 specialist 生成 delegate_to_<id> 虚拟工具。"""
    tools = []
    for agent in specialists:
        agent_id = agent["agent_id"]
        tools.append(
            {
                "id": f"delegate_to_{agent_id}",
                "name": f"委派给 {agent['name']}",
                "description": (
                    f"将子任务交给专业 Agent「{agent['name']}」"
                    f"（{agent.get('description') or agent_id}）。"
                    "传入清晰的任务说明，返回该 Agent 的结论。"
                ),
                "entrypoint": f"__builtin__:handoff:{agent_id}",
                "risk_level": "low",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "交给该专业 Agent 的任务说明",
                        }
                    },
                    "required": ["task"],
                },
                "source_path": f"builtin:handoff:{agent_id}",
                "handoff_agent_id": agent_id,
            }
        )
    return tools


def resolve_tools(
    *,
    declared_tool_ids: list[str],
    workspace_tools: list[dict[str, Any]],
    specialists: list[dict[str, Any]] | None = None,
    namespaces: list[str] | None = None,
) -> list[dict[str, Any]]:
    """合并 YAML 工具、内置 retrieve、handoff 虚拟工具。"""
    by_id = {t["id"]: t for t in workspace_tools}
    resolved: list[dict[str, Any]] = []
    for tid in declared_tool_ids:
        if tid == "retrieve":
            resolved.append(build_retrieve_tool(namespaces or []))
        elif tid in by_id:
            resolved.append(by_id[tid])
    if specialists:
        resolved.extend(build_handoff_tools(specialists))
    # 去重保序
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for tool in resolved:
        if tool["id"] in seen:
            continue
        seen.add(tool["id"])
        unique.append(tool)
    return unique


def _accumulate_usage(total: dict[str, int], usage: dict[str, Any] | None) -> None:
    usage = usage or {}
    for key in total:
        total[key] += int(usage.get(key) or 0)


async def _emit(
    on_step: StepCallback | None, payload: dict[str, Any]
) -> dict[str, Any]:
    if on_step is not None:
        maybe = on_step(payload)
        if inspect.isawaitable(maybe):
            await maybe
    return payload


async def _invoke_file_tool(
    slug: str,
    workspace_path: str,
    tool: dict[str, Any],
    arguments: dict[str, Any],
    *,
    tenant_id: str | None = None,
) -> tuple[str, str | None]:
    """返回 (observation, error)。"""
    from packages.core.tool_context import current_tenant_id

    token = current_tenant_id.set(tenant_id) if tenant_id else None
    try:
        func = _load_callable(slug, workspace_path, tool["entrypoint"])
        if inspect.iscoroutinefunction(func):
            result = await func(**arguments)
        else:
            result = func(**arguments)
        if isinstance(result, str):
            return result, None
        return json.dumps(result, ensure_ascii=False, default=str), None
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        return (
            json.dumps(
                {"error": err, "traceback": traceback.format_exc(limit=5)},
                ensure_ascii=False,
            ),
            err,
        )
    finally:
        if token is not None:
            current_tenant_id.reset(token)


async def _invoke_retrieve(
    *,
    tenant_id: str,
    arguments: dict[str, Any],
    allowed_namespaces: list[str],
) -> tuple[str, str | None]:
    from packages.governance import vector_namespace_service

    namespace = str(arguments.get("namespace") or "").strip()
    query = str(arguments.get("query") or "").strip()
    top_k = int(arguments.get("top_k") or 5)
    if not namespace or not query:
        return json.dumps({"error": "namespace 与 query 必填"}, ensure_ascii=False), (
            "namespace 与 query 必填"
        )
    if namespace not in allowed_namespaces:
        err = (
            f"namespace 不在允许范围：{namespace}，"
            f"可选值 {', '.join(allowed_namespaces)}"
        )
        return json.dumps({"error": err}, ensure_ascii=False), err
    try:
        result = await vector_namespace_service.search(
            tenant_id=tenant_id,
            namespaces=[namespace],
            query=query,
            top_k=top_k,
        )
        return json.dumps(result, ensure_ascii=False, default=str), None
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False), str(exc)


async def iter_agent_run(
    *,
    slug: str,
    workspace_path: str,
    agent_id: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    adapter: OpenAICompatibleChatAdapter,
    max_steps: int,
    tenant_id: str,
    specialists: list[dict[str, Any]] | None = None,
    workspace_tools: list[dict[str, Any]] | None = None,
    on_step: StepCallback | None = None,
    step_counter: list[int] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """逐步产出 step 事件，最后产出 final。"""
    openai_tools = tools_to_openai_schema(tools)
    tools_by_id = {t["id"]: t for t in tools}
    specialists_by_id = {s["agent_id"]: s for s in (specialists or [])}
    all_workspace_tools = workspace_tools if workspace_tools is not None else tools
    working = list(messages)
    tool_trace: list[dict[str, Any]] = []
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    answer = ""
    finished = False
    counter = step_counter if step_counter is not None else [0]

    def next_step_no() -> int:
        counter[0] += 1
        return counter[0]

    steps = max(1, int(max_steps))
    for round_i in range(steps):
        result = await adapter.chat(
            working,
            tools=openai_tools if openai_tools else None,
        )
        _accumulate_usage(usage_total, result.get("usage"))

        message = result.get("message") or {}
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        working.append(assistant_msg)

        if content:
            yield await _emit(
                on_step,
                {
                    "step_no": next_step_no(),
                    "agent_id": agent_id,
                    "type": "thought",
                    "tool_id": None,
                    "args": None,
                    "output": content,
                    "duration_ms": None,
                    "error": None,
                },
            )

        if not tool_calls:
            answer = content or ""
            finished = True
            break

        for call in tool_calls:
            fn = call.get("function") or {}
            tool_id = fn.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                arguments = (
                    json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                )
            except json.JSONDecodeError:
                arguments = {}
            if not isinstance(arguments, dict):
                arguments = {}

            tool_def = tools_by_id.get(tool_id)
            started = time.perf_counter()
            error: str | None = None

            if tool_def is None:
                observation = json.dumps(
                    {"error": f"未知工具：{tool_id}"}, ensure_ascii=False
                )
                error = f"未知工具：{tool_id}"
            elif str(tool_def.get("entrypoint") or "").startswith("__builtin__:retrieve"):
                observation, error = await _invoke_retrieve(
                    tenant_id=tenant_id,
                    arguments=arguments,
                    allowed_namespaces=list(tool_def.get("allowed_namespaces") or []),
                )
            elif str(tool_def.get("entrypoint") or "").startswith("__builtin__:handoff:"):
                target_id = tool_def.get("handoff_agent_id") or tool_def[
                    "entrypoint"
                ].split(":")[-1]
                target = specialists_by_id.get(target_id)
                if target is None:
                    observation = json.dumps(
                        {"error": f"专业 Agent 不存在：{target_id}"},
                        ensure_ascii=False,
                    )
                    error = f"专业 Agent 不存在：{target_id}"
                else:
                    nested_messages = [
                        {
                            "role": "system",
                            "content": target.get("system_prompt_content")
                            or f"你是 {target['name']}",
                        },
                        {
                            "role": "user",
                            "content": str(arguments.get("task") or ""),
                        },
                    ]
                    nested_tools = resolve_tools(
                        declared_tool_ids=target.get("allowed_tools") or [],
                        workspace_tools=all_workspace_tools,
                        specialists=None,
                        namespaces=target.get("namespaces") or [],
                    )
                    nested_answer = ""
                    # 嵌套不再回调 on_step，统一由外层 yield 消费，避免重复落库
                    async for nested_ev in iter_agent_run(
                        slug=slug,
                        workspace_path=workspace_path,
                        agent_id=target_id,
                        messages=nested_messages,
                        tools=nested_tools,
                        adapter=adapter,
                        max_steps=int(target.get("max_steps") or 8),
                        tenant_id=tenant_id,
                        specialists=None,
                        workspace_tools=all_workspace_tools,
                        on_step=None,
                        step_counter=counter,
                    ):
                        if nested_ev.get("_final"):
                            nested_answer = nested_ev.get("answer") or ""
                            _accumulate_usage(usage_total, nested_ev.get("usage"))
                        else:
                            yield nested_ev
                    observation = nested_answer or json.dumps(
                        {"error": "专业 Agent 未返回结论"}, ensure_ascii=False
                    )
            else:
                observation, error = await _invoke_file_tool(
                    slug,
                    workspace_path,
                    tool_def,
                    arguments,
                    tenant_id=tenant_id,
                )

            duration_ms = int((time.perf_counter() - started) * 1000)
            tool_trace.append(
                {
                    "step": round_i + 1,
                    "tool_call_id": call.get("id"),
                    "tool_id": tool_id,
                    "arguments": arguments,
                    "observation": observation,
                    "duration_ms": duration_ms,
                    "error": error,
                }
            )
            working.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id") or tool_id,
                    "content": observation,
                }
            )
            yield await _emit(
                on_step,
                {
                    "step_no": next_step_no(),
                    "agent_id": agent_id,
                    "type": "tool",
                    "tool_id": tool_id,
                    "args": arguments,
                    "output": observation,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )

    if not finished:
        final = await adapter.chat(working, tools=None)
        _accumulate_usage(usage_total, final.get("usage"))
        answer = (
            (final.get("message") or {}).get("content")
            or final.get("content")
            or ""
        )
        working.append({"role": "assistant", "content": answer})
        if answer:
            yield await _emit(
                on_step,
                {
                    "step_no": next_step_no(),
                    "agent_id": agent_id,
                    "type": "thought",
                    "tool_id": None,
                    "args": None,
                    "output": answer,
                    "duration_ms": None,
                    "error": None,
                },
            )

    yield {
        "_final": True,
        "messages": working,
        "answer": answer,
        "tool_trace": tool_trace,
        "usage": usage_total,
    }


async def run_agent(
    *,
    slug: str,
    workspace_path: str,
    agent_id: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    adapter: OpenAICompatibleChatAdapter,
    max_steps: int,
    tenant_id: str,
    specialists: list[dict[str, Any]] | None = None,
    workspace_tools: list[dict[str, Any]] | None = None,
    on_step: StepCallback | None = None,
) -> dict[str, Any]:
    """兼容包装：收集 iter_agent_run 的最终结果。"""
    final: dict[str, Any] = {
        "messages": messages,
        "answer": "",
        "tool_trace": [],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    async for ev in iter_agent_run(
        slug=slug,
        workspace_path=workspace_path,
        agent_id=agent_id,
        messages=messages,
        tools=tools,
        adapter=adapter,
        max_steps=max_steps,
        tenant_id=tenant_id,
        specialists=specialists,
        workspace_tools=workspace_tools,
        on_step=on_step,
    ):
        if ev.get("_final"):
            final = {
                "messages": ev["messages"],
                "answer": ev["answer"],
                "tool_trace": ev["tool_trace"],
                "usage": ev["usage"],
            }
    return final
