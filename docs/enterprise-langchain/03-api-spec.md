# OpenAPI 接口清单（草案）

> 基础路径：`/api/v1`  
> 鉴权：`Authorization: Bearer <api_key_or_jwt>`  
> 所有请求/响应携带或回传 `X-Request-Id`；业务体建议含 `tenant_id`（也可从凭证解析）。  
> 流式接口：`Accept: text/event-stream`（SSE）。
> 阶段标识：未标注的接口属于 P0；标记 **P1** 的接口仅在 P1 开放。

## 1. 通用约定

### 1.1 统一错误体

```json
{
  "code": "QUOTA_EXCEEDED",
  "message": "tenant token budget exceeded",
  "request_id": "req_xxx",
  "details": {}
}
```

常见 `code`：`UNAUTHORIZED`、`FORBIDDEN`、`NOT_FOUND`、`VALIDATION_ERROR`、`QUOTA_EXCEEDED`、`MODEL_UNAVAILABLE`、`RAG_EMPTY`、`AGENT_STEP_LIMIT`、`TOOL_DENIED`、`INTERNAL_ERROR`。

### 1.2 分页

查询参数：`page`（从 1）、`page_size`（默认 20，最大 100）  
响应：`{ "items": [], "total": 0, "page": 1, "page_size": 20 }`

---

## 2. 认证与当前用户

管理端使用 JWT；业务系统使用 API 凭证。JWT 中的 `tenant_id`、`user_id` 和 `permissions` 为服务端唯一可信来源，请求体不接受这些字段覆盖。

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/auth/login` | 账号密码登录，签发 access/refresh token | 匿名 |
| POST | `/auth/refresh` | 以 refresh token 刷新 access token | 已登录 |
| POST | `/auth/logout` | 注销当前 refresh token | 已登录 |
| GET | `/auth/me` | 当前用户、租户及权限集合 | 已登录 |

`POST /auth/login` 请求：`{ "account": "name", "password": "..." }`；响应：`{ "access_token": "...", "refresh_token": "...", "expires_in": 3600 }`。

`GET /auth/me` 响应：`{ "user_id": "usr_xxx", "display_name": "...", "tenant_id": "ten_xxx", "permissions": ["app:write"] }`。

---

## 3. 对话与生成

### 3.1 创建/继续对话

`POST /chat/completions`

| 字段 | 类型 | 说明 |
|------|------|------|
| app_id | string | 必填，应用 ID |
| session_id | string | 可选；空则新建会话 |
| message | string | 用户消息 |
| stream | bool | 默认 false |
| variables | object | Prompt 变量 |
| metadata | object | 业务透传 |

**非流式响应（摘要）**

```json
{
  "request_id": "req_xxx",
  "session_id": "ses_xxx",
  "answer": "...",
  "model": "deepseek-chat",
  "usage": { "prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200 },
  "citations": []
}
```

若 App 绑定知识库，`citations` 为命中切片列表（见 RAG）。

**SSE 事件类型**：`delta`（增量文本）、`citation`、`usage`、`error`、`done`。

### 3.2 会话

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sessions` | 列出会话（按 app/user） |
| GET | `/sessions/{session_id}` | 会话详情 |
| GET | `/sessions/{session_id}/messages` | 消息历史 |
| DELETE | `/sessions/{session_id}` | 删除会话（含 Memory） |

---

## 4. RAG / 知识库

### 4.1 知识库 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge-bases` | 创建（绑定 embedding、dimension、vector_store） |
| GET | `/knowledge-bases` | 列表 |
| GET | `/knowledge-bases/{kb_id}` | 详情 |
| PATCH | `/knowledge-bases/{kb_id}` | 更新元数据（**不可直接改 dimension**） |
| DELETE | `/knowledge-bases/{kb_id}` | 删除（级联文档与向量，需确认参数） |

**创建请求关键字段**

```json
{
  "name": "员工手册",
  "embedding_model_id": "mdl_emb_xxx",
  "dimension": 1024,
  "vector_store": "qdrant",
  "chunk_size": 800,
  "chunk_overlap": 100
}
```

### 4.2 文档

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/knowledge-bases/{kb_id}/documents` | `multipart/form-data` 上传文件（字段 `file`，可选 `title`），返回 doc_id，异步向量化 |
| POST | `/knowledge-bases/{kb_id}/documents/text` | 直接提交文本入库 |
| GET | `/knowledge-bases/{kb_id}/documents` | 文档列表 |
| GET | `/documents/{doc_id}` | 文档状态：`pending/processing/ready/failed` |
| POST | `/documents/{doc_id}/reindex` | 重新向量化 |
| DELETE | `/documents/{doc_id}` | 删除文档及向量 |

文档列表支持 `status`、`source_type`、`keyword`、`page`、`page_size`。上传和文本入库成功响应均为
`{ "doc_id": "doc_xxx", "status": "pending", "job_id": "job_xxx" }`。`GET /documents/{doc_id}` 返回 `chunk_count`、`error_message` 和最新 `job_id`。

### 4.3 检索与问答

`POST /rag/query`

```json
{
  "app_id": "app_xxx",
  "query": "年假怎么请？",
  "knowledge_base_ids": ["kb_1"],
  "top_k": 5,
  "rerank": true,
  "stream": false
}
```

响应含 `answer`、`citations[]`（`doc_id`、`chunk_id`、`score`、`content`、`source`）。

`POST /rag/search`：仅检索不生成，供调试与外部编排。

### 4.4 切片（运维/调试）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/documents/{doc_id}/chunks` | 切片列表 |
| GET | `/chunks/{chunk_id}` | 单切片 |

---

## 5. Agent（P1）

`POST /agent/runs`

```json
{
  "app_id": "app_xxx",
  "session_id": "ses_xxx",
  "input": "帮我查订单 ORD-1 的物流并总结",
  "tool_allowlist": [],
  "max_steps": 8,
  "stream": true
}
```

响应/流式事件额外包含：`tool_call`、`tool_result`、`approval_required`、`final`。

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/agent/runs` | 运行列表，支持 `app_id`、`status`、`from`、`to`、分页 |
| GET | `/agent/runs/{run_id}` | 运行详情与步骤轨迹 |
| GET | `/agent/runs/pending-approvals` | 当前租户待审批运行，支持分页 |
| POST | `/agent/runs/{run_id}/approve` | 人工审批高危工具，要求 `agent:approve` |
| POST | `/agent/runs/{run_id}/cancel` | 取消运行 |

工具治理见 [05-agent-governance.md](./05-agent-governance.md)。

审批请求体：`{ "decision": "approve|reject", "comment": "..." }`。运行详情返回 `status`、`current_step`、`max_steps`、`input`、`final_output` 以及脱敏后的 `steps[]`；当状态为 `waiting_approval` 时额外返回 `pending_tool`。

---

## 6. 模型与 Prompt（管理）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/models` | 登记模型（provider、base_url、密文 api_key、类型 chat/embedding/**rerank**） |
| GET | `/models` | 列表（密钥脱敏） |
| GET | `/models/{model_id}` | 详情（密钥始终不返回） |
| PATCH | `/models/{model_id}` | 更新非密钥字段，传入 `api_key` 时替换密钥 |
| DELETE | `/models/{model_id}` | 删除未被知识库或 App 引用的模型 |
| POST | `/models/{model_id}/test` | 连通性探测 |
| POST | `/prompts` | **P1** 创建 Prompt 模板及首个草稿版本 |
| GET | `/prompts` | **P1** 模板列表 |
| GET | `/prompts/{prompt_id}` | **P1** 模板与当前版本详情 |
| POST | `/prompts/{prompt_id}/versions` | **P1** 新建草稿版本 |
| POST | `/prompts/{prompt_id}/publish` | **P1** 发布指定版本 |
| GET | `/prompts/{prompt_id}/versions` | **P1** 版本历史 |

---

## 7. 应用 App

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/apps` | 创建应用 |
| GET | `/apps` | 列表 |
| GET | `/apps/{app_id}` | 详情（含策略） |
| PATCH | `/apps/{app_id}` | 更新：模型策略、知识库、工具、Prompt、RAG 参数、安全策略 |
| DELETE | `/apps/{app_id}` | 停用/删除 |

**App 策略字段（逻辑）**

```json
{
  "chat_model_policy": {
    "primary_model_id": "mdl_a",
    "timeout_ms": 60000,
    "_comment": "mdl_* 指向业务自有 Chat 链接（base_url + model_name），非框架内置模型"
  },
  "knowledge_base_ids": ["kb_1"],
  "tool_ids": ["tool_order_query"],
  "prompt_id": "prt_xxx",
  "prompt_version": 3,
  "rag": {
    "top_k": 5,
    "recall_n": 30,
    "rerank": true,
    "rerank_model_id": "mdl_rerank_xxx"
  },
  "safety_policy": { "input_moderation": true, "output_moderation": true },
  "agent": { "max_steps": 8, "require_approval_for": ["high"] }
}
```

---

## 8. 工具注册（P1）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tools` | 注册工具（HTTP/SQL/RPC 元数据） |
| GET | `/tools` | 列表 |
| GET | `/tools/{tool_id}` | 工具详情 |
| PATCH | `/tools/{tool_id}` | 更新 |
| POST | `/tools/{tool_id}/enable` | 启用 |
| POST | `/tools/{tool_id}/disable` | 禁用 |

---

## 9. 治理：租户 / 配额 / 审计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/tenants` | 创建租户（平台管理员） |
| GET | `/tenants` | 租户列表（平台管理员） |
| GET | `/tenants/{tenant_id}` | 租户详情（平台管理员） |
| PATCH | `/tenants/{tenant_id}` | 修改名称或 `active/suspended` 状态（平台管理员） |
| GET | `/tenants/{tenant_id}/quota` | 查看配额使用 |
| PUT | `/tenants/{tenant_id}/quota` | **P1** 设置 RPM/Token/预算 |
| POST | `/api-credentials` | 创建 API 凭证，密钥仅在本响应返回一次 |
| GET | `/api-credentials` | API 凭证列表，仅返回 key_prefix、scopes、status、expires_at |
| PATCH | `/api-credentials/{credential_id}` | 修改名称、scope、过期时间或状态 |
| DELETE | `/api-credentials/{credential_id}` | 吊销 API 凭证 |
| GET | `/users` | **P1** 用户列表 |
| POST | `/users` | **P1** 创建用户 |
| PATCH | `/users/{user_id}` | **P1** 更新用户状态与角色 |
| GET | `/roles` | **P1** 角色及权限点列表 |
| PUT | `/knowledge-bases/{kb_id}/acl` | **P1** 覆盖知识库 ACL |
| GET | `/audit/logs` | 审计查询（时间、app、user、request_id） |
| GET | `/traces/{request_id}` | 单次调用追踪（模型、检索、工具、耗时、usage） |

---

## 10. 健康与运维

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 存活 |
| GET | `/ready` | 依赖就绪（MySQL/Redis/Qdrant） |
| GET | `/metrics` | Prometheus 指标（可选） |

`GET /ready` 响应：`{ "ready": true, "dependencies": { "mysql": "up", "redis": "up", "qdrant": "up" } }`。

---

## 11. 管理端补充契约

### 11.1 列表筛选与权限

- `GET /apps` 支持 `status`、`keyword`、分页；需要 `app:read`，创建、更新、删除需要 `app:write`。
- `GET /knowledge-bases` 支持 `status`、`keyword`、分页；读写分别需要 `kb:read`、`kb:write`。
- `GET /models` 支持 `model_type`、`status`、`keyword`、分页；读写分别需要 `model:read`、`model:write`。
- `GET /tools` 支持 `tool_type`、`risk_level`、`status`、`keyword`、分页；所有工具管理接口需要 `tool:write`。
- `GET /audit/logs` 支持 `from`、`to`、`app_id`、`user_id`、`request_id`、`action`、分页；需要 `audit:read`。
- `GET /sessions` 支持 `app_id`、`user_id`、`status`、分页，并始终按凭证所属租户过滤。

### 11.2 App 配置映射

`GET /apps/{app_id}` 与 `PATCH /apps/{app_id}` 使用以下稳定结构。`PATCH` 仅提交待更新字段：

```json
{
  "name": "员工助手",
  "status": "enabled",
  "chat_model_policy": { "primary_model_id": "mdl_chat_xxx", "timeout_ms": 60000 },
  "knowledge_bases": [{ "kb_id": "kb_xxx", "weight": 1 }],
  "tool_ids": ["tool_xxx"],
  "prompt": { "prompt_id": "prt_xxx", "version": 3 },
  "rag": { "top_k": 5, "recall_n": 30, "rerank": true, "rerank_model_id": "mdl_rerank_xxx" },
  "agent": { "max_steps": 8, "require_approval_for": ["high"] },
  "safety_policy": { "input_moderation": true, "output_moderation": true }
}
```

- `chat_model_policy.primary_model_id` 映射 `app.primary_model_id`；`fallback_model_id` 不作为本期 API 字段。
- `knowledge_bases` 映射 `app_knowledge_base(app_id, kb_id, weight)`；`tool_ids` 映射 `app_tool`。
- `prompt` 映射 `app.prompt_id`、`app.prompt_version`，仅允许引用已发布版本。
- `rag.top_k`、`rag.rerank` 映射 `app.rag_top_k`、`app.rag_rerank`；`recall_n`、`rerank_model_id` 存入 `app.extra`。
- Embedding 模型和维度由 `knowledge_base.embedding_model_id`、`knowledge_base.dimension` 唯一确定，App 不得覆盖。

### 11.3 SSE 事件体

`POST /chat/completions`、`POST /rag/query`、`POST /agent/runs` 的流式响应均使用 `event: <type>` 与 JSON `data`。所有事件含 `request_id`。

| event | data 关键字段 |
|------|---------------|
| `delta` | `text` |
| `citation` | `doc_id`、`chunk_id`、`score`、`content`、`source` |
| `tool_call` | `run_id`、`step`、`tool_id`、`args_summary` |
| `tool_result` | `run_id`、`step`、`tool_id`、`output_summary` |
| `approval_required` | `run_id`、`pending_tool`、`expires_at` |
| `usage` | `prompt_tokens`、`completion_tokens`、`total_tokens` |
| `error` | `code`、`message`、`details` |
| `done` / `final` | `session_id`、`run_id`（Agent）、`answer`（final） |

### 11.4 工作台与异步任务

| 方法 | 路径 | 阶段 | 说明 |
|------|------|------|------|
| GET | `/dashboard/overview` | P0 | 当前租户的配额用量、近 24 小时调用量/失败数、文档状态统计 |
| GET | `/ingest-jobs` | P0 | 文档导入任务列表，支持 `doc_id`、`status`、分页 |
| GET | `/ingest-jobs/{job_id}` | P0 | 单任务状态、attempts、last_error |

`GET /dashboard/overview` 返回 `quota`、`request_count_24h`、`failed_count_24h`、`documents_by_status`。P1 在此响应增加 `pending_approval_count`。

### 11.5 创建与删除约束

- `DELETE /knowledge-bases/{kb_id}?confirm=true` 需要 `kb:write`；缺少 `confirm=true` 返回 `VALIDATION_ERROR`，删除级联文档、切片和向量。
- 创建模型时，`model_type=embedding` 必填 `dimension`；`model_type=rerank` 不得填写 `dimension`。密钥写入后不再回传。
- 创建 API 凭证响应为 `{ "credential": {...}, "api_key": "sk_..." }`；`api_key` 仅出现一次。
- 工具创建/更新时必须提供 `input_schema`、`risk_level`、含超时设置的 `config`；high 工具需要 `tool:write`。

---

## 12. P0 最小接口集

上线骨架只需实现：

1. 认证与当前用户：`/auth/*`
2. `POST /chat/completions`（含可选 RAG）
3. 知识库 + 文档上传/状态 + `POST /rag/search` + ingest job 查询
4. 模型、应用、API 凭证、租户基础管理
5. `GET /dashboard/overview`、`GET /traces/{request_id}`、基础审计写入
6. `GET /health`、`GET /ready`
