# 规划文档（进行中）

> **约定**：后续新的改造/演进规划统一追加到本文，按条目归档；落地完成后把状态改为「已完成」并链到对应设计/实现文档，不另起零散规划文件。  
> **文档分区**：业务文档在 `docs/`；框架实现见 `framework/agent_apps/README.md`、API 见 `apps/api/README.md`、管理端见 `apps/admin/README.md`；设计备忘见 `framework/design/`（总入口 [framework/README.md](../framework/README.md)）。

## 索引

| ID | 标题 | 状态 | 更新日期 |
|----|------|------|----------|
| P-001 | Agent 注册与可视化单测 | 已完成 | 2026-08-03 |
| P-002 | 框架/业务依赖与目录分离 | 已完成（同仓逻辑分离） | 2026-08-03 |
| P-003 | 框架 API / 业务 API 进程拆分 | 已完成 | 2026-08-03 |

---

## P-001：Agent 注册与可视化单测

**状态**：已完成（阶段 A）  
**范围**：框架层（`framework/agent_apps` + Admin Playground）  
**目标**：代码注册的 Agent 可在可视化界面单独测试，无需每次走完整 coordinator 链路。

### 已落地

| 层 | 改动 |
|----|------|
| Runtime | `iter_agent_run(..., agent_id=)`：specialist 单测不挂 handoff；未传/coordinator 为全链路 |
| chat_service | `prepare_completion` 校验 agent、换 system prompt / max_steps；切换 Agent 前端清 session |
| API | `POST /chat/completions` 可选 `agent_id` |
| Admin | 配置页「单独调试」；Playground Select + `?agent_id=`；`chat.ts` 透传 |

### 用法

1. `/apps/script-workshop` → 某个 Agent →「单独调试」
2. 或打开 `/apps/script-workshop/playground?agent_id=parser`
3. 顶部 Select 可改「全链路」或其它 Agent（切换会清空当前会话）

```json
{
  "slug": "script-workshop",
  "agent_id": "parser",
  "message": "...",
  "stream": true
}
```

### 阶段 B（可选，未做）

- Tool 直测：`POST /apps/{slug}/tools/{tool_id}/invoke`

### 验收（阶段 A）

- [x] 配置页每个 Agent 可一键进入调试台且带 `agent_id`
- [x] Playground 可选「全链路」或指定 agent
- [x] 指定 specialist 时仅加载该 agent 工具，无 `delegate_to_*`
- [x] SSE step 轨迹中 `agent_id` 正确；历史 run 可回放
- [x] 未传 `agent_id` 的业务工作台 / 现网 chat 不受影响

---

## P-002：框架/业务依赖与目录分离

**状态**：已完成（同仓物理分目录；独立发布另开规划）  
**范围**：`framework/*`、`business/*`、Admin、Celery 入口  
**目标**：框架包可被其他项目复用；业务 App / 媒体 / 作业 / 页面以插件方式挂接。

### 已落地

| 项 | 说明 |
|----|------|
| Agent 应用 | `script_workshop` → `business/apps/` |
| 框架 AgentSpec / 注册 | `framework/agent_apps` + `register_apps`；业务 `bootstrap` 注入 |
| 工具桥接 | `tool_catalog` + `entrypoint` |
| 媒体 Adapter | → `business/adapters/` |
| Celery | 框架壳 `framework/infra/celery_app`；业务 `business/jobs` |
| 投递壳 | `framework/infra/jobs/enqueue.py` |
| Admin | 框架页 `pages/framework/`；业务页 `pages/business/`；菜单/路由 `src/business/` |
| 目录 | 取消混放的 `packages/`；框架与业务各占根目录 |

目标树：

```text
framework/                 # 框架（可复用）
  agent_apps/ adapters/ core/ domain/ governance/ infra/
  design/                  # 设计备忘
business/                  # 业务（本产品）
  apps/ script/ adapters/ jobs/

apps/admin/src/
  pages/framework/     # 应用空间、调试台、AI Key、登录
  pages/business/      # 剧本工作台、画布
  business/            # 业务菜单与路由片段
  api/business/        # scriptBiz
```

依赖方向：

```text
business.* → framework.*
framework.* ✗→ business.*
Admin：framework 页可引用 business 事件通道（调试台推画布），业务不反向依赖框架页
```

### 后续（另开规划）

- [ ] 物理拆仓库（框架独立发布）
- [ ] Admin 分构建（可选独立业务 SPA）

### 验收

- [x] `framework/agent_apps` 无业务硬编码 import
- [x] 启动通过 `register_business_apps()` 注入应用
- [x] 媒体 adapter / 业务 Celery 任务在业务包
- [x] Celery Worker/Beat 入口为 `business.jobs.celery_app`
- [x] Admin 框架/业务目录分离，业务菜单与路由可拔插
- [x] 根目录 `framework/` 与 `business/` 分开放，不再使用混放的 `packages/`

### 明确不做

- 不回退 YAML apps-space 扫描
- 不为兼容保留旧路径

---

## P-003：框架 API / 业务 API 进程拆分

**状态**：已完成  
**范围**：`apps/api`、docker-compose、Admin Vite 代理  
**目标**：框架能力与剧本业务 REST 分进程部署，互不挂载对方路由。

### 已落地

| 进程 | 入口 | 路由 | 默认端口 |
|------|------|------|----------|
| 框架 API | `app.main:app` | health / auth / models / index / apps / chat | `APP_PORT` 42867 |
| 业务 API | `app.biz_main:app` | health + `/script-biz` | `BIZ_APP_PORT` 42868 |

- 共用：`factory.py`（CORS / RequestId / 异常处理）、`deps`、同一 Docker 镜像
- 业务路由：`apps/api/app/routers/business/script_biz.py`（仅 biz_main 挂载）
- 框架 lifespan：仍 `register_business_apps()`（Agent 插件供调试台）
- 业务 lifespan：不注册 Agent，只起 REST
- Admin 开发代理：`/api/v1/script-biz` → 业务 API，其余 `/api` → 框架 API
- 本地：`python apps/api/run.py` / `python apps/api/run_biz.py`

### 验收

- [x] 框架进程 OpenAPI 无 `/script-biz`
- [x] 业务进程仅有 health + script-biz
- [x] compose 提供 `api` + `biz-api` 两服务
- [x] Admin 开发态可同时访问两进程（Vite 分流）

### 明确不做

- 不为兼容保留「单进程挂全部路由」的合并入口
- 本阶段不拆物理仓库 / 不拆 Admin 双 SPA

---

## 追加规划模板

复制下方模板追加新条目，并更新文首索引表。

```markdown
## P-00X：标题

**状态**：规划中 | 进行中 | 已完成 | 取消  
**范围**：  
**目标**：  

### 现状
### 方案
### 验收
### 明确不做
```
