# agent_apps：框架核心（实现与使用）

多 Agent 应用框架：内存注册表 + LangGraph ReAct + 工具桥接。  
业务 App 以插件注入，本包**不**硬编码业务模块名。

相关：API 见 [apps/api/README.md](../../apps/api/README.md)；管理端见 [apps/admin/README.md](../../apps/admin/README.md)；设计备忘见 [framework/design/](../../framework/design/)。

## 模块职责

| 文件 | 职责 |
|------|------|
| `spec.py` | 通用 `AgentSpec`（prompt / tools / namespaces） |
| `registry.py` | `register_app(s)`、校验、workspace/runtime 视图 |
| `runtime.py` | `build_agent_graph` / `iter_agent_run`；handoff；可选 `agent_id` 单测 |
| `tooling.py` | `tool_catalog` + `entrypoint` → LangChain Tool；内置 `retrieve` |
| `llm.py` | 从 AI Key 构建 Chat 模型 |

## 注册如何工作

```text
业务 build_app_spec()
  → business.apps.bootstrap.register_business_apps()
  → register_apps([builders...])
  → _finalize_app（coordinator / namespaces / workspace）
  → 内存 _apps[slug]
```

- 启动注入点：框架 API lifespan（`apps/api/app/main.py`）
- 真源是代码；不落 Agent 元数据表
- 改 SPEC 后需**重启框架 API**

### 业务侧声明（示例：script_workshop）

1. `agents/<id>.py` 定义 `SPEC = AgentSpec(...)`
2. 加入 `ALL_AGENTS`
3. `prompts/<agent_id>/system.md`
4. `tool_meta.py` + `tools.py`（entrypoint 指向 tools 函数）
5. `app.py` 提供 slug / tenant_id / coordinator
6. `__init__.py` 实现 `build_app_spec()`
7. `bootstrap.register_business_apps` 挂上 builder

约束：唯一 `coordinator`；Agent `namespaces` 必须在 `knowledge/manifest.yaml` 声明。

### 注册表读法

| API | 方法 | 用途 |
|-----|------|------|
| 配置 | `get_workspace` | Admin 详情（含 prompt 全文；展示 `delegate_to_*`） |
| 运行 | `get_runtime_app` | Chat：agents + `tool_catalog` + system_prompt |

## 运行时如何工作

`iter_agent_run(app, messages, max_steps=, agent_id=)`：

- 未传 / coordinator：挂全部 specialist 的 `delegate_to_*`
- specialist：只构图该 Agent，不挂 handoff
- 工具经 `tool_catalog[id].entrypoint` 动态 import
- Callbacks 产出 thought/tool step，供 SSE

Chat 侧：`governance.chat_service.prepare_completion` 解析 `agent_id`，换 system prompt / max_steps，再驱动 runtime。

## 扩展清单

**新 Agent（同 App）**：SPEC → prompts → ALL_AGENTS →（可选新 tool）→ 重启框架 API。

**新 App**：新建 `business/apps/<app>/` + `build_app_spec`，写入 bootstrap 的 `register_apps([...])`，重启框架 API。

## 不做

- YAML apps-space 扫描  
- UI/DB CRUD 注册 Agent  
- 在本包 import `business.script` / 具体业务 tools 模块  
