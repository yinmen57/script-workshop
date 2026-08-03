# 技术栈与关键决策（已确认）

> 本文锁定企业级 LangChain 框架的默认选型，后续接口、表结构、Agent 规范均以此为准。仅设计，不涉及代码实现。

## 1. 语言与编排栈

| 项 | 决策 | 理由 |
|----|------|------|
| 语言 | **Python 3.11+** | LangChain / LangGraph 生态最完整，RAG 与 Agent 资料最多 |
| Web API | **FastAPI** | 原生异步、OpenAPI、流式（SSE）友好 |
| 编排内核 | **LangChain + LangGraph** | Chat/RAG 用 LangChain；有状态多步 Agent 用 LangGraph |
| 配置与密钥 | 环境变量 + 配置中心（逻辑层），密钥加密落库 | 禁止厂商 Key 写死在代码或镜像中 |

**对等替代（非默认）**：若组织强制 Java，分层与领域模型不变，实现层替换为 LangChain4j + Spring Boot；向量 Adapter 与治理接口保持同构。

## 2. 前端管理端

| 项 | 决策 | 理由 |
|----|------|------|
| 框架 | **React 18 + TypeScript + Vite** | 企业管理后台以受登录保护的单页应用为主，构建与部署简单 |
| UI | **Ant Design 5 + Ant Design Pro Components** | 模型、知识库、工具、审批、审计等后台场景可直接复用成熟的表格、表单与布局组件 |
| 路由 | **React Router 7** | 管理端路由、权限守卫与嵌套路由标准化 |
| 服务端状态 | **TanStack Query** | 统一管理 API 缓存、请求状态和失效刷新 |
| 客户端状态 | **Zustand** | 仅保存登录态、界面偏好等不属于服务端的数据 |
| 样式 | Ant Design Token + CSS Modules | 保持主题一致，避免引入第二套通用 UI 库 |

**前后端交互约束（前后端分离）**：

- 后端只提供 JSON/SSE API；前端为独立 SPA，二者进程、构建、部署均可分开。
- FastAPI 通过 OpenAPI 生成 TypeScript 类型与请求客户端；页面禁止直接拼写接口地址和数据结构。
- 流式 Chat 使用 `Fetch + ReadableStream` 消费后端 SSE，以携带认证头并支持主动取消；不使用 `EventSource`。
- 首期仅建设管理后台；业务侧聊天界面通过 API / SDK 接入，不与管理端强行共用前端工程。
- 不采用 Next.js / SSR：当前管理端不以 SEO 为目标，FastAPI 已提供 API 与流式响应，SSR 会额外引入 BFF 与部署复杂度。

## 3. 首期向量库

| 阶段 | 向量库 | 说明 |
|------|--------|------|
| **P0（首期）** | **Qdrant** | 专用向量库，过滤（payload filter）与多租户隔离友好，LangChain 集成成熟，水平扩展清晰 |
| P1 | 增加 **Milvus** 或 **PgVector** Adapter | 按规模/运维偏好扩展，业务代码不改 |
| 可选 | Elasticsearch / OpenSearch | 已有搜索中台时复用 |

**约束**：

- `KnowledgeBase` 创建时绑定：`embedding_model` + `dimension` + `vector_store_instance`
- 维度变更必须重建 Collection，禁止在线改维度继续写入
- Redis 仅作缓存/会话/限流，**不作首期向量主存**
- 检索必须带 payload 过滤：`tenant_id` + `kb_id`（或按 KB 独立 Collection）

## 4. 配套基础设施（P0）

| 组件 | 用途 |
|------|------|
| MySQL 8+ | 租户、应用、文档元数据、审计、RBAC |
| Redis | 会话缓存、限流计数、短期 Memory 可选 |
| **Qdrant** | 向量存储（独立部署；HTTP/gRPC） |
| 对象存储（OSS/S3/本地） | 原始文档 |
| **Celery + RabbitMQ**（作业总线唯一） | 全部异步作业：剧本 job、生图/生视频、Beat 调度；见 [09-celery-rabbitmq-job-bus.md](./09-celery-rabbitmq-job-bus.md)。Redis Stream 作业路径废弃 |

## 5. 本地推理与检索模型（已确认）

| 角色 | 模型 | 部署 | 说明 |
|------|------|------|------|
| **Embedding** | **bge-m3** | **外部** Xinference（`model_type=embedding`） | 多语种、长文本友好；P0 先用 **稠密向量（dense）** 写入 Qdrant |
| **Reranker** | **bge-reranker-v2-m3** | **外部** Xinference（`model_type=rerank`） | 初检 top_n 后再精排，提升剧本/物品相关片段精度 |
| **Chat / 生成** | **自有接入（不锁定具体型号）** | 业务方自行提供的推理地址 | 与 Embedding/Rerank **完全解耦**；按应用配置切换 |

**Chat：自有链接（已确认）**

- 不绑定某一家云或某一个本地 Chat 模型名；由租户/应用在「模型管理」里登记自己的 endpoint
- **优先 OpenAI 兼容**：配置 `base_url` + `api_key` + `model_name` 即可（自建网关、vLLM、Xinference Chat、DeepSeek、通义兼容模式等）
- 支持 `primary` / `fallback` 两条自有链接，超时或 5xx 时降级
- 框架只负责：鉴权注入、超时熔断、Token/审计、按 App 选用哪条 Chat；**不负责**替用户托管 Chat GPU
- Embedding / Rerank 通过配置连外部 Xinference（bge-m3 / bge-reranker-v2-m3）；Chat 可指向完全不同的机器或厂商

**Xinference 约定（检索侧，外部独立服务）**

- **不在本项目内启动/部署**：Xinference 由运维或独立项目单独拉起；本框架只做客户端对接
- 连接方式：配置 **服务地址**（如 `http://<host>:9997`）+ **模型 UID**（Xinference 启动模型后返回的 `model_uid`，写入 `model_config.model_name`）
- 约定模型：Embedding = **bge-m3**；Rerank = **bge-reranker-v2-m3**（在外部 Xinference 上先 launch，再把 UID 登记到本平台）
- Embeddings：OpenAI 兼容 `/v1/embeddings`（`model` 填 UID）
- Rerank：Xinference Rerank API；应用侧 `Rerank Adapter` 对接
- 若业务也将 Chat 挂在同一外部 Xinference 上，只是 Chat 的一种可选「自有链接」，不是强制

**bge-m3 → Qdrant 约束（P0）**

- 默认按 dense 维度建 Collection（常见为 **1024**；以实际 `embeddings` 返回维度为准，写入 `knowledge_base.dimension`）
- 维度一旦写入知识库不可改；换模型或改维度必须重建索引
- P1 可选：启用 bge-m3 的 sparse / multi-vector 能力做混合检索（非 P0 必做）

**RAG 查询链路（与模型对应）**

```text
Query → bge-m3 Embedding → Qdrant 召回 top_n（如 20～50）
     → bge-reranker-v2-m3 精排取 top_k（如 5）
     → Chat 模型生成（物品描述等）
```

## 6. 模型接入策略（通用）

- **优先 OpenAI 兼容协议**（Xinference / DeepSeek / 通义代理等走同一 Chat·Embedding Adapter）
- 保留厂商原生 Adapter 扩展点（Rerank、特殊参数）
- 每个 `App` 配置 `primary` + `fallback` Chat 模型；超时/限流/5xx 触发降级
- Embedding、Rerank、Chat **三者分离**；禁止混用不同维度的 Embedding 写入同一知识库

## 7. 明确不做（首期）

- 低代码 Workflow 画布
- 绑定单一云厂商或单一向量库产品（Adapter 仍可扩展，但 P0 实现只做 Qdrant）
- 替代现有业务中台（本框架只做 AI 能力层）
- P0 不强依赖 bge-m3 的 sparse/ColBERT 全能力（先 dense + rerank）

## 8. 决策摘要

```
Python + FastAPI + LangChain/LangGraph
管理端：React 18 + TypeScript + Vite + Ant Design 5
业务库 MySQL + 向量库 Qdrant(P0) + Redis + OSS + MQ
检索侧：外部 Xinference（地址 + model_uid）→ Embedding=bge-m3，Rerank=bge-reranker-v2-m3
生成侧 Chat：业务自有链接（OpenAI 兼容 base_url，可换）
多租户 / RBAC / 审计 / 配额 为一等公民
Adapter：LLM / Embedding / Rerank / VectorStore / Tool 可插拔
```
