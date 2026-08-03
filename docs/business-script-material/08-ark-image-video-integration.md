# 火山方舟生图 / 生视频对接说明

> 本平台生图、生视频支持两条上游：**赏舞**（现有）与 **火山方舟**（Seedream / Seedance）。  
> 凭证与模型名在管理端「AI Key 配置」登记（`model_type=image|video`，`provider=shangwu|volcengine_ark`），不写 `.env`。  
> **禁止**把真实 API Key 写进文档或提交到 Git。

官方入口以火山文档站为准（控制台镜像路径仅便于收藏）：

| 能力 | 官方文档 | 控制台镜像 |
|------|----------|------------|
| 图片生成 API | [82379/1541523](https://www.volcengine.com/docs/82379/1541523?lang=zh) | [ark …/1541523](https://ark.volcengine.com/region:cn-beijing/docs/82379/1541523?lang=zh) |
| 图片生成流式事件 | [82379/1824137](https://www.volcengine.com/docs/82379/1824137?lang=zh) | [ark …/1824137](https://ark.volcengine.com/region:cn-beijing/docs/82379/1824137?lang=zh) |
| 创建视频任务 | [82379/1520757](https://www.volcengine.com/docs/82379/1520757?lang=zh) | [ark …/1520757](https://ark.volcengine.com/region:cn-beijing/docs/82379/1520757?lang=zh) |
| 查询视频任务 | [82379/1521309](https://www.volcengine.com/docs/82379/1521309?lang=zh) | [ark …/1521309](https://ark.volcengine.com/region:cn-beijing/docs/82379/1521309?lang=zh) |
| 查询视频任务列表 | [82379/1521675](https://www.volcengine.com/docs/82379/1521675?lang=zh) | [ark …/1521675](https://ark.volcengine.com/region:cn-beijing/docs/82379/1521675?lang=zh) |
| 取消或删除视频任务 | [82379/1521720](https://www.volcengine.com/docs/82379/1521720?lang=zh) | [ark …/1521720](https://ark.volcengine.com/region:cn-beijing/docs/82379/1521720?lang=zh) |

赏舞对照：[02-sd-api-key-and-calls.md](./02-sd-api-key-and-calls.md)。

---

## 1. 能力矩阵与选型

| 能力 | `model_type` | `provider` | 上游产品 | 协议形态 |
|------|--------------|------------|----------|----------|
| 生图 | `image` | `volcengine_ark` | Seedream | 同步 HTTP（可选 SSE 流式） |
| 生图 | `image` | `shangwu` | 赏舞生图 | 异步：提交 + 轮询 |
| 生视频 | `video` | `volcengine_ark` | Seedance | 异步：创建任务 + 轮询 |
| 生视频 | `video` | `shangwu` | 赏舞生视频 | 异步：提交 + 轮询 |

自由选择：同类型可登记多条配置，**仅一条 `is_default=true` 且 `enabled` 生效**。  
运行时 `render_service` 读默认配置，再按 `provider` 分流适配器。

Chat（剧本解析等）仍走 `model_type=chat`，与生图/生视频配置独立；可共用同一把方舟 Key，但是三条记录。

---

## 2. 公共约定（方舟）

### 2.1 Base URL 与鉴权

```text
Base URL（推荐写入 AI Key 配置）:
https://ark.cn-beijing.volces.com/api/v3
```

```http
Authorization: Bearer {ARK_API_KEY}
Content-Type: application/json
```

| AI Key 字段 | 含义 |
|-------------|------|
| `base_url` | 上表根路径（含 `/api/v3`） |
| `api_key` | 方舟 API Key |
| `model_name` | 推理接入点 / 模型 ID（控制台创建后的 Endpoint 或公开模型 ID） |
| `provider` | 固定 `volcengine_ark` |

### 2.2 产物落库

方舟返回的图片/视频 URL **有时效**（视频常见约 24 小时）。  
本平台流程：拿到 URL → 下载 → 写入自有 OSS → 业务表只存 OSS 地址。与赏舞一致。

---

## 3. 生图（Seedream）

### 3.1 文档职责

| 文档 | 本平台用法 |
|------|------------|
| [1541523 图片生成 API](https://www.volcengine.com/docs/82379/1541523?lang=zh) | **主对接**：请求/响应字段 |
| [1824137 流式响应事件](https://www.volcengine.com/docs/82379/1824137?lang=zh) | 可选；P0 **不接流式**（`stream=false`），一次拿结果 URL |

### 3.2 接口

```http
POST {base_url}/images/generations
```

完整示例：

```http
POST https://ark.cn-beijing.volces.com/api/v3/images/generations
Authorization: Bearer {ARK_API_KEY}
```

### 3.3 请求体（P0 子集）

```json
{
  "model": "doubao-seedream-5-0-260128",
  "prompt": "水墨山水画，远山近水，云雾缭绕",
  "size": "2K",
  "response_format": "url",
  "watermark": false,
  "stream": false,
  "sequential_image_generation": "disabled"
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `model` | 是 | 取自 AI Key 的 `model_name` |
| `prompt` | 是 | 物料提示词正文 |
| `size` | 否 | `2K` / `3K` / `4K` 或 `宽x高`；P0 默认 `2K` |
| `image` | 否 | 参考图 URL 或数组（图生图）；P0 物料生图可先不传 |
| `response_format` | 否 | P0 固定 `url` |
| `stream` | 否 | P0 固定 `false` |
| `watermark` | 否 | P0 建议 `false` |
| `sequential_image_generation` | 否 | P0 建议 `disabled`（单图） |

字段以官方 [1541523](https://www.volcengine.com/docs/82379/1541523?lang=zh) 为准；模型版本差异（参考图数量、size 档位）以控制台模型说明为准。

### 3.4 响应（P0）

```json
{
  "model": "doubao-seedream-5-0-260128",
  "created": 1757321139,
  "data": [
    { "url": "https://...", "size": "3104x1312" }
  ],
  "usage": {
    "generated_images": 1,
    "output_tokens": 0,
    "total_tokens": 0
  }
}
```

本平台取 `data[0].url` → 下载 → OSS → `material_image`。

### 3.5 与赏舞生图对比

| 项 | 方舟 Seedream | 赏舞 |
|----|---------------|------|
| 提交 | `POST /images/generations` | `POST /api/generation/image-tasks` |
| 等待 | 同步返回 URL（P0） | `task_id` + 轮询 |
| 模型字段 | `model` | `image_model` |
| 适配器（规划） | `ark_image_client` | `sd_client`（kind=image） |

---

## 4. 生视频（Seedance）

### 4.1 文档职责

| 文档 | 本平台用法 |
|------|------------|
| [1520757 创建视频生成任务](https://www.volcengine.com/docs/82379/1520757?lang=zh) | **必接**：提交 |
| [1521309 查询视频生成任务](https://www.volcengine.com/docs/82379/1521309?lang=zh) | **必接**：轮询到终态 |
| [1521675 查询任务列表](https://www.volcengine.com/docs/82379/1521675?lang=zh) | 运维/排查；P0 业务链路可不接 |
| [1521720 取消或删除任务](https://www.volcengine.com/docs/82379/1521720?lang=zh) | 取消作业时可选；P0 可不接 |

### 4.2 创建任务

```http
POST {base_url}/contents/generations/tasks
```

```json
{
  "model": "doubao-seedance-2-0-260128",
  "content": [
    {
      "type": "text",
      "text": "女孩抱着狐狸，温柔看向镜头，镜头缓缓拉出"
    },
    {
      "type": "image_url",
      "image_url": { "url": "https://your-oss/.../ref.png" },
      "role": "reference_image"
    }
  ],
  "resolution": "480p",
  "ratio": "adaptive",
  "duration": 5,
  "watermark": false
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `model` | 是 | AI Key 的 `model_name` |
| `content` | 是 | 多模态输入数组：`text` / `image_url` /（高阶）`video_url`、`audio_url` |
| `duration` | 否 | 秒；与业务 `video_prompt.duration_sec` 对齐，封顶按产品规则（现有 15） |
| `resolution` | 否 | 如 `480p` / `720p` / `1080p` |
| `ratio` | 否 | 如 `16:9`、`9:16`、`adaptive` |
| `watermark` | 否 | P0 建议 `false` |
| `callback_url` | 否 | P0 不接回调，只用轮询 |

`content` 与现有赏舞视频组装方式接近：文案 + 可选参考图 URL（已落 OSS 的公开地址）。

创建成功响应至少含任务 `id`（后续轮询用）。

### 4.3 查询任务（轮询）

```http
GET {base_url}/contents/generations/tasks/{task_id}
```

关注字段（名称以 [1521309](https://www.volcengine.com/docs/82379/1521309?lang=zh) 为准）：

| 字段 | 说明 |
|------|------|
| `id` | 任务 ID |
| `status` | 如 `queued` / `running` / `succeeded` / `failed`（以官方枚举为准） |
| 结果 URL | 成功时的视频地址（常见在 `content.video_url` 或文档标明的等价路径） |
| `error` | 失败信息 |

P0 轮询建议：间隔 5～15 秒；超时单独配置（视频通常数分钟）。  
仅 `succeeded` 才下载转存。

### 4.4 列表 / 取消（非 P0）

| 接口 | 文档 | P0 |
|------|------|----|
| 任务列表 | [1521675](https://www.volcengine.com/docs/82379/1521675?lang=zh) | 不接 |
| 取消或删除 | [1521720](https://www.volcengine.com/docs/82379/1521720?lang=zh) | 不接；后续可对接作业取消 |

### 4.5 与赏舞生视频对比

| 项 | 方舟 Seedance | 赏舞 |
|----|---------------|------|
| 提交 | `POST /contents/generations/tasks` | `POST /api/generation/tasks` |
| 查询 | `GET /contents/generations/tasks/{id}` | `GET /api/generation/tasks/{id}` |
| 模型字段 | `model` | 业务侧记录 / 网关侧模型 |
| 适配器（规划） | `ark_video_client` | `sd_client`（kind=video） |

---

## 5. 本平台落地映射（实现前约定）

### 5.1 AI Key 配置示例

**方舟生图**

| 字段 | 示例 |
|------|------|
| 类型 | `image` |
| Provider | `volcengine_ark` |
| 模型名 | `doubao-seedream-5-0-260128`（以控制台为准） |
| Base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| API Key | 方舟 Key |
| 默认 | 是（若选用方舟生图） |

**方舟生视频**

| 字段 | 示例 |
|------|------|
| 类型 | `video` |
| Provider | `volcengine_ark` |
| 模型名 | `doubao-seedance-2-0-260128`（以控制台为准） |
| Base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| API Key | 方舟 Key |
| 默认 | 是（若选用方舟生视频） |

赏舞同理：`provider=shangwu`，Base URL 为赏舞根地址。

### 5.2 代码落点（规划）

| 模块 | 职责 |
|------|------|
| `business/adapters/ark_image_client.py` | Seedream：`/images/generations` |
| `business/adapters/ark_video_client.py` | Seedance：创建 + 查询轮询 |
| `business/adapters/sd_client.py` | 赏舞（已有） |
| `business/script/render_service.py` | 按 `provider` 分流 |
| `framework/governance/model_service.py` | `image`/`video` + provider 校验与解密 |
| `apps/admin` ModelsPage | Provider 可选「赏舞 / 火山方舟」 |

业务入口不变：

- 生图：`render_material_image` → job → `render_service.render_material_image`
- 生视频：`render_video` → job → `render_service.render_video`

### 5.3 分流伪代码

```text
creds = load_runtime_model(tenant_id, "image" | "video")
match creds.provider:
  "volcengine_ark" -> ark_*_client(creds)
  "shangwu"        -> ShangwuClient(kind=..., creds)
  _                -> 明确报错（无 fallback）
```

### 5.4 不纳入 P0

- 图片 SSE 流式（1824137）
- 视频 callback / 任务列表 / 取消删除
- 方舟视频多模态里的音频、参考视频（可先只做 text + reference_image）
- LangChain ChatModel 直调生图/生视频（继续 Tool + 适配器）

---

## 6. 联调检查清单

- [ ] 方舟控制台已开通 Seedream / Seedance，并拿到可用 `model` / Endpoint ID
- [ ] AI Key 页已分别配置默认 `image`、`video`（provider 与赏舞二选一）
- [ ] 生图：一次请求返回 `data[].url`，能下载并落 OSS
- [ ] 生视频：创建得 `task_id`，轮询至 `succeeded`，转存 OSS 后业务可播放
- [ ] 切换默认 provider 后，无需改 `.env`，重启 Worker/API 后新作业走新上游
- [ ] 未把真实 Key 写入 Git

---

## 7. 实现顺序建议

1. 按本文对接 `ark_image_client`（同步生图，路径短）
2. 对接 `ark_video_client`（创建 + 单次查询；长轮询见可靠性文档）
3. `render_service` provider 分流 + ModelsPage Provider 选项
4. 长耗时调度改造见 [09-generation-async-reliability.md](./09-generation-async-reliability.md)（提交与轮询分离）
5. 用演示租户各跑通一条生图、一条生视频作业

字段或路径若与线上控制台不一致，**以官方最新文档为准**，改适配器映射即可，不必改业务表结构。
