# 参考项目对照与吸收计划（script_material_library）

> 本文是「哪些能吸收、怎么吸收、什么不碰」的唯一依据。  
> 目标形态见 [04-narrative-space-and-dual-mode.md](./04-narrative-space-and-dual-mode.md)；实施顺序见 [05-dev-roadmap.md](./05-dev-roadmap.md)。

参考仓库：`git@codeup.aliyun.com:62cd523611fc0f0c9e2b547c/script_material_library.git`

| 用法 | 说明 |
|------|------|
| 本仓库 git remote | `script_material_library`（`git remote -v` 可见；`git fetch script_material_library`） |
| 本地只读副本 | `D:\pro\_ref\script_material_library`（刻意放在本仓库之外，不进版本库） |

## 1. 结论

**按模块吸收，不做整体迁移。**

对面是一套可运行的单体（FastAPI + 同步 SQLAlchemy + React），资源管理成熟度高于本项目，
但有三条硬阻断使「照搬表结构与服务层」不可行：

| 阻断 | 对面 | 本项目 | 后果 |
|------|------|--------|------|
| 多租户 | 全库无 `tenant_id` | 每张表都有 `tenant_id`，唯一约束含租户 | 每张表都要补租户列并重写唯一约束 |
| 主键 | int 自增，且把 id 存进 JSON 数组（`script_shot_ids` / `costume_ids` / `reference_image_ids`） | `String(32)` 前缀 id（`new_id("sns")`） | 所有外键与 JSON 内引用都要换类型 |
| 迁移 | `create_all` + 手写 `_ensure_columns()` 与 ad-hoc `ALTER TABLE`（`backend/app/database.py`，约 26KB） | Alembic 为 schema 唯一来源 | 迁移脚本必须重写，不能 copy |

叠加「对面同步 `Session`、本项目 async」，任何一块进来都是逐行改写，不是复制。
因此吸收对象是**建模思想与表设计**，不是代码文件。

## 2. 先澄清一个撞名

对面的 `SceneSpace` 与本项目的 `narrative_space` 名字相近，**语义完全不同，不可互相替代**。

| 概念 | 归属 | 定义 | 作用 |
|------|------|------|------|
| `SceneSpace`（对面） | 地点主数据 | `canonical_key` 在剧本内唯一，存 `anchor`（基准描述）与 `reference_image_url`（基准参考图），经 `SceneSpaceScene` 多对多绑到具体场 | 跨集视觉一致性锚点 |
| `narrative_space`（本项目） | 内容维度第三级 | 语义完整的一场戏（长度不设限） | 语义/知识库单位；画布与成片挂 `video_segment`（≤15s） |

两者应当并存：本项目当前 `narrative_space.time_place` 是自由文本，同一地点在不同集之间没有身份关联，
生图必然漂移。地点身份这一层是本项目的真实缺口。

## 3. 资源建模差距

对面没有单张 `Material` 表，而是按可生图实体分工：`Character`（主形象 + 花名册标记 + 人像审核态）、
`Costume`（角色 × 集 × 场景 的造型变化）、`Asset`（道具 / 场景视角 / 陈设，带分级与归属）、
`SceneSpace`、`CharacterAsset`（角色资产清单）、`MaterialImage`（统一图片目录）。

本项目现有 `character_asset` / `prop_asset` / `material_prompt` 三张。缺口按价值排序：

| 缺口 | 对面做法 | 为什么要 |
|------|----------|----------|
| 产物图片层 | `MaterialImage` 统一登记生成图 / 上传图 / 导入图，带提示词快照、生成参数、来源指向（`source_kind` + `source_id`），`(script_id, url)` 唯一 | 本项目完全空白；04 第 5 节本就欠此表 |
| 地点身份 | `SceneSpace.canonical_key` + `anchor` + 基准参考图 | 跨集一致性的根因，不补则生图漂移 |
| 造型变化 | `Costume`：角色 × 集 × 场景，带 `change_point` 与 evidence | 本项目只有 `costume_baseline` 单字符串，表达不了「第 3 集换西装」 |
| 重要度分级 | `Asset.importance` = 关键 / 次要 / 背景 | 决定哪些资源值得花钱生图，直接影响成本 |
| 图片引用协议 | 提示词内嵌 `[[ref:id]]`，生图时 remap 为 `@图片N` + `image_urls` | 让参考图真正生效的机制 |
| 全剧复用开关 | `series_wide` 布尔 | 控制某张已生成图能否被全剧任意集引用 |

`Asset` 的分级维度：`level1`（道具 / 场景・陈设 / 服化道，取值受 LLM 提示词硬约束）、
`level2`（二级细分）、`category`（美术策展分类，与 `level1` 正交）、`owner`（归属角色）。

## 4. 最该吸收的架构：Facts / Decisions / Evidence 三层

对面把物料抽取拆成四个职责清晰的层（`backend/app/pipeline/materials/`）：

| 层 | 文件 | 职责 | 是否调 LLM |
|----|------|------|-----------|
| Facts | `facts.py` | 从本集确定性提取硬事实：出场角色、地点、外观证据行（带稳定 id `{scene_code}:{line_index}`）、词典命中道具 | 否 |
| Decisions | `decisions.py` | 两阶段 LLM：先 inventory 盘点，再对每条出「复用 / 新建」决策 + 生图提示词；必须引用 facts | 是 |
| Evidence | `evidence.py` | 证据验真与索引：声明的 evidence 必须是原文子串，否则丢弃 | 否 |
| Persistence | `persistence.py` | 落库前再验真、按业务键二次匹配复用、执行状态守卫 | 否 |

对本项目的意义直接：当前 `parse_service` 是整篇丢给 LLM 抽 `characters` / `props`，
既无验真也无复用决策，更不是按集增量，多集剧本必然把同一角色在不同集抽成不同描述。
而第二段已落地的 `narrative_space.source_text` 正是 Facts 层需要的输入，接口现成。

配套的去重比本项目完整：`canonical_key`（去 EP 前缀、空白、标点后小写）作业务键，
落库时**即使 LLM 判定为新建，也按 `canonical_key` 二次匹配复用**；
跨集冲突另有 `MergeProposal` 走「规则召回 → LLM 校验 → 人工确认」，
合并时重绑外键、合并出场范围、删除源记录。

本项目的 `character_key` / `prop_key` 方向一致，但缺「复用决策」与「事后归并」两步。

## 5. 新锁定决策：定版 + 废稿历史 + 反悔

对面用 5 态 `RecordStatus`（AI / 待审核 / 人工已确认 / 已退回 / 人工修改）配员工提交、导演审批。
**本项目不采用审批流。** 没有多角色送审环节，改为：

| 环节 | 规则 |
|------|------|
| 定版 | 用户点确认，`record_status` 由 `ai` 变 `confirmed`，同时落一条 revision 快照 |
| 定版后修改 | 允许直接改，`record_status` 保持 `confirmed`；改动前先把当前内容快照为下一 revision |
| 反悔 | 选任一历史 revision 写回主记录；写回前先把当前内容也快照一条，防止反悔后丢失 |
| AI 重跑 | `confirmed` 记录不覆盖（现有规则不变）；`ai` 记录直接删除，**不进历史**，避免重跑垃圾撑爆历史表 |

状态枚举仍只保留 `ai` / `confirmed` 两态，不引入 `pending` / `rejected`。

### 5.1 历史表草案

一张泛化表承接全部文本类记录，沿用 `material_prompt` 已有的 `target_type` + `target_id` 风格：

| 列 | 说明 |
|----|------|
| `id` | `String(32)` 前缀 id |
| `tenant_id` / `project_id` | 租户与项目 |
| `target_type` | `character_asset` / `prop_asset` / `costume_change` / `scene_space` / `narrative_space` / `material_prompt` / `shot_plan` |
| `target_id` | 主记录 id |
| `revision_no` | 自 1 递增；`(target_type, target_id, revision_no)` 唯一 |
| `snapshot` | JSON，快照当时主记录的业务字段 |
| `change_reason` | `pin`（定版）/ `manual_edit`（人工改动）/ `revert`（反悔写回） |
| `created_by` / `created_at` | 操作人与时间 |

### 5.2 图片与视频不进历史表

生成产物天然带版本：每次生成登记一条 `material_image`（或成片记录），
主记录的 `image_url` 只是「当前选中」指针，其余留在目录里就是废稿历史。
因此二进制产物走「目录表 + current 指针」，只有文本类记录走 revision 快照表。

## 6. 不吸收清单

| 不吸收 | 原因 |
|--------|------|
| 审批流（提交 → 审核 → 退回） | 已按第 5 节改为定版 + 反悔 |
| 手工 `VideoClip` 成片单元 | 与 04 的 D1 冲突：成片单位是自动切分的叙事空间，不是人工选镜头组 |
| `ThreadPoolExecutor(max_workers=2)` 执行器 | 第三段走 Redis Stream worker；但 `JobRun` 的 `dedupe_key` 表设计可借 |
| `database.py` 手写迁移 | 本项目 schema 唯一来源是 Alembic + `models.py` |
| `Asset` 审核路径 | 该路径疑似未接线：全库无处将 `Asset.status` 写为待审核，且审核列表引用了 `Asset` 上不存在的 `episode_id` / `kind` 字段 |

## 7. 可直接对接的现成实现

对面已跑通本项目路线图第四段的全部内容：

| 能力 | 落点 | 要点 |
|------|------|------|
| 生图 | `pipeline/imagegen.py` | 提交图片任务 → 轮询 → 取结果 URL；对上游 502 有重试 |
| 生视频 | `pipeline/videogen.py` | duration / resolution / ratio 参数；轮询取成片 URL |
| 虚拟人像 | `pipeline/modellib.py` | 人物 / 造型需人像状态 active 才能进视频生成 |
| OSS | `services/oss_storage.py` | 生成图 key 为 `scripts/{id}/generated/{YYYY/MM}/{uuid}`；前端 STS 直传且策略只允许写 `scripts/{id}/uploads/` 前缀 |
| 模型调用审计 | `models.LlmCall` | token / 耗时 / 状态，关联作业与集 |
| 导出 | `export/excel.py` | Excel 与 JSON 导出 |

改写工作量集中在：同步改 async、补 `tenant_id`、int id 改前缀 id。

## 8. 吸收顺序与落点

按「解决真问题 / 工作量」比排序，并与 [05-dev-roadmap.md](./05-dev-roadmap.md) 的分段对齐：

| 序号 | 吸收项 | 对应路线图 | 说明 |
|------|--------|-----------|------|
| A1 | `material_image` 统一图片目录 | 第二段 2.5 | 边界清晰、不依赖其他改动；含来源指向与提示词快照 |
| A2 | `scene_space` 地点身份（`canonical_key` + `anchor` + 基准参考图） | 第二段 2.5 | 一致性根因；与 `narrative_space` 并存，不合并 |
| A3 | Facts / Decisions / Evidence 三层替换现有整篇抽取 | 第二段 2.2 增强 | 输入取已落地的 `narrative_space.source_text` |
| A4 | `costume_change` 造型变化表 | 第二段 2.5 | 04 第 5 节本就列入 |
| A5 | 定版 + 废稿历史 + 反悔（第 5 节） | 第二段 2.6 | 与目录手工编辑同批做，共用 revision 表 |
| A6 | 赏舞生图 / 生视频客户端 | 第四段 | 参考对面实现改写为 async + 多租户 |
| A7 | `job_run` + `llm_call` 表设计 | 第三段 | 只借表与 `dedupe_key` 幂等思路，执行器换 Redis Stream |

前置约束不变：清障与迁移 → 四级模型走完 → 任务化 → SD 客户端 → 画布。
A1 / A2 / A4 是建表，可与第二段剩余任务合并为同一批 Alembic migration。
