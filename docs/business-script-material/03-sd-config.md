# 赏舞（sd-2-c）完整配置说明

> 本文件说明本平台对接赏舞开放 API 时，本地 `.env` 中全部 `SD_*` 项的含义、合法值与业务映射。  
> 调用方式见 [02-sd-api-key-and-calls.md](./02-sd-api-key-and-calls.md)；上游接口见 `.ref/sd-2-c/docs/api-reference.md`。  
> **禁止**把真实 `SD_API_KEY` 写进文档或提交到 Git。

---

## 1. 完整配置模板

复制到仓库根目录 `.env`（勿提交）。`.env.example` 仅占位。

```text
# ---- sd-2-c 图像 / 视频 ----
SD_ENABLED=true
SD_BASE_URL=http://115.191.32.99:8080
SD_API_KEY=sk-你的密钥
SD_IMAGE_MODEL=doubao-seedream-5-0-260128
SD_VIDEO_MODEL=doubao-seedance-2-0-260128
SD_RESOLUTION=2K
SD_CHARACTER_SIZE=3:4
SD_THREE_VIEW_SIZE=16:9
SD_CHARACTER_VIEW_SIZE=21:9
SD_BACKGROUND_SIZE=16:9
SD_REQUEST_TIMEOUT_SECONDS=60
SD_POLL_INTERVAL_SECONDS=3
SD_POLL_TIMEOUT_SECONDS=300
SD_VIDEO_DURATION=-1
SD_VIDEO_RESOLUTION=480p
SD_VIDEO_RATIO=adaptive
SD_VIDEO_POLL_INTERVAL_SECONDS=5
SD_VIDEO_POLL_TIMEOUT_SECONDS=600
SD_PORTRAIT_POLL_INTERVAL_SECONDS=5
SD_PORTRAIT_POLL_TIMEOUT_SECONDS=300
SD_PORTRAIT_WAIT_ON_SUBMIT=true
```

---

## 2. 配置分组总览

| 分组 | 变量前缀 / 项 | 作用 |
|------|----------------|------|
| 开关与连接 | `SD_ENABLED`、`SD_BASE_URL`、`SD_API_KEY` | 是否启用、服务地址、鉴权 |
| 生图默认 | `SD_IMAGE_MODEL`、`SD_RESOLUTION`、各 `*_SIZE` | 模型、分辨率、各物料画幅 |
| HTTP / 生图轮询 | `SD_REQUEST_TIMEOUT_*`、`SD_POLL_*` | 单次请求超时、生图任务轮询 |
| 生视频默认 | `SD_VIDEO_*` | 时长、分辨率、比例、视频任务轮询 |
| 虚拟人像 | `SD_PORTRAIT_*` | 人像审核轮询与提交时是否等待 |

所有开放 API 请求 Header：

```http
Authorization: Bearer {SD_API_KEY}
```

---

## 3. 逐项说明

### 3.1 开关与连接

| 变量 | 类型 | 推荐值 | 说明 |
|------|------|--------|------|
| `SD_ENABLED` | bool | `true` | 为 `false` 时本平台不调用赏舞（生图/生视频/人像相关能力关闭） |
| `SD_BASE_URL` | string | `http://115.191.32.99:8080` | 赏舞 API 根地址，**不要**末尾斜杠 |
| `SD_API_KEY` | string | `sk-...` | 开放 API Key；后台「设置 → API 密钥」创建 |

### 3.2 生图：模型与分辨率

| 变量 | 类型 | 推荐值 | 说明 |
|------|------|--------|------|
| `SD_IMAGE_MODEL` | string | `doubao-seedream-5-0-260128` | 传给 `POST /api/generation/image-tasks` 的 `image_model` |
| `SD_RESOLUTION` | string | `2K` | 生图分辨率；请求前建议规范为小写 `2k` / `3k` |

| `image_model` | 支持分辨率 |
|---------------|------------|
| `doubao-seedream-4-5-251128` | `1k` / `2k` / `4k` |
| `doubao-seedream-5-0-260128` | `2k` / `3k` |

当前默认模型只支持 **2k / 3k**；填 `1k` 或 `4k` 会被上游拒绝。

### 3.3 生图：各业务画幅（`size`）

对应生图接口字段 `size`（画面比例）。按物料类型选用：

| 变量 | 推荐值 | 业务用途 | 映射接口字段 |
|------|--------|----------|--------------|
| `SD_CHARACTER_SIZE` | `3:4` | 角色定妆 / 半身人设图 | `size` |
| `SD_THREE_VIEW_SIZE` | `16:9` | 角色三视图拼图 | `size` |
| `SD_CHARACTER_VIEW_SIZE` | `21:9` | 超宽角色展示 / 横版人设条 | `size` |
| `SD_BACKGROUND_SIZE` | `16:9` | 场景 / 背景图 | `size` |

常见合法比例（与上游一致）：`1:1`、`16:9`、`9:16`、`4:3`、`3:4`、`21:9` 等。

### 3.4 HTTP 与生图任务轮询

| 变量 | 类型 | 推荐值 | 说明 |
|------|------|--------|------|
| `SD_REQUEST_TIMEOUT_SECONDS` | int | `60` | 单次 HTTP 请求超时（提交任务、查状态、上传等） |
| `SD_POLL_INTERVAL_SECONDS` | int | `3` | 生图任务轮询间隔；上游建议 3–5 秒 |
| `SD_POLL_TIMEOUT_SECONDS` | int | `300` | 生图任务最长等待（秒）；超时视为失败 |

轮询接口：`GET /api/generation/tasks/{task_id}`。  
图片任务通常约 10–30 秒；`300` 秒足够覆盖排队高峰。

### 3.5 生视频

| 变量 | 类型 | 推荐值 | 说明 |
|------|------|--------|------|
| `SD_VIDEO_MODEL` | string | `doubao-seedance-2-0-260128` | 本平台记录的默认视频模型名（业务侧标识；赏舞视频任务以开放 API 字段为准） |
| `SD_VIDEO_DURATION` | int | `-1` | 传给视频任务的 `duration`。`-1` = 智能时长；正整数为固定秒数（如 `5`） |
| `SD_VIDEO_RESOLUTION` | string | `480p` | 视频分辨率：`480p` / `720p` / `1080p`。越高越贵，`1080p` 积分约为 `720p` 的 2.5 倍 |
| `SD_VIDEO_RATIO` | string | `adaptive` | 画面比例：`16:9`、`9:16`、`1:1`、`4:3`、`3:4`、`21:9`、`adaptive` |
| `SD_VIDEO_POLL_INTERVAL_SECONDS` | int | `5` | 视频任务轮询间隔 |
| `SD_VIDEO_POLL_TIMEOUT_SECONDS` | int | `600` | 视频任务最长等待；视频通常 2–5 分钟，高峰可更长 |

提交接口：`POST /api/generation/tasks`。

`adaptive` 比例：上游按该分辨率下最大像素档做预估计费（详见 `.ref/sd-2-c/docs/video-token-pricing.md`）。

### 3.6 虚拟人像（审核轮询）

人像流程：创建分组 → 上传素材 → **等待审核** → 视频里用 `asset://{upstream_asset_id}` 引用。

| 变量 | 类型 | 推荐值 | 说明 |
|------|------|--------|------|
| `SD_PORTRAIT_POLL_INTERVAL_SECONDS` | int | `5` | 查询人像素材审核状态的间隔 |
| `SD_PORTRAIT_POLL_TIMEOUT_SECONDS` | int | `300` | 人像审核最长等待；超时后由业务决定是否继续后台查或标失败 |
| `SD_PORTRAIT_WAIT_ON_SUBMIT` | bool | `true` | `true`：上传/提交后人像链路同步等到审核结束（或超时）再返回；`false`：提交后立即返回，由后续任务/接口再查状态 |

相关接口：

- `POST /api/model-library/groups`
- `POST /api/model-library/groups/{group_id}/assets`
- `GET /api/model-library/groups/{group_id}/assets`

所需 Scope：`model:write`、`model:read`。

---

## 4. 与赏舞接口字段对照

| 本平台配置 | 赏舞请求字段 / 行为 |
|------------|---------------------|
| `SD_BASE_URL` + 路径 | HTTP 根地址 |
| `SD_API_KEY` | `Authorization: Bearer ...` |
| `SD_IMAGE_MODEL` | `image_model` |
| `SD_RESOLUTION` | `resolution`（生图，建议小写） |
| `SD_CHARACTER_SIZE` 等 | `size`（按物料类型选用） |
| `SD_VIDEO_DURATION` | `duration` |
| `SD_VIDEO_RESOLUTION` | `resolution`（生视频） |
| `SD_VIDEO_RATIO` | `ratio` |
| `SD_POLL_*` / `SD_VIDEO_POLL_*` | 客户端轮询 `GET .../tasks/{id}` |
| `SD_PORTRAIT_*` | 客户端轮询人像素材审核状态 |

---

## 5. 与剧本业务阶段的对应

| 业务阶段 | 使用的配置 | 接口 |
|----------|------------|------|
| C 角色定妆生图 | `SD_IMAGE_MODEL`、`SD_RESOLUTION`、`SD_CHARACTER_SIZE`、`SD_POLL_*` | `POST /api/generation/image-tasks` |
| C 三视图 / 宽画幅人设 | 同上 + `SD_THREE_VIEW_SIZE` / `SD_CHARACTER_VIEW_SIZE` | 同上 |
| C 背景生图 | 同上 + `SD_BACKGROUND_SIZE` | 同上 |
| 虚拟人像入库 | `SD_PORTRAIT_*` | `/api/model-library/*` |
| E 生视频 | `SD_VIDEO_*` | `POST /api/generation/tasks` |

剧本解析 / 物料提示词 / 视频提示词仍走本平台 Chat，**不使用** `SD_*`。

---

## 6. 推荐默认与调优建议

| 场景 | 建议 |
|------|------|
| 本地联调 / 控成本 | `SD_VIDEO_RESOLUTION=480p`，`SD_RESOLUTION=2K` |
| 成片质量优先 | 视频改 `720p` 或 `1080p`（注意积分） |
| 固定片长 | `SD_VIDEO_DURATION=5`（或业务需要的秒数），不要用 `-1` |
| 生图慢 / 排队 | 适当增大 `SD_POLL_TIMEOUT_SECONDS`，间隔保持 3–5 秒 |
| 人像审核久 | 增大 `SD_PORTRAIT_POLL_TIMEOUT_SECONDS`；或 `SD_PORTRAIT_WAIT_ON_SUBMIT=false` 改为异步查 |

---

## 7. Key 权限（Scopes）清单

| Scope | 何时需要 |
|-------|----------|
| `generation:write` | 提交生图 / 生视频 |
| `generation:read` | 轮询任务状态 |
| `media:write` / `media:read` | 上传、查询参考素材 |
| `model:write` / `model:read` | 虚拟人像分组与审核轮询 |
| `account:read` | 余额自检 |

---

## 8. 自检清单

- [ ] `.env` 已填完整 `SD_*`，且未提交真实 Key
- [ ] `SD_ENABLED=true`，`GET {SD_BASE_URL}/api/account/balance` 返回 200
- [ ] 生图：定妆 `3:4` / 背景 `16:9` 能到 `succeeded` 并拿到 `result_image_urls`
- [ ] 生视频：`duration` / `resolution` / `ratio` 与预期一致，能拿到 `stored_video_url`
- [ ] 人像：上传后审核能到可用状态；`SD_PORTRAIT_WAIT_ON_SUBMIT` 行为符合产品预期
- [ ] Key 具备上表所需 scopes
