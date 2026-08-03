# 剧本工坊后续开发路线

> 本文是实施顺序与验收标准的唯一依据。  
> 目标形态见 [04-narrative-space-and-dual-mode.md](./04-narrative-space-and-dual-mode.md)。  
> 赏舞对接细节见 [02-sd-api-key-and-calls.md](./02-sd-api-key-and-calls.md)、[03-sd-config.md](./03-sd-config.md)。  
> 参考项目吸收范围见 [06-material-library-adoption.md](./06-material-library-adoption.md)。

## 1. 已落地（截止本文撰写）

| 能力 | 落点 |
|------|------|
| 项目 / 剧本上传（markitdown + OSS + 项目命名空间索引） | `project_service` / `ingest` |
| LLM 解析人物与归属道具；`style_bible` 落库 | `parse_service` |
| 物料提示词生成；业务链路注入工艺知识 | `material_service` + `knowledge_context` |
| 五级表：`episode` / `narrative_space` / `shot_plan` / `video_segment` / `canvas_snapshot` | `models.py` + Alembic |
| 规则粗切多集与叙事空间（集标记 + 场景变化 / 转场），不调 LLM | `structure_parser` + `structure_service` |
| 语义切分叙事空间：逐集 LLM 判边界，只收段号不收正文 | `narrative_segment_service` + `narrative-segmenter` Agent |
| 视频片段编组：LLM 按分镜内容判边界，只收镜号，≤15s 作硬校验 | `video_segment_service` + `plan-video-segments` |
| 项目知识库从工作台重建（叙事空间+人物+场景）；ConsistencyPack 接入生成 | `script_index_service` + `consistency_context` + 工作台「知识库」模式 |
| 地点身份 `scene_space` 回填并挂叙事空间 | `structure_service.ensure_scene_space` |
| 分镜规划 / 确认（挂 `narrative_space_id`） | `shot_service` + `plan_shots` 工具 |
| 成片视频提示词（一片段一段，D1） | `video_prompt_service` + `generate-video-prompts` |
| 图片目录登记 / 设当前指针 | `material_image_service` |
| 定版废稿历史 + 反悔写回 | `revision_service` + 管理端历史弹窗 |
| 叙事空间手工编辑 / 删除（ai） | `structure_service` + API |
| `record_status`（ai / confirmed）；重跑只清 ai | 资产 / 物料 / 叙事空间 / 分镜 / 成片提示词 |
| 管理端：项目、上传、解析、目录树、分镜、成片提示词、地点、反悔 | `ScriptBizPage` |
| 作业表 / Redis Stream Worker / HTTP 投递 job | `job_run` + `apps/worker` + `job_service` |
| 赏舞薄客户端：生图 / 生视频 / 余额预检 / 落 OSS | `sd_client` + `render_service` + `video_job` |
| 叙事空间画布：快照 API + React Flow + 节点调同一套 script-biz | `canvas_service` + `script-canvas/*` |
| 双模式 step 同步 | 画布对话面板 + Playground `BroadcastChannel` |

未落地：Facts/Decisions/Evidence 三层抽取（2.2 A3）、`costume_change` 抽取服务、集级增删改与排序。
表已建：`scene_space` / `costume_change` / `material_image` / `video_segment` / `video_prompt` / `record_revision` / `job_run` / `video_job`。

## 2. 已锁定决策

| 决策 | 结论 |
|------|------|
| 内容类型 | **不做带货（commerce）**。拆除 `content_type` 字段、校验、知识库类型分派机制与前端选项；只做解说漫节奏与规则 |
| 结构解析 | 按 04 的 **D6 / 2.1**：集边界用稿面标记（如 `剧集 [N]`），规则粗切按场景变化与转场，均不进 LLM；**叙事空间的语义边界交 LLM 判定**，只收段号不收正文，段号不连续即判失败 |
| 成片粒度 | 按 04 的 **D1**：叙事空间是语义单元，长度不设限；15 秒模型上限下沉到 `video_segment`，一片段一次生成，`video_prompt` 改挂 `video_segment_id` |
| 片段编组 | 按 04 的 **2.2.1**：由 LLM 按分镜内容判定哪几镜能一次连贯拍完，只收镜号不收正文；15 秒只作硬校验，多镜合计超限即判失败，不做机械累加兜底 |
| 知识库粒度 | 项目命名空间为可重建副本（叙事空间+人物+场景）；工作台 DB 为唯一事实；上传不盲切；删除项目清向量 |
| product 建模 | 不做产品替换；不建 `product_asset`；知识库中带货相关条目一并删除 |
| 业务表迁移 | **Alembic**；补 `business/script/models.py` 作 schema 唯一来源，服务层可继续裸 SQL |
| 迁移接管范围 | 现状 stamp 为 baseline；**剧本业务表**交 Alembic；平台基础表仍留 `init.sql` |
| 清障范围（第一段） | 只删未挂载的 `kb_service` + `knowledge_bases` router；九张死表、Qdrant 异步化、core↔governance 循环依赖本期不动 |
| 平台与业务分工 | 业务流水线保持确定性编排；经统一提示词装配层读 `apps-space` 模板并检索工艺知识；ReAct 留给 Playground |
| 生图 / 生视频 | 不直连方舟，走赏舞 Public API 薄客户端 + 提交前成本预估 |
| 人工确认机制 | **不做审批流**（无提交 / 审核 / 退回）；改为定版 + 废稿历史 + 反悔，状态仍只有 `ai` / `confirmed`；见 [06 第 5 节](./06-material-library-adoption.md#5-新锁定决策定版--废稿历史--反悔) |
| 参考项目 `script_material_library` | 按模块吸收表设计与建模思想，**不整体迁移**（无多租户 / int 主键 / 无 Alembic / 同步 Session 四条阻断）；吸收项与顺序见 [06 第 8 节](./06-material-library-adoption.md#8-吸收顺序与落点) |

## 3. 分阶段任务

顺序硬约束：清障与迁移 → 四级模型走完 → 任务化 → SD 客户端 → 画布 → 语义切分与片段层。  
不可先做画布或生视频：维度未立全、异步未通时会二次返工。

### 第一段 · 清障与迁移底座

| 序号 | 任务 | 说明 |
|------|------|------|
| 1.1 | 删 legacy 知识库 | 删除 `framework/governance/kb_service.py`、`apps/api/app/routers/knowledge_bases.py`；若 `KB_READ` / `KB_WRITE` 仅被该路由使用则一并删除 |
| 1.2 | 撤除 content_type / commerce | 见下文「1.2 撤除清单」；语料改完后必须重新索引 |
| 1.3 | 接入 Alembic | async engine（aiomysql）；`models.py` 对齐现有九张剧本表；stamp baseline；首个 migration drop `script_project.content_type` |
| 1.4 | 去掉运行时建表双轨 | 删除 `business/script/schema.py`；`main.py` 不再调用 `ensure_script_schema`；`init.sql` 撤出剧本业务建表段（种子数据保留） |

**1.2 撤除清单（代码与语料）**

- 知识：删除 `00-content-types.md`；删除 `02-roles-extraction.md` / `03-storyboard-templates.md` 中带货条目；`01-shot-language.md` / `01-script-structure.md` 去掉类型条件句，节奏规则改为无条件生效
- Agent：`router` / `parser` / `asset-planner` / `shot-planner` 的 system 与任务提示词去掉类型分派与 commerce 分支
- 业务：`_VALID_CONTENT_TYPES`、`knowledge_context` 中类型中文名拼接、`material_service` 对缺失 `content_type` 的硬校验、前端「带货」选项、`README` 内容类型说明
- 库：Alembic migration 删除 `script_project.content_type`

**验收**

- 空库可由 Alembic 从零升到最新；现有库 stamp 后可升级
- API 启动不再执行剧本业务建表
- 解析 → 物料提示词在无 `content_type` 下端到端可跑
- 重新索引后检索不到带货专属条目

**迁移命令（容器内）**

```powershell
# 现有库（表已由旧 ensure/init 建好）：认账 baseline 后跑后续 revision
docker exec -w /app ai-api alembic stamp 0001
docker exec -w /app ai-api alembic upgrade head

# 空库：直接升到最新
docker exec -w /app ai-api alembic upgrade head
```

### 第二段 · 四级模型走完

| 序号 | 任务 | 说明 | 状态 |
|------|------|------|------|
| 2.1 | 规则结构解析器 | 输入 `txt` / `md` / `docx` / `fdx` → `episode`（如 `剧集 [N]`）+ `narrative_space`（场景变化 / 转场 / 累计时长将超 15s 时断开）；**禁止**用 Hook/Escalation/Cliffhanger 作空间边界；**不调 LLM** | 已完成 |
| 2.2 | 解析流程重构 | 规则切结构后，LLM 只对已切好的叙事空间做语义抽取（人物、道具、分镜）；去掉或降级对 LLM `scenes` 的依赖。进一步按 06 的 A3 引入 Facts / Decisions / Evidence 三层与按集增量复用决策 | 基础完成；A3 待做 |
| 2.3 | `shot_service` | 分镜挂 `narrative_space_id`；规划 / 查询 / 确认；工具 `plan_shots` 落地 | 已完成 |
| 2.4 | `video_prompt` 改挂叙事空间 | 按 D1：一空间一段成片提示词；表与 API 同步 | 已完成 |
| 2.5 | 04 第 5 节剩余表 | `costume_change` / `bilingual_line` / `content_tag` / `material_image` / `video_job` 等按需落地（Alembic migration）；并入 06 的 A1 `material_image`、A2 `scene_space`、A4 `costume_change`，合并为同一批 migration | 表已建；`scene_space`/`material_image` 服务已接；`costume_change` 抽取与 `video_job` 待做 |
| 2.6 | 目录手工编辑 + 定版反悔 | 集与叙事空间的增删改、排序；同批落 06 第 5 节的 revision 快照表与反悔接口 | 叙事空间编辑/删除 + 反悔已完成；集级增删待补 |

**前置**：规则解析器需要真实多集剧本样本（各格式至少两份），否则边界规则不可拍脑袋定。

**验收**

- 多集剧本可拆出多集、多叙事空间，且可手工改结构
- 分镜可按集 / 叙事空间检索
- 视频提示词 API 以 `narrative_space_id` 为粒度

### 第三段 · 任务化

| 序号 | 任务 | 说明 | 状态 |
|------|------|------|------|
| 3.1 | 作业表与状态机 | 解析、物料、生图、生视频统一作业模型 | 已完成（`job_run` + `job_service`） |
| 3.2 | Worker | 消费 Redis Stream（已有 `queue_backend=redis_stream` 配置）；dispatch / poll / reconcile 搬 sd-2-c 设计 | 已完成（`apps/worker`；SD poll 留第四段） |
| 3.3 | API 改造 | HTTP 只投递作业并返回 job_id；查询与轮询接口 | 已完成（解析/物料/分镜/成片提示词） |

**验收**：长流程不再在请求内串行 `await` 全部 LLM / 外部调用；失败可重试且不覆盖 `confirmed`。

### 第四段 · 赏舞薄客户端

| 序号 | 任务 | 说明 | 状态 |
|------|------|------|------|
| 4.1 | SD HTTP 客户端 | 读 `SD_*`；鉴权与 scopes 按 02 文档 | 已完成（`business/adapters/sd_client.py`） |
| 4.2 | 生图 / 生视频工具 | `render_material_image` / `render_video` 落地；提交前成本预估 | 已完成（余额预检 + job 投递） |
| 4.3 | 轮询与落 OSS | 任务状态回写；产物 URI 挂资产 / 叙事空间成片 | 已完成（`material_image` / `video_job`） |

**验收**：确认后的物料提示词可出图；确认后的叙事空间可出一段成片视频。

### 第五段 · 画布模式

| 序号 | 任务 | 说明 | 状态 |
|------|------|------|------|
| 5.1 | `canvas_snapshot` API | 读写布局 / 视口 / 版本；自动保存就地更新 | 已完成 |
| 5.2 | React Flow 迁移 | 从 sd-2-c copy 再改写；节点按钮调 `/script-biz` 同一套能力 | 已完成 |
| 5.3 | 双模式状态同步 | 画布旁对话 `event: step` → 节点状态；调试台 BroadcastChannel | 已完成 |

**验收**：单叙事空间画布可拖拽持久化；节点生成与对话工具为同一函数。

入口：工坊叙事空间行「画布」→ `/script-biz/canvas/:spaceId`。

### 第六段 · 语义切分与片段层

起因：15 秒模型上限倒灌进了语义切分，第一集两个场景被切成 14 个叙事空间，知识库检索回来的也是碎片。根因是叙事空间同时承担语义单元与成片单元两个身份，必须拆开。

| 序号 | 任务 | 说明 | 状态 |
|------|------|------|------|
| 6.1 | 叙事空间去时长约束 | `structure_parser` 移除 15 秒硬拆，只按集标记与地点 / 转场粗切 | 已完成 |
| 6.2 | `narrative-segmenter` Agent | 逐集判定语义边界；送编号段落，收段号 + 节拍 / 氛围 / 断开理由；段号不连续即失败，无兜底 | 已完成 |
| 6.3 | `video_segment` 片段层 | 新表 + LLM 按分镜内容编组（只收镜号，≤15s 硬校验）；`video_prompt` / `video_job` 改挂 `video_segment_id` | 已完成 |
| 6.4 | 知识库按叙事空间入库 | `script_index_service`；向量索引支持自定义 payload；上传路径撤掉盲切索引 | 已完成（已扩展为空间+人物+场景 + ConsistencyPack） |
| 6.5 | 管理端与画布适配片段层 | 目录树展示节拍 / 氛围；片段列表与逐片段生成入口 | 目录树按钮已接，片段列表待补 |

**验收**

- 第一集切出的叙事空间数量与实际场次相当（个位数），且每个空间能说清为什么在那里断开
- 一个长叙事空间能编出多个视频片段，每段说得清这几镜为什么编在一起，逐片段出提示词并各自生成一段视频
- 知识库检索命中后可直接定位到「第几集第几个叙事空间」

**迁移命令（容器内）**

```powershell
docker exec -w /app ai-api alembic upgrade head
```

`0007` 会重建 `video_prompt` / `video_job`（挂载层从叙事空间改为视频片段，历史行补不出片段归属），已有提示词与视频任务记录会丢失，需要重新生成。

## 4. 明确不做（本期路线内）

- 带货 / commerce / product 替换 / `content_type` 分派机制
- 分镜级成片视频；剧本级或分镜级单画布
- 为画布单独写第二套编排
- 用 LLM 切集边界（叙事空间与片段边界走 LLM，见第 2 节）
- 视频片段之间的自动拼接与转场渲染
- 九张无人读写平台死表清理（可另开专项）
- Qdrant 异步客户端、core↔governance 循环依赖（可另开专项）
- 一致性自动质检、批量版本对比导出（原 B2，排在第五段之后）

## 5. 测试策略

不单独排测试专项。从第二段表结构与解析流程定型起，补 `business.script` 服务层测试；第一段以手工验收与迁移可重复执行为主。
