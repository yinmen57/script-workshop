# 赏舞（sd-2-c）API Key 用法与调用说明

> 本项目通过 **赏舞开放 API**（sd-2-c 已部署服务）做生图 / 生视频，不直连火山方舟。  
> 官方对照：`.ref/sd-2-c/docs/api-reference.md`  
> **禁止**把真实 Key 写进文档或提交到 Git。

---

## 1. 项目凭证

| `.env` 变量 | 说明 |
|-------------|------|
| `SD_BASE_URL` | 赏舞 API 根地址，如 `http://115.191.32.99:8080` |
| `SD_API_KEY` | 开放 API Key（`sk-` 前缀） |

所有请求 Header：

```http
Authorization: Bearer {SD_API_KEY}
```

Key 在赏舞后台「设置 → API 密钥」创建；权限由管理员配置 scopes（见下）。

---

## 2. 权限范围（Scopes）

| Scope | 能力 |
|-------|------|
| `generation:write` | 提交视频/图片任务、重命名素材 |
| `generation:read` | 查询任务状态与结果 |
| `media:write` | 上传/删除媒体素材 |
| `media:read` | 素材列表、搜索 |
| `model:write` | 虚拟人像分组与上传 |
| `model:read` | 查看人像分组与素材状态 |
| `account:read` | 积分余额与流水 |

---

## 3. `.env` 配置

真实值只写仓库根目录 `.env`（gitignore）。`.env.example` 仅占位。  
**完整项说明（画幅、轮询、视频、人像等）见 [03-sd-config.md](./03-sd-config.md)。**

```text
# 赏舞（sd-2-c）开放 API：生图 / 生视频 / 素材
SD_ENABLED=true
SD_BASE_URL=http://115.191.32.99:8080
SD_API_KEY=sk-你的密钥
SD_IMAGE_MODEL=doubao-seedream-5-0-260128
SD_VIDEO_MODEL=doubao-seedance-2-0-260128
# 其余 SD_RESOLUTION / *_SIZE / 轮询 / 视频 / 人像 等见 03-sd-config.md
```

说明：

- 生图 / 生视频 / 上传素材：**只用** `SD_*`，不再配置方舟 `ARK_*`。
- 赏舞开放 API **不提供** Chat/剧本解析接口；剧本解析仍走本平台自己的 Chat 模型配置（与 `SD_*` 无关）。若后续赏舞开放脚本接口，再另补文档。

---

## 4. 调用示例

### 4.1 查余额（连通性自检）

```http
GET {SD_BASE_URL}/api/account/balance
Authorization: Bearer {SD_API_KEY}
```

### 4.2 生图

```http
POST {SD_BASE_URL}/api/generation/image-tasks
```

```json
{
  "prompt": "水墨山水画，远山近水，云雾缭绕",
  "image_model": "doubao-seedream-5-0-260128",
  "size": "1:1",
  "resolution": "2k",
  "n": 1
}
```

| `image_model` | 支持分辨率 |
|---------------|------------|
| `doubao-seedream-4-5-251128` | 1k / 2k / 4k |
| `doubao-seedream-5-0-260128` | 2k / 3k |

响应含任务 `id`，状态一般为 `processing`。

### 4.3 生视频

```http
POST {SD_BASE_URL}/api/generation/tasks
```

```json
{
  "content": [
    {"type": "text", "text": "一只橘猫在阳光下伸懒腰"},
    {
      "type": "image_url",
      "image_url": {"url": "https://..."},
      "role": "reference_image"
    }
  ],
  "duration": 5,
  "resolution": "720p",
  "ratio": "16:9"
}
```

参考图/视频 URL 可先走上传接口拿到。

### 4.4 上传素材

```http
POST {SD_BASE_URL}/api/generation/upload
Content-Type: multipart/form-data
```

表单字段：`file`（图/视频/音频）。响应里的 `url` 可填入视频 `content`。

### 4.5 查询任务

```http
GET {SD_BASE_URL}/api/generation/tasks/{task_id}
```

| status | 含义 |
|--------|------|
| `queued` | 排队 |
| `processing` | 生成中 |
| `succeeded` | 成功（读 `stored_video_url` 或 `result_image_urls`） |
| `failed` | 失败（看 `error_message`） |

建议 3–5 秒轮询；图约 10–30 秒，视频约 2–5 分钟。

---

## 5. 与剧本业务阶段的对应

| 业务阶段 | 走哪边 |
|----------|--------|
| A 剧本解析 / B 物料提示词 / D 视频提示词 | 本平台 Chat（非 `SD_*`） |
| C 物料生图 | `POST /api/generation/image-tasks` |
| E 生视频 | `POST /api/generation/tasks` |
| 参考图上传 | `POST /api/generation/upload` |

```text
Bearer SD_API_KEY
        ├── GET  /api/account/balance
        ├── POST /api/generation/image-tasks
        ├── POST /api/generation/tasks
        ├── GET  /api/generation/tasks/{id}
        └── POST /api/generation/upload
```

---

## 6. 自检清单

- [ ] `SD_BASE_URL`、`SD_API_KEY` 已写入本地 `.env`
- [ ] `GET /api/account/balance` 返回 200
- [ ] Key 具备 `generation:write` / `generation:read`（及需要的 `media:*`）
- [ ] 生图任务能到 `succeeded` 并拿到 `result_image_urls`
- [ ] 生视频任务能到 `succeeded` 并拿到 `stored_video_url`
- [ ] 真实 Key 未进 Git / 未写进本文档正文
