# 剧本工坊业务文档

垂直业务：剧本解析 → 物料 → 分镜 → 成片视频。  
代码落在 `business/script`、`apps-space/script-workshop`、`/api/v1/script-biz`。  
框架侧实现见 [../../framework/agent_apps/README.md](../../framework/agent_apps/README.md)；设计备忘见 [../../framework/design/08-agent-framework-pivot.md](../../framework/design/08-agent-framework-pivot.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [04-narrative-space-and-dual-mode.md](./04-narrative-space-and-dual-mode.md) | **目标产品形态**：五级模型、工作台/知识库分离、ConsistencyPack、双模式、关键决策 |
| [05-dev-roadmap.md](./05-dev-roadmap.md) | **后续开发路线**：已落地现状、已锁定决策、分阶段任务与验收 |
| [06-material-library-adoption.md](./06-material-library-adoption.md) | **参考项目对照与吸收计划**：资源管理差距、定版与反悔机制、不吸收清单 |
| [07-agent-tool-selection-risks.md](./07-agent-tool-selection-risks.md) | **Agent 工具选择风险**：router 决策 + 服务端校验的问题清单、约束与验收 |
| [02-sd-api-key-and-calls.md](./02-sd-api-key-and-calls.md) | 赏舞开放 API 鉴权与调用 |
| [03-sd-config.md](./03-sd-config.md) | 赏舞历史 `SD_*` 说明（密钥已迁 AI Key 页，仅作对照） |
| [08-ark-image-video-integration.md](./08-ark-image-video-integration.md) | **方舟 Seedream/Seedance 对接**：官方文档索引、接口子集、与赏舞分流、落地映射 |
| [09-generation-async-reliability.md](./09-generation-async-reliability.md) | **长耗时生成可靠性**（建在 Celery+RabbitMQ 上）：槽位、短轮询、claim、快照、对账；总线通则见 [../../framework/design/09-celery-rabbitmq-job-bus.md](../../framework/design/09-celery-rabbitmq-job-bus.md) |

## 已删除

| 原文档 | 原因 |
|--------|------|
| `01-domain-design.md` | 扁平 `Project → Shot`、分镜级视频、旧 B0/B1 分期；已被 04 + 05 取代 |

## 阅读顺序

1. 目标形态（04）→ 2. 开发路线（05）→ 3. 吸收计划（06）→ 4. 接入生图/生视频前再读 02、03
