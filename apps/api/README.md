# API 文档（进程与路由）

同一镜像、两个 uvicorn 入口，分框架能力与业务 REST。

框架运行时说明见 [framework/agent_apps/README.md](../../framework/agent_apps/README.md)。  
管理端代理见 [apps/admin/README.md](../admin/README.md)。

## 进程

| 进程 | 模块 | Compose | 默认端口 | 启动 |
|------|------|---------|----------|------|
| 框架 API | `app.main:app` | `api` | `APP_PORT` 42867 | `python apps/api/run.py` |
| 业务 API | `app.biz_main:app` | `biz-api` | `BIZ_APP_PORT` 42868 | `python apps/api/run_biz.py` |

共用：`app/factory.py`（CORS / RequestId / 异常）、`deps.py`、同一 Dockerfile。

## 框架 API 路由（`main.py`）

| 前缀 | 说明 |
|------|------|
| `/api/v1/health` `/ready` | 健康检查 |
| `/api/v1/auth` | 登录 / 当前用户 |
| `/api/v1/apps` | 应用空间列表与详情（读注册表） |
| `/api/v1/chat` | 对话（POST 非流式 / WS 流式）、sessions、agent runs |
| `/api/v1/index` | 向量索引与检索 |
| `/api/v1/models` | AI Key CRUD / 测通 |

Lifespan：`ensure_chat_schema` + **`register_business_apps()`**（Agent 注册只在这里做）。

### Chat 请求要点

流式：`WS /api/v1/chat/ws?token=<access_token>`，首包：

```json
{
  "action": "chat",
  "slug": "script-workshop",
  "message": "...",
  "agent_id": "parser",
  "session_id": null,
  "selection": {}
}
```

推送事件：`reasoning` / `delta` / `step` / `usage` / `done` / `error`。取消：`{"action":"cancel"}`。

非流式：`POST /api/v1/chat/completions`（不要带 `stream: true`）。

- 不传 `agent_id`：全链路 coordinator + handoff  
- 传 specialist：`agent_id` 单 Agent  
- SSE：`step` / `delta` / `done` / `error`

## 业务 API 路由（`biz_main.py`）

| 前缀 | 说明 |
|------|------|
| `/api/v1/health` | 健康检查 |
| `/api/v1/script-biz/*` | 剧本领域 REST（`routers/business/script_biz.py`） |

Lifespan：**不**注册 Agent。鉴权与框架共用 JWT（`deps.AuthDep`）。

## 目录

```text
apps/api/app/
  main.py                 # 框架入口
  biz_main.py             # 业务入口
  factory.py
  deps.py
  routers/                # 框架路由
  routers/business/       # 仅 biz_main 挂载
```

## 本地与 Docker

```bash
docker compose up -d api          # 框架
docker compose up -d biz-api      # 业务
```

环境变量见根目录 `.env.example`（`APP_PORT` / `BIZ_APP_PORT`）。
