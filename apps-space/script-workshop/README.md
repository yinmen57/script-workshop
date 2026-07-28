# 剧本工坊（多 Agent 应用空间）

```text
script-workshop/
  app.yaml
  agents/
    router/         # 协调 Agent（ReAct）
    parser/         # 剧本解析
    asset-planner/  # 物料提示词
    shot-planner/   # 分镜与视频提示词
    media/          # 生图 / 生视频
  tools/            # 共享工具声明
  src/              # 工具代码入口
  knowledge/        # 知识库语料 + manifest.yaml
```

- 文件是 Agent 与工具的唯一配置来源。
- 项目、人物、道具、图片和视频任务等业务数据在 `packages/business_script` + `/api/v1/script-biz`，不写入本目录。
- `src/tools.py` 透传调用业务服务；管理端「剧本工坊」菜单可直接创建项目与解析。
- 修改后在管理端刷新应用空间页即可同步（按目录 mtime 热重载）。

## 知识库

`knowledge/` 存放工艺规范语料，`manifest.yaml` 声明目录到向量命名空间的映射。
语料文件用单独一行的 `---` 分隔知识条目，每条独立入库，条目长度控制在一个 chunk 内以免被切碎。

三个命名空间：

| namespace | 内容 |
| --- | --- |
| `script/craft/prompting` | 内容类型机制、脚本 17 字段、roles 提取口径、提示词模板、产品替换铁律 |
| `script/craft/cinematography` | 景别、机位、构图、运镜、按 content_type 区分的节奏 |
| `script/craft/visual-style` | 生图/生视频参数规范、光影调色、内容安全红线 |

内容类型：`content_type` 为脚本顶层字段，取值 `narration_comic`（解说漫）或 `commerce`（带货，含种草/测评/开箱）。标题含「解说漫」或「带货」的知识条目为类型专属，其余为通用；检索查询须带类型中文名，禁止跨类型套用。

索引（改语料后重跑，条目内容不变时为覆盖写入）：

```powershell
python scripts/index_knowledge.py --slug script-workshop
```

Agent 要用知识库，必须在 `agent.yaml` 中同时声明 `retrieve` 工具与 `namespaces` 列表，两者缺一会校验失败。
声明的 namespaces 必须落在 `knowledge/manifest.yaml` 内，并会注入 `retrieve` 的参数枚举；运行时再校验一次。
管理端应用空间详情页会展示知识库语料清单、条目数、索引状态，以及各 Agent 的引用关系。
