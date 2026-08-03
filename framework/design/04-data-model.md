# 核心表结构草案

> 业务元数据默认落 **MySQL 8+**；向量落 **Qdrant**（独立集群/单机均可）。  
> 所有业务表含：`id`、`tenant_id`（平台级表除外）、`created_at`、`updated_at`；逻辑删除可用 `deleted_at`。  
> 以下为逻辑草案，字段类型可按 ORM 微调。

## 1. 库划分

| 库/实例 | 内容 |
|---------|------|
| MySQL `ai_platform` | 租户、用户权限、模型、应用、知识库元数据、文档、会话、工具、审计、配额 |
| **Qdrant** | 按知识库 Collection（或统一 Collection + payload 过滤）存储切片向量 |
| Redis | 限流计数、会话热缓存、分布式锁、MQ（若用 Stream） |
| OSS | 原始文件对象 |

---

## 2. 租户与权限

### 2.1 `tenant`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | 租户 ID |
| name | varchar(128) | 名称 |
| status | varchar(16) | active/suspended |
| created_at / updated_at | datetime | |

### 2.2 `tenant_quota`

| 字段 | 类型 | 说明 |
|------|------|------|
| tenant_id | varchar(32) PK | |
| rpm_limit | int | 每分钟请求 |
| token_daily_limit | bigint | 日 Token |
| budget_monthly | decimal | 月预算（可选） |
| rpm_used_window | int | 由 Redis 实时计，库内可存快照 |
| token_used_daily | bigint | 日用量快照 |

### 2.3 `user_account` / `role` / `user_role` / `permission`

常规 RBAC：

- 权限点示例：`model:write`、`kb:read`、`kb:write`、`app:write`、`tool:invoke:{tool_id}`、`audit:read`、`agent:approve`
- 知识库级授权可用 `kb_acl(tenant_id, kb_id, subject_type, subject_id, action)`

### 2.4 `api_credential`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| name | varchar(64) | |
| key_hash | varchar(128) | 仅存哈希 |
| key_prefix | varchar(16) | 展示用前缀 |
| scopes | json | 允许的 app/能力 |
| status | varchar(16) | |
| expires_at | datetime | 可空 |

---

## 3. 模型与 Prompt

### 3.1 `model_config`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | 平台共享模型可用特殊 tenant 或 `is_system` |
| name | varchar(128) | |
| provider | varchar(32) | openai_compatible / ollama / azure / ... |
| model_type | varchar(16) | chat / embedding / **rerank** |
| model_name | varchar(128) | 厂商模型名；Xinference 时填 **model_uid** |
| base_url | varchar(512) | 可空；Xinference 时填服务地址（如 `http://host:9997`） |
| api_key_cipher | text | 加密密文 |
| dimension | int | embedding 时必填 |
| extra | json | temperature 默认值等 |
| status | varchar(16) | |

### 3.2 `prompt_template` / `prompt_version`

**prompt_template**：`id, tenant_id, name, latest_version`  

**prompt_version**：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| prompt_id | varchar(32) | |
| version | int | |
| content | mediumtext | 含变量占位 |
| variables_schema | json | |
| status | varchar(16) | draft/published |
| published_at | datetime | |

---

## 4. 应用

### 4.1 `app`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| name | varchar(128) | |
| status | varchar(16) | |
| primary_model_id | varchar(32) | |
| fallback_model_id | varchar(32) | 可空 |
| prompt_id | varchar(32) | |
| prompt_version | int | 钉死已发布版本 |
| rag_top_k | int | |
| rag_rerank | tinyint | |
| agent_max_steps | int | 默认 8 |
| safety_policy | json | |
| extra | json | |

### 4.2 `app_knowledge_base`（应用绑定知识库）

`app_id, kb_id, weight`（联合主键）

### 4.3 `app_tool`

`app_id, tool_id`（联合主键）+ `enabled`

---

## 5. 知识库与文档（MySQL 元数据）

### 5.1 `knowledge_base`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| name | varchar(128) | |
| embedding_model_id | varchar(32) | |
| dimension | int | **创建后不可变** |
| vector_store | varchar(32) | **qdrant**（P0）/ milvus / pgvector / ... |
| vector_collection | varchar(128) | Qdrant collection 名 |
| chunk_size | int | |
| chunk_overlap | int | |
| status | varchar(16) | |

### 5.2 `document`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| kb_id | varchar(32) | |
| title | varchar(256) | |
| source_type | varchar(32) | upload/url/text |
| uri | varchar(1024) | OSS 路径或 URL |
| content_hash | varchar(64) | 去重 |
| status | varchar(16) | pending/processing/ready/failed |
| error_message | varchar(1024) | |
| chunk_count | int | |
| meta | json | |

### 5.3 `document_chunk`（可选元数据镜像）

便于管理端展示；向量本体在 Qdrant。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | 与向量侧 chunk_id 一致 |
| tenant_id | varchar(32) | |
| kb_id | varchar(32) | |
| doc_id | varchar(32) | |
| ordinal | int | 序 |
| content | mediumtext | |
| token_estimate | int | |
| meta | json | 页码、标题路径等 |

---

## 6. Qdrant 侧（首期）

### 6.1 Collection 策略（二选一，P0 推荐 A）

| 策略 | 做法 | 适用 |
|------|------|------|
| **A. 每知识库一 Collection** | 名如 `kb_{kb_id}`，创建时指定 `vector.size = dimension` | 隔离清晰、删库简单（推荐） |
| B. 租户级统一 Collection | 名如 `tenant_{tenant_id}`，payload 含 `kb_id` | Collection 数量更少 |

### 6.2 Point 结构（逻辑）

| 项 | 说明 |
|----|------|
| id | 使用 `chunk_id`（UUID 或字符串 ID，与 MySQL `document_chunk.id` 一致） |
| vector | 长度 = 知识库 `dimension` |
| payload.tenant_id | **检索必带过滤** |
| payload.kb_id | **检索必带过滤**（策略 B 时尤其重要） |
| payload.doc_id | 按文档删除 / 重建 |
| payload.content | 原文切片（或只存引用，原文只放 MySQL） |
| payload.meta | 页码、标题路径等 |
| payload.created_at | ISO 时间 |

### 6.3 索引与过滤

- Payload 索引：`tenant_id`、`kb_id`、`doc_id`（keyword）
- 相似度：默认 Cosine（与多数 Embedding 一致；创建 Collection 时固定 distance）
- 删除文档：`Filter doc_id = ?` 后 delete points
- 检索：`query_vector` + `Filter must=[tenant_id, kb_id]` + `top_k`

**规则**：

- 同一 Collection 的 `vector.size` 创建后不可变；改维度需新建 Collection 并迁移
- 禁止跨租户不带 filter 的全局检索
- Adapter 统一接口仍为：`upsert / similarity_search / delete_by_doc`

---

## 7. 会话与追踪

### 7.1 `chat_session`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| app_id | varchar(32) | |
| user_id | varchar(64) | 可空（仅 API Key 时） |
| title | varchar(256) | |
| status | varchar(16) | |

### 7.2 `chat_message`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| session_id | varchar(32) | |
| role | varchar(16) | user/assistant/system/tool |
| content | mediumtext | 脱敏策略按合规 |
| token_count | int | |
| request_id | varchar(64) | |
| created_at | datetime | |

### 7.3 `run_trace`

| 字段 | 类型 | 说明 |
|------|------|------|
| request_id | varchar(64) PK | |
| tenant_id | varchar(32) | |
| app_id | varchar(32) | |
| session_id | varchar(32) | |
| run_type | varchar(16) | chat/rag/agent |
| model_id | varchar(32) | 实际使用（含降级后） |
| status | varchar(16) | success/error/cancelled |
| latency_ms | int | |
| prompt_tokens | int | |
| completion_tokens | int | |
| error_code | varchar(64) | |
| detail | json | 检索命中摘要、工具步骤等（控制体积） |
| created_at | datetime | |

### 7.4 `audit_log`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint PK AI | |
| tenant_id | varchar(32) | |
| actor | varchar(64) | user/api_key |
| action | varchar(64) | |
| resource_type | varchar(32) | |
| resource_id | varchar(64) | |
| request_id | varchar(64) | |
| ip | varchar(64) | |
| payload | json | 已脱敏 |
| created_at | datetime | |

---

## 8. 工具与 Agent 运行

### 8.1 `tool_definition`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| name | varchar(128) | |
| description | varchar(1024) | 给 LLM 看 |
| tool_type | varchar(32) | http/sql_readonly/rpc/retriever |
| risk_level | varchar(16) | low/medium/high |
| input_schema | json | JSON Schema |
| config | json | URL、超时、数据源等（密钥引用） |
| status | varchar(16) | enabled/disabled |

### 8.2 `agent_run`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | run_id |
| request_id | varchar(64) | |
| tenant_id | varchar(32) | |
| app_id | varchar(32) | |
| session_id | varchar(32) | |
| status | varchar(16) | running/waiting_approval/succeeded/failed/cancelled |
| current_step | int | |
| max_steps | int | |
| input | mediumtext | |
| final_output | mediumtext | |
| created_at / updated_at | datetime | |

### 8.3 `agent_run_step`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| run_id | varchar(32) | |
| step_no | int | |
| node | varchar(32) | plan/tool/observe/approve/finalize |
| tool_id | varchar(32) | 可空 |
| tool_input | json | 脱敏 |
| tool_output | json | 截断存储 |
| status | varchar(16) | |
| latency_ms | int | |
| created_at | datetime | |

---

## 9. 异步任务

### 9.1 `ingest_job`

| 字段 | 类型 | 说明 |
|------|------|------|
| id | varchar(32) PK | |
| tenant_id | varchar(32) | |
| doc_id | varchar(32) | |
| job_type | varchar(32) | parse/embed/reindex |
| status | varchar(16) | |
| attempts | int | |
| last_error | varchar(1024) | |
| created_at / updated_at | datetime | |

队列消息体至少含：`job_id, tenant_id, doc_id, kb_id`。

---

## 10. 索引与隔离建议

1. 所有查询默认 `WHERE tenant_id = ?`  
2. 向量检索：`tenant_id + kb_id` 过滤后再做相似度  
3. `run_trace.request_id`、`audit_log(tenant_id, created_at)`、`document(kb_id, status)` 建索引  
4. 密钥类字段禁止明文日志；`api_credential` 只存哈希  

## 11. 与领域对象映射

| 领域 | 主表 |
|------|------|
| Tenant | tenant, tenant_quota |
| App | app, app_knowledge_base, app_tool |
| ModelConfig | model_config |
| KnowledgeBase | knowledge_base |
| Document/Chunk | document, document_chunk；向量点在 Qdrant Collection |
| Session/Message | chat_session, chat_message |
| ToolDefinition | tool_definition |
| RunTrace | run_trace, agent_run, agent_run_step |
