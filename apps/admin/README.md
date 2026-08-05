# 管理端文档（页面与组件分区）

React + Ant Design。框架调试面与剧本业务面分目录，路由可拔插。

框架运行时：[framework/agent_apps/README.md](../../framework/agent_apps/README.md)  
API 代理目标：[apps/api/README.md](../api/README.md)

## 目录分区

```text
apps/admin/src/
  pages/framework/     # 框架页：登录、应用空间、调试台
  pages/business/      # 业务页：剧本工作台、叙事画布、AI Key
  business/            # 业务菜单项 + 路由片段（给 App/Layout 挂载）
  api/                 # 框架 API 客户端（chat / resources / models）
  api/business/        # 业务 API 客户端（scriptBiz → /script-biz）
  layouts/             # AdminLayout（拼装框架菜单 + business 菜单）
```

## 框架页

| 页面 | 路由 | 作用 |
|------|------|------|
| LoginPage | `/login` | JWT 登录 |
| AppsPage | `/apps` | 已注册应用列表 |
| AgentWorkspacePage | `/apps/:slug` | Agent/工具/prompt；「单独调试」 |
| PlaygroundPage | `/apps/:slug/playground` | SSE 调试；`?agent_id=` 单 Agent |

单 Agent 调试：配置页按钮或  
`/apps/script-workshop/playground?agent_id=parser`。  
切换 Select 会清空会话。

## 业务页（插件）

| 区域 | 路由 |
|------|------|
| AI Key 配置 | `/models`（按类目 Tab：语言 / 声音 / 生图 / 生视频 / 检索） |
| 剧本工作台 | `/script-workspace` |
| 片段画布 | `/script-biz/canvas/:segmentId`（≤15s 视频片段） |

由 `src/business/routes.tsx` / `menu.tsx` 导出，`App.tsx` / `AdminLayout` 挂载。去掉业务时删挂载即可，框架页可独立使用。

## 开发代理

`vite.config.ts`：

- `/api/v1/script-biz` → `VITE_BIZ_API_PROXY_TARGET`（默认 42868）  
- `/api` → `VITE_API_PROXY_TARGET`（默认 42867）  

见 `.env.example`。前端统一 `VITE_API_BASE_URL=/api/v1`，靠代理分流。

## 启动

```bash
cd apps/admin
npm install
npm run dev
```

需框架 API 已启动（应用注册与 chat）；剧本工作台还需业务 API。
