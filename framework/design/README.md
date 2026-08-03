# 框架设计备忘（非上手主路径）

本目录为架构与选型决策记录。  
**实现与使用**请到代码旁文档：

| 类别 | 位置 |
|------|------|
| 框架核心 | [framework/agent_apps/README.md](../../framework/agent_apps/README.md) |
| API | [apps/api/README.md](../../apps/api/README.md) |
| 管理端 | [apps/admin/README.md](../../apps/admin/README.md) |
| 总入口 | [framework/README.md](../README.md) |

业务文档在 [docs/](../../docs/README.md)，不要与本目录混放。

## 索引

| 文档 | 内容 |
|------|------|
| [01-stack-and-decisions.md](./01-stack-and-decisions.md) | 技术栈 |
| [02-architecture.md](./02-architecture.md) | 总体架构 |
| [03-api-spec.md](./03-api-spec.md) | 接口清单草案 |
| [04-data-model.md](./04-data-model.md) | 表结构草案 |
| [05-agent-governance.md](./05-agent-governance.md) | Agent 治理规范 |
| [06-admin-pages.md](./06-admin-pages.md) | 管理端页面规范（历史） |
| [07-p0-build-steps.md](./07-p0-build-steps.md) | P0 步骤（历史） |
| [08-agent-framework-pivot.md](./08-agent-framework-pivot.md) | 定位修订：框架/业务分层 |
| [09-celery-rabbitmq-job-bus.md](./09-celery-rabbitmq-job-bus.md) | Celery + RabbitMQ 作业总线 |

阅读设计时优先 08 → 01 → 02 → 05 → 09。06/07 含修订前形态，仅作参照。
