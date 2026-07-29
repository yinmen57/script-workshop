# 剧本工坊业务文档

垂直业务：剧本解析 → 物料 → 分镜 → 成片视频。  
代码落在 `packages/business_script`、`apps-space/script-workshop`、`/api/v1/script-biz`。  
框架侧见 [../enterprise-langchain/08-agent-framework-pivot.md](../enterprise-langchain/08-agent-framework-pivot.md)。

## 文档索引

| 文档 | 内容 |
|------|------|
| [04-narrative-space-and-dual-mode.md](./04-narrative-space-and-dual-mode.md) | **目标产品形态**：四级模型、一致性规则、双模式、关键决策 |
| [05-dev-roadmap.md](./05-dev-roadmap.md) | **后续开发路线**：已落地现状、已锁定决策、分阶段任务与验收 |
| [06-material-library-adoption.md](./06-material-library-adoption.md) | **参考项目对照与吸收计划**：资源管理差距、定版与反悔机制、不吸收清单 |
| [02-sd-api-key-and-calls.md](./02-sd-api-key-and-calls.md) | 赏舞开放 API 鉴权与调用（第四段接入时用） |
| [03-sd-config.md](./03-sd-config.md) | `SD_*` 完整配置说明（第四段接入时用） |

## 已删除

| 原文档 | 原因 |
|--------|------|
| `01-domain-design.md` | 扁平 `Project → Shot`、分镜级视频、旧 B0/B1 分期；已被 04 + 05 取代 |

## 阅读顺序

1. 目标形态（04）→ 2. 开发路线（05）→ 3. 吸收计划（06）→ 4. 接入生图/生视频前再读 02、03
