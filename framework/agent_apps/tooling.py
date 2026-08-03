"""业务工具桥接：按 App 的 tool_catalog / entrypoint 解析，不硬编码业务包。"""

from __future__ import annotations

import importlib
import inspect
import json
import time
import traceback
from typing import Any, Callable, get_type_hints

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from framework.core.tool_context import current_tenant_id


def _annotation_to_field(name: str, annotation: Any, default: Any) -> tuple[Any, Any]:
    if annotation is inspect.Parameter.empty:
        annotation = Any
    if default is inspect.Parameter.empty:
        return annotation, Field(..., description=name)
    return annotation | None, Field(default=default, description=name)


def _args_model_for(func: Callable[..., Any], model_name: str) -> type[BaseModel]:
    sig = inspect.signature(func)
    try:
        hints = get_type_hints(func)
    except Exception:  # noqa: BLE001
        hints = {}
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        if name in {"self", "cls"}:
            continue
        annotation = hints.get(name, param.annotation)
        fields[name] = _annotation_to_field(name, annotation, param.default)
    if not fields:
        return create_model(model_name)
    return create_model(model_name, **fields)


def resolve_entrypoint(entrypoint: str) -> Callable[..., Any]:
    """解析 module.path:func_name。"""
    if ":" not in entrypoint:
        raise ValueError(f"非法 entrypoint：{entrypoint}")
    module_path, func_name = entrypoint.split(":", 1)
    module_path = module_path.strip()
    func_name = func_name.strip()
    if not module_path or not func_name:
        raise ValueError(f"非法 entrypoint：{entrypoint}")
    module = importlib.import_module(module_path)
    func = getattr(module, func_name, None)
    if func is None or not callable(func):
        raise AttributeError(f"entrypoint 未找到可调用对象：{entrypoint}")
    return func


def wrap_business_tool(
    *,
    tool_id: str,
    func: Callable[..., Any],
    description: str,
    tenant_id: str,
) -> StructuredTool:
    """包装业务异步函数：注入 tenant_id，统一 JSON 序列化错误。"""
    args_model = _args_model_for(func, f"Args_{tool_id.replace('-', '_')}")

    async def _run(**kwargs: Any) -> str:
        token = current_tenant_id.set(tenant_id)
        started = time.perf_counter()
        try:
            cleaned = {k: v for k, v in kwargs.items() if v is not None}
            if inspect.iscoroutinefunction(func):
                result = await func(**cleaned)
            else:
                result = func(**cleaned)
            if isinstance(result, str):
                return result
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {
                    "error": str(exc),
                    "traceback": traceback.format_exc(limit=5),
                    "duration_ms": int((time.perf_counter() - started) * 1000),
                },
                ensure_ascii=False,
            )
        finally:
            current_tenant_id.reset(token)

    return StructuredTool.from_function(
        coroutine=_run,
        name=tool_id,
        description=description,
        args_schema=args_model,
    )


def build_retrieve_tool(*, namespaces: list[str], tenant_id: str) -> StructuredTool:
    """内置知识检索：namespace 限定为 Agent 白名单枚举。"""
    if not namespaces:
        raise ValueError("retrieve 需要至少一个 namespace")
    ns_literal = tuple(namespaces)

    class RetrieveArgs(BaseModel):
        namespace: str = Field(description=f"命名空间，只能是：{', '.join(namespaces)}")
        query: str = Field(description="检索问题")
        top_k: int = Field(default=5, description="返回条数，默认 5")

    async def _retrieve(namespace: str, query: str, top_k: int = 5) -> str:
        from framework.governance import vector_namespace_service

        namespace = (namespace or "").strip()
        query = (query or "").strip()
        if not namespace or not query:
            return json.dumps({"error": "namespace 与 query 必填"}, ensure_ascii=False)
        if namespace not in ns_literal:
            return json.dumps(
                {
                    "error": (
                        f"namespace 不在允许范围：{namespace}，"
                        f"可选值 {', '.join(ns_literal)}"
                    )
                },
                ensure_ascii=False,
            )
        try:
            result = await vector_namespace_service.search(
                tenant_id=tenant_id,
                namespaces=[namespace],
                query=query,
                top_k=int(top_k or 5),
            )
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    return StructuredTool.from_function(
        coroutine=_retrieve,
        name="retrieve",
        description=(
            "在下列知识库命名空间中检索相关文本片段：" + "、".join(namespaces)
        ),
        args_schema=RetrieveArgs,
    )


def build_business_tools(
    *,
    tool_ids: list[str],
    tenant_id: str,
    tool_catalog: dict[str, dict[str, Any]] | None = None,
    namespaces: list[str] | None = None,
    workspace_path: str | None = None,
) -> list[StructuredTool]:
    """按声明的 tool_id 与 App tool_catalog 组装 LangChain 工具列表。"""
    del workspace_path
    catalog = tool_catalog or {}
    tools: list[StructuredTool] = []
    for tool_id in tool_ids:
        if tool_id == "retrieve":
            tools.append(
                build_retrieve_tool(
                    namespaces=list(namespaces or []),
                    tenant_id=tenant_id,
                )
            )
            continue
        meta = catalog.get(tool_id)
        if meta is None:
            raise ValueError(f"未知工具：{tool_id}")
        entrypoint = meta.get("entrypoint")
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            raise ValueError(f"工具缺少 entrypoint：{tool_id}")
        description = str(meta.get("description") or tool_id)
        func = resolve_entrypoint(entrypoint)
        tools.append(
            wrap_business_tool(
                tool_id=tool_id,
                func=func,
                description=description,
                tenant_id=tenant_id,
            )
        )
    return tools
