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
| 四级表：`episode` / `narrative_space` / `shot_plan` / `canvas_snapshot` | `models.py` + Alembic |
| 规则切分多集与叙事空间（集标记 + 场景变化 / 转场 / ≤15s），不调 LLM | `structure_parser` + `structure_service` |
| `record_status`（ai / confirmed）；重跑只清 ai | 资产 / 物料提示词 / 叙事空间 |
| 管理端：项目、上传、解析、目录树、确认、物料提示词 | `ScriptBizPage` |

未落地：视频提示词生成服务、地点身份回填、图片目录服务、反悔写回 UI、异步作业、SD 客户端、画布 UI。
表已建：`scene_space` / `costume_change` / `material_image` / `video_prompt` / `record_revision`；分镜服务已落地。

## 2. 已锁定决策

| 决策 | 结论 |
|------|------|
| 内容类型 | **不做带货（commerce）**。拆除 `content_type` 字段、校验、知识库类型分派机制与前端选项；只做解说漫节奏与规则 |
| 结构解析 | 按 04 的 **D6 / 2.1**：集边界用稿面标记（如 `剧集 [N]`）；叙事空间按**场景变化、转场、≤15 秒**切分，不用 Hook/Escalation/Cliffhanger；不进 LLM |
| product 建模 | 不做产品替换；不建 `product_asset`；知识库中带货相关条目一并删除 |
| 业务表迁移 | **Alembic**；补 `packages/business_script/models.py` 作 schema 唯一来源，服务层可继续裸 SQL |
| 迁移接管范围 | 现状 stamp 为 baseline；**剧本业务表**交 Alembic；平台基础表仍留 `init.sql` |
| 清障范围（第一段） | 只删未挂载的 `kb_service` + `knowledge_bases` router；九张死表、Qdrant 异步化、core↔governance 循环依赖本期不动 |
| 平台与业务分工 | 业务流水线保持确定性编排；经统一提示词装配层读 `apps-space` 模板并检索工艺知识；ReAct 留给 Playground |
| 生图 / 生视频 | 不直连方舟，走赏舞 Public API 薄客户端 + 提交前成本预估 |
| 人工确认机制 | **不做审批流**（无提交 / 审核 / 退回）；改为定版 + 废稿历史 + 反悔，状态仍只有 `ai` / `confirmed`；见 [06 第 5 节](./06-material-library-adoption.md#5-新锁定决策定版--废稿历史--反悔) |
| 参考项目 `script_material_library` | 按模块吸收表设计与建模思想，**不整体迁移**（无多租户 / int 主键 / 无 Alembic / 同步 Session 四条阻断）；吸收项与顺序见 [06 第 8 节](./06-material-library-adoption.md#8-吸收顺序与落点) |

## 3. 分阶段任务

顺序硬约束：清障与迁移 → 四级模型走完 → 任务化 → SD 客户端 → 画布。  
不可先做画布或生视频：维度未立全、异步未通时会二次返工。

### 第一段 · 清障与迁移底座

| 序号 | 任务 | 说明 |
|------|------|------|
| 1.1 | 删 legacy 知识库 | 删除 `packages/governance/kb_service.py`、`apps/api/app/routers/knowledge_bases.py`；若 `KB_READ` / `KB_WRITE` 仅被该路由使用则一并删除 |
| 1.2 | 撤除 content_type / commerce | 见下文「1.2 撤除清单」；语料改完后必须重新索引 |
| 1.3 | 接入 Alembic | async engine（aiomysql）；`models.py` 对齐现有九张剧本表；stamp baseline；首个 migration drop `script_project.content_type` |
| 1.4 | 去掉运行时建表双轨 | 删除 `packages/business_script/schema.py`；`main.py` 不再调用 `ensure_script_schema`；`init.sql` 撤出剧本业务建表段（种子数据保留） |

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

| 序号 | 任务 | 说明 |
|------|------|------|
| 2.1 | 规则结构解析器 | 输入 `txt` / `md` / `docx` / `fdx` → `episode`（如 `剧集 [N]`）+ `narrative_space`（场景变化 / 转场 / 累计时长将超 15s 时断开）；**禁止**用 Hook/Escalation/Cliffhanger 作空间边界；**不调 LLM** |
| 2.2 | 解析流程重构 | 规则切结构后，LLM 只对已切好的叙事空间做语义抽取（人物、道具、分镜）；去掉或降级对 LLM `scenes` 的依赖。进一步按 06 的 A3 引入 Facts / Decisions / Evidence 三层与按集增量复用决策 |
| 2.3 | `shot_service` | 分镜挂 `narrative_space_id`；规划 / 查询 / 确认；工具 `plan_shots` 落地 |
| 2.4 | `video_prompt` 改挂叙事空间 | 按 D1：一空间一段成片提示词；表与 API 同步 |
| 2.5 | 04 第 5 节剩余表 | `costume_change` / `bilingual_line` / `content_tag` / `material_image` / `video_job` 等按需落地（Alembic migration）；并入 06 的 A1 `material_image`、A2 `scene_space`、A4 `costume_change`，合并为同一批 migration |
| 2.6 | 目录手工编辑 + 定版反悔 | 集与叙事空间的增删改、排序；同批落 06 第 5 节的 revision 快照表与反悔接口 |

**前置**：规则解析器需要真实多集剧本样本（各格式至少两份），否则边界规则不可拍脑袋定。

**验收**

- 多集剧本可拆出多集、多叙事空间，且可手工改结构
- 分镜可按集 / 叙事空间检索
- 视频提示词 API 以 `narrative_space_id` 为粒度

### 第三段 · 任务化

| 序号 | 任务 | 说明 |
|------|------|------|
| 3.1 | 作业表与状态机 | 解析、物料、生图、生视频统一作业模型 |
| 3.2 | Worker | 消费 Redis Stream（已有 `queue_backend=redis_stream` 配置）；dispatch / poll / reconcile 搬 sd-2-c 设计 |
| 3.3 | API 改造 | HTTP 只投递作业并返回 job_id；查询与轮询接口 |

**验收**：长流程不再在请求内串行 `await` 全部 LLM / 外部调用；失败可重试且不覆盖 `confirmed`。

### 第四段 · 赏舞薄客户端

| 序号 | 任务 | 说明 |
|------|------|------|
| 4.1 | SD HTTP 客户端 | 读 `SD_*`；鉴权与 scopes 按 02 文档 |
| 4.2 | 生图 / 生视频工具 | `render_material_image` / `render_video` 落地；提交前成本预估 |
| 4.3 | 轮询与落 OSS | 任务状态回写；产物 URI 挂资产 / 叙事空间成片 |

**验收**：确认后的物料提示词可出图；确认后的叙事空间可出一段成片视频。

### 第五段 · 画布模式

| 序号 | 任务 | 说明 |
|------|------|------|
| 5.1 | `canvas_snapshot` API | 读写布局 / 视口 / 版本 |
| 5.2 | React Flow 迁移 | 从 sd-2-c copy 再改写；节点 = 工具可触发单元 |
| 5.3 | 双模式状态同步 | 对话 `event: step` 反映到画布节点状态 |

**验收**：单叙事空间画布可拖拽持久化；节点生成与对话工具为同一函数。

## 4. 明确不做（本期路线内）

- 带货 / commerce / product 替换 / `content_type` 分派机制
- 分镜级成片视频；剧本级或分镜级单画布
- 为画布单独写第二套编排
- 结构解析用 LLM
- 九张无人读写平台死表清理（可另开专项）
- Qdrant 异步客户端、core↔governance 循环依赖（可另开专项）
- 一致性自动质检、批量版本对比导出（原 B2，排在第五段之后）

## 5. 测试策略

不单独排测试专项。从第二段表结构与解析流程定型起，补 `business_script` 服务层测试；第一段以手工验收与迁移可重复执行为主。
