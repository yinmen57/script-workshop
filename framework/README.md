# 框架文档入口

本目录与代码旁文档共同构成**框架侧文档**。  
业务文档只在 `docs/`（见 [docs/README.md](../docs/README.md)）。

## 文档分放位置

| 类别 | 位置 | 内容 |
|------|------|------|
| **框架（运行时/注册）** | [agent_apps/README.md](./agent_apps/README.md) | AgentSpec、注册表、runtime、tooling、如何扩展 App |
| **API** | [apps/api/README.md](../apps/api/README.md) | 框架 API / 业务 API 进程、路由、启动 |
| **管理端组件/页面** | [apps/admin/README.md](../apps/admin/README.md) | 框架页与业务页目录、路由、调试台用法 |
| **设计备忘** | [design/](./design/) | 选型与架构决策（历史/规范，非上手主路径） |

上手顺序：先读 **agent_apps → api → admin**；需要决策背景再翻 `design/08`、`design/09`。
