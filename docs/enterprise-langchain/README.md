# LangChain 企业级框架设计（仅设计）

本目录为架构与规范交付物，**不含业务代码实现**。

> **定位已修订**：项目收敛为「Agent 开发框架」，管理端只保留应用空间与调试台，知识库/模型不再做产品化管理。阅读 01~07 前请先看 [08-agent-framework-pivot.md](./08-agent-framework-pivot.md)，其决策优先于 06、07 中冲突的部分。

## 文档索引

| 文档 | 内容 |
|------|------|
| [01-stack-and-decisions.md](./01-stack-and-decisions.md) | 技术栈确认：Python + LangChain/LangGraph；React 管理端；首期向量库 Qdrant |
| [02-architecture.md](./02-architecture.md) | 总体架构、分层模块、链路、原则与路线图 |
| [03-api-spec.md](./03-api-spec.md) | OpenAPI 接口清单草案 |
| [04-data-model.md](./04-data-model.md) | 核心表结构草案（MySQL + Qdrant） |
| [05-agent-governance.md](./05-agent-governance.md) | LangGraph 状态机与工具治理规范 |
| [06-admin-pages.md](./06-admin-pages.md) | React 管理端页面、路由、权限与交互规范 |
| [07-p0-build-steps.md](./07-p0-build-steps.md) | P0 平台建立顺序、验收标准与范围边界 |
| [08-agent-framework-pivot.md](./08-agent-framework-pivot.md) | **定位修订**：收敛为 Agent 开发框架，框架与业务层分层、改造顺序 |
| [../business-script-material/README.md](../business-script-material/README.md) | 剧本工坊业务文档索引（非框架交付物） |
| [../business-script-material/04-narrative-space-and-dual-mode.md](../business-script-material/04-narrative-space-and-dual-mode.md) | **目标产品形态**：四级模型 + 双模式 + 一致性规则 |
| [../business-script-material/05-dev-roadmap.md](../business-script-material/05-dev-roadmap.md) | **后续开发路线**：已锁定决策与分阶段任务 |

## 已锁定决策（摘要）

- **语言**：Python 3.11+ / FastAPI  
- **编排**：LangChain + LangGraph  
- **管理端**：React 18 + TypeScript + Vite；Ant Design 5 + Ant Design Pro Components  
- **P0 向量库**：Qdrant  
- **检索侧**：**外部** Xinference（本项目不部署，按地址 + `model_uid` 连接）；**Embedding = bge-m3**；**Rerank = bge-reranker-v2-m3**  
- **Chat**：业务**自有链接**（OpenAI 兼容 `base_url`，不锁定型号）  


- **业务库**：MySQL 8+；缓存/限流：Redis  
- **企业能力**：多租户、RBAC、审计、配额、可观测为一等公民  

## 阅读顺序建议

1. 定位修订（08）→ 2. 选型确认（01）→ 3. 总体架构（02）→ 4. Agent 治理（05）→ 5. 接口与表结构（03、04）  

06、07 记录的是修订前的平台形态，仅作历史参照。  
