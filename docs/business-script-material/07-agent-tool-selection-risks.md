# Agent 工具选择：问题清单与约束

> router 自行 `inspect` 并委派专业 Agent；服务端在写操作前再次校验前置条件。  
> 目标不是让 Agent 自由尝试工具，而是基于当前业务状态选择下一步可执行动作。

## 1. 目标架构

```text
用户请求
  ↓
router
  ├─ inspect 当前项目状态
  ├─ 判断缺失的前置条件与下一步
  ├─ 信息不足时 ask / confirm
  └─ delegate_to_* 委派专业 Agent
  ↓
专业 Agent / 业务工具
  └─ 再次校验前置条件并执行
```

职责：

- `router`：状态巡检、下一步判断、委派、失败处理与用户确认；不写业务正文。
- 专业 Agent：领域产出（解析、语义切分、物料、分镜/片段/提示词、媒体生成）。
- 业务工具：权限、数据归属、状态、幂等和不可覆盖规则。

Agent 列表：`router`、`parser`、`narrative-segmenter`、`asset-planner`、`shot-planner`、`media`。

## 2. 能力落点

状态标记：`已完成` / `部分完成` / `未开始`。

### 2.1 router 决策 · 已完成

落点：`business/apps/script_workshop/agents/router.py` + `prompts/router/system.md`

- 工具：`inspect` / `confirm` / `revert` + `delegate_to_*`
- 模糊目标先 `inspect`（优先 `scope=progress`），再按链路委派
- 链路顺序与专业 Agent 映射写在 router system prompt
- 最多 3 次 inspect，避免空转巡检

### 2.2 inspect 查询工具 · 已完成

落点：`business/script/inspect_service.py` + 工具 `inspect`

支持 scope：`progress` / `structure` / `assets` / `shots` / `segments` / `materials` / `jobs`。

查询结果带 id、归属、`status`、`record_status`、`inspected_at`，不返回 `source_text`。

### 2.3 工具备注和参数说明 · 已完成

工具元数据含用途 / 前置 / 产出 / 是否改数据 / 是否费用；参数含 description，枚举字段用 enum。

### 2.4 工具执行前置条件校验 · 已完成

落点：`business/script/precondition_service.py`，写工具入口调用。

覆盖：项目/对象归属、依赖、已确认产物阻挡重跑、生图/生视频要求 confirmed；失败返回 `code` / `next_action` / `retryable`。

同类任务去重由 `job_service.submit_job` 的 dedupe key 负责。

### 2.5 结构化 selection 上下文 · 部分完成

已完成：`/chat` 接受 `selection`；`prepare_completion` 注入系统前缀；画布对话传结构化 selection。

未完成：三栏工作台左树全链路接入；selection 归属强校验；文字与 selection 冲突确认 UI。

### 2.6 任务恢复和错误协议 · 部分完成

已完成：job 公开字段含 `current_step` / `business_object` / `retryable` / `has_result`；`job_recovery_view` 供 inspect；前置错误带结构化 `details`。

未完成：失败 `details` 完整持久化；`waiting_confirmation` 独立状态机。

### 2.7 并发、幂等和审计 · 部分完成

已有：稳定 dedupe key、活动任务去重、确认幂等、AI 清理限定目标、API 侧审计。

未完成：统一乐观版本冲突层；付费生成在 Agent 路径的二次确认闸门（当前靠 risk_level + prompt）。

### 2.8 前端状态同步 · 部分完成

独立工作台 `/script-workspace`：左树 / 中栏画布 / 右栏对话；Agent step 后刷新查询。

未完成：画布与左树联动高亮；selection 强校验；页面级快照恢复。

## 3. 运行时仍需约束的问题

### 3.1 决策与执行职责清晰

router 同时做「判断」与「委派」，避免再套一层选择 Agent。

约束：

1. 业务正文只由专业 Agent / 对应写工具产出；
2. 服务端前置条件失败时，按 `next_action` 补前置或向用户说明，不要空转 inspect；
3. 每次重新委派应能从 step 轨迹看出原因。

### 3.2 inspect 状态不完整导致错误选择

router 至少需要：对象 id 与归属、`status` / `record_status`、是否存在 `confirmed`、运行中同类 job、最近失败原因、是否有 `style_bible`、资产/提示词是否满足下一步。

约束：

- inspect 摘要不得丢失决策字段；
- 不返回 `source_text` 等大字段；
- 复杂查询用明确 `scope` 与筛选 id；
- 结果带查询时间，便于发现过期计划。

### 3.3 选择结果在执行前过期

```text
inspect：空间没有视频片段
决定：plan-video-segments
其他请求：已经创建视频片段
执行旧计划
```

约束：

1. router 的判断只是建议，不能视为事实；
2. 每个写工具执行前必须重新查前置条件；
3. 关键资源变化时拒绝旧计划；
4. dedupe key 阻止同一对象重复运行。

### 3.4 不能相信模型 confidence

`confidence` 仅日志/展示；最终判断靠 schema、权限、库状态与业务规则。不得因 confidence 跳过 `confirmed` 保护或自动执行危险操作。

### 3.5 模糊目标引发过度执行

请求先区分：查询 / 准备 / 付费生成 / 覆盖。

约束：

- 查询不得自动触发写工具；
- 付费生成必须得到明确意图；
- 覆盖前说明会清理哪些内容；
- 触及 `confirmed` 须先确认反悔或修改。

### 3.6 多步骤可能陷入循环

约束：最大决策步数；同工具失败限制重试；同资源同阶段不得无限重复；需人工确认时暂停；到达上限后说明阻塞点。

### 3.7 router 不得越权写业务内容

router 只判断「是否调用某能力」并委派，不能：

- 自行切叙事空间段数；
- 自行决定哪些分镜同属一片段；
- 自行编写最终视频/物料提示词正文。

### 3.8 工具备注不能保证不误选

工具描述须说明：做什么、前置、结果、是否改数据/清理/费用、不适用场景、易混淆工具。参数有 description；可枚举字段用 enum。备注必须落在运行时实际加载的字段上。

### 3.9 选择上下文可能丢失

请求须携带结构化 selection（project_id + selection + message）。服务端校验归属；文字与 selection 冲突时提示用户，不得静默二选一。

### 3.10 任务恢复信息不足

「继续上次任务」需要 job kind、业务对象、dedupe key、当前步骤、失败错误、是否可重试、已有结果、是否等待确认。从失败步骤继续，不无条件从头、不重复已确认内容。

### 3.11 并发和幂等

写工具稳定 dedupe key；运行中不可重复提交；确认幂等；清理 AI 产物限定 tenant/project/目标；前端以服务端状态为准。

### 3.12 确认、反悔和费用边界

- router 可建议确认，但不能无提示执行确认；
- 反悔须携带明确 revision id；
- 付费/覆盖在工具描述中标明，并由后端做最终风险校验；
- 确认、反悔、付费生成写审计。

### 3.13 Agent 输出与前端状态不一致

工具返回对象 id/状态/版本；前端按 id 更新；重要操作后重新拉取 scope；刷新后以数据库为准。

### 3.14 错误信息不足

错误应含：失败工具、目标对象、缺少前置、当前状态、`next_action`、是否可重试。

```json
{
  "code": "VIDEO_SEGMENT_SHOTS_REQUIRED",
  "message": "该叙事空间尚无分镜，不能编组视频片段",
  "target": {
    "type": "narrative_space",
    "id": "sns_xxx"
  },
  "next_action": "plan-shots",
  "retryable": false
}
```

## 4. 不可违反的执行规则

由服务端保证，不能只写在 Agent prompt 中：

1. 工具参数和资源归属必须校验；
2. 写操作执行前必须重新检查前置条件；
3. `confirmed` 产物不能被普通重跑覆盖；
4. AI 产物清理必须限定目标范围；
5. 同一业务对象的任务必须幂等；
6. 付费生成和覆盖操作需要明确确认；
7. router 不得直接写入业务正文；
8. 任务达到循环或重试上限后必须停止；
9. 所有关键变更必须记录审计信息；
10. 前端展示以服务端最终状态为准。

## 5. 验收场景

1. 只有剧本，没有资产：不能直接规划分镜；
2. 有资产，没有叙事空间：先解析或切分结构；
3. 有分镜，没有视频片段：选择片段编组；
4. 有片段，没有视频提示词：选择提示词生成；
5. 有确认片段：普通重跑必须停止；
6. 两个相同请求并发：只能产生一个有效任务；
7. 用户请求含糊：先询问，不自动执行完整链路；
8. job 中途失败：能定位失败步骤并给出下一步；
9. 判断过期：执行前校验失败并重新决策；
10. 画布和列表页同时操作：最终状态一致。

## 6. 结论

```text
工具备注帮助模型理解能力
inspect 提供当前事实
router 判断下一步并委派
业务工具负责最终校验
```

服务端校验是底线：模型选得越「自信」，缺少校验时错误操作越容易被自动执行。
