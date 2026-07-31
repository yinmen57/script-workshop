# Agent 工具选择方案：问题清单与约束

> 本文记录「工具选择 Agent + router + 专业 Agent」方案可能出现的问题，以及实施时必须落实的约束。
>
> 目标不是让 Agent 自由尝试工具，而是让它基于当前业务状态选择下一步可执行动作，并由服务端在执行前再次校验。

## 1. 目标架构

```text
用户请求
  ↓
tool-selector
  ├─ inspect 当前项目状态
  ├─ 判断缺失的前置条件
  ├─ 选择下一步工具或专业 Agent
  └─ 信息不足时请求补充或确认
  ↓
router
  └─ 执行选择结果，不重复猜测业务意图
  ↓
专业 Agent / 业务工具
  └─ 再次校验前置条件并执行
```

职责必须分开：

- `tool-selector`：只负责状态判断和下一步选择，不直接执行写操作。
- `router`：负责接收选择结果、委派执行和处理失败，不重新设计业务流程。
- 专业 Agent：负责具体领域产出，例如语义切分、分镜规划、视频片段编组和视频提示词。
- 业务工具：负责权限、数据归属、状态、幂等和不可覆盖规则。

## 2. 当前缺少的实现

以下内容属于「补齐即可落地」的能力。状态标记：`已完成` / `部分完成` / `未开始`。

### 2.1 工具选择 Agent · 已完成

落点：

- `agents/tool-selector/agent.yaml` + `prompts/system.md`
- 只挂 `inspect`，最大 4 步
- 结构化决策协议：`delegate` / `ask` / `confirm` / `stop` / `inspect`
- router 规则：模糊目标先 `delegate_to_tool-selector`，明确工具可跳过

选择 Agent 只负责判断下一步，不直接执行写操作。

### 2.2 inspect 查询工具 · 已完成

落点：`packages/business_script/inspect_service.py` + `tools/inspect.yaml`

支持 scope：

- `progress`：链路总览与建议下一步
- `structure`：集和叙事空间
- `assets`：人物、道具、地点
- `shots`：分镜和确认状态
- `segments`：视频片段和关联分镜
- `materials`：物料提示词、物料图、成片提示词
- `jobs`：运行中、失败和已完成任务

查询结果带 id、归属、`status`、`record_status`、`inspected_at`，不返回 `source_text`。

### 2.3 工具备注和参数说明 · 已完成

全部 `tools/*.yaml` 已补用途 / 前置 / 产出 / 是否改数据 / 是否费用 / 不适用场景 / 易混淆工具；参数含 description，`scope`、`target_type`、`job_status` 使用 enum。

新增工具：`inspect`、`confirm`、`revert`、`parse-structure`。

### 2.4 工具执行前置条件校验 · 已完成

落点：`packages/business_script/precondition_service.py`，在 `src/tools.py` 写工具入口调用。

覆盖：

- 项目 / 目标对象存在与归属；
- style_bible、分镜、片段等依赖；
- 已确认产物阻挡重跑；
- 生图 / 生视频要求 confirmed；
- 失败返回 `code` / `next_action` / `retryable`。

同类任务去重仍由 `job_service.submit_job` 的 dedupe key 负责。

### 2.5 结构化 selection 上下文 · 部分完成

已完成：

- `/chat/completions` 接受 `selection` 对象；
- `chat_service.prepare_completion` 注入系统前缀；
- 画布对话面板改为传结构化 selection，不再把 id 拼进用户原文。

未完成：

- 三栏工作台左树选中项全链路接入；
- selection 与数据库归属的服务端强校验；
- 用户文字与 selection 冲突时的交互确认 UI。

### 2.6 任务恢复和错误协议 · 部分完成

已完成：

- `job_service._job_public` 增加 `current_step` / `business_object` / `retryable` / `has_result`；
- `job_recovery_view` 供 inspect 使用；
- 前置条件错误带结构化 `details`。

未完成：

- job 失败时把完整 `details` 持久化到 `job_run.error`（目前多为字符串）；
- `waiting_confirmation` 状态机尚未独立建模。

### 2.7 并发、幂等和审计 · 部分完成

已有：稳定 dedupe key、活动任务去重、确认幂等、AI 清理限定目标、API 侧审计。

未完成：乐观版本 / updated_at 冲突检测的统一层；付费生成在 Agent 路径的二次确认闸门（当前靠工具 risk_level + prompt）。

### 2.8 前端状态同步 · 部分完成

已新建独立工作台（不替换旧 `ScriptBizPage`）：

- 路由：`/script-workspace`（全屏三栏）
- 左树：视频类（集→空间→片段→分镜懒加载）/ 素材类（人物·道具·地点）
- 中栏：视频类嵌入叙事空间画布；素材类展示资产/提示词/图
- 右栏：多轮对话 + step 轨迹，携带结构化 selection
- Agent step 后 `invalidateQueries(['script-workspace'])` 刷新左树

未完成：

- 画布片段分组层与左树片段选中联动高亮；
- selection 服务端归属强校验与冲突确认 UI；
- 页面级快照恢复（刷新后记住项目/选中）；
- 列表页与工作台状态统一。

## 3. 补齐后仍存在的运行问题

以下问题不是简单补一个文件就能消除，即使实现完整，运行时仍需通过约束控制。

### 3.1 选择 Agent 与 router 重复决策

当前 router 已经承担协调和 handoff 职责。新增选择 Agent 后，如果两个 Agent 都可以重新选择工具，会出现：

- 同一个请求被判断两次，增加延迟和 token 消耗；
- 选择 Agent 选择 `plan-video-segments`，router 又改成 `plan-shots`；
- 执行失败时无法判断是选择错误、委派错误还是业务工具错误。

约束：

1. 选择 Agent 输出下一步建议后，router 默认直接执行；
2. 只有服务端前置条件校验失败时，router 才能重新请求选择；
3. router 不得基于工具名称自行绕过选择结果；
4. 每次重新选择必须记录原因。

### 3.2 inspect 状态不完整导致错误选择

选择 Agent 不能只知道「有没有分镜」或「有几个片段」，还需要知道产物状态和任务状态。

至少需要提供：

- 项目、集、叙事空间、视频片段、分镜的 id 和归属关系；
- `status` 与 `record_status`；
- 当前是否存在 `confirmed` 产物；
- 是否存在运行中的同类 job；
- 最近一次失败 job 的错误原因；
- 项目是否已有 `style_bible`；
- 资产、提示词和图片是否满足下一步前置条件。

约束：

- `inspect` 返回摘要时不能丢失影响决策的状态字段；
- 不返回 `source_text` 等大字段，避免撑爆 Agent 上下文；
- 复杂查询需要提供明确的 `scope` 和筛选 id；
- inspect 的结果必须标注查询时间或版本，便于发现过期计划。

### 3.3 选择结果在执行前过期

选择和执行不是原子操作：

```text
inspect：空间没有视频片段
选择：plan-video-segments
其他请求：已经创建视频片段
执行旧计划
```

约束：

1. 选择 Agent 的输出只能视为建议，不能视为事实；
2. 每个写工具执行前必须重新查询关键前置条件；
3. 关键资源变化时必须拒绝旧计划或重新选择；
4. 使用 dedupe key 阻止同一对象的重复运行；
5. 需要时记录状态版本或更新时间，避免覆盖并发修改。

### 3.4 不能相信模型返回的 confidence

模型输出的 `confidence` 没有稳定的统计含义，不能作为自动执行、跳过确认或提升权限的依据。

约束：

- `confidence` 只能用于日志和界面展示；
- 最终判断必须依靠 schema、权限、数据库状态和业务规则；
- 不允许因为 confidence 高而跳过 `confirmed` 保护；
- 不允许因为 confidence 低而自动执行危险操作。

### 3.5 模糊目标引发过度执行

以下请求都可能有多种解释：

- 「处理第 3 集」
- 「把这场戏生成出来」
- 「继续上次任务」
- 「重新做一下这个片段」

Agent 可能自动执行完整链路，造成不必要的解析、覆盖或付费生成。

请求应先区分为：

1. 查询：只读，不改变数据；
2. 准备：解析、切分、规划、生成提示词；
3. 生成：调用生图、生视频、上传 OSS，可能产生费用；
4. 覆盖：重跑 AI 产物或替换当前版本。

约束：

- 查询请求不得自动触发写工具；
- 付费生成必须得到明确意图；
- 覆盖 AI 产物前要说明会清理哪些内容；
- 触及 `confirmed` 产物时必须要求用户先确认反悔或修改；
- 不能通过自然语言推测用户已经同意付费或覆盖。

### 3.6 多步骤计划可能陷入循环

典型循环：

```text
没有视频片段
  → 选择 plan-video-segments
没有分镜
  → 选择 plan-shots
没有确认资产
  → 选择 generate-material-prompts
又回到没有视频片段
```

约束：

- 每次请求设置最大决策步数；
- 同一工具失败后限制重试次数；
- 同一资源和同一阶段不得无限重复；
- 需要人工确认时必须暂停，而不是继续补步骤；
- 记录已执行工具、失败原因和当前阶段；
- 到达循环上限后向用户说明阻塞点。

### 3.7 选择 Agent 越权判断业务内容

选择 Agent 只能判断「是否调用某能力」，不能替专业 Agent 产出业务结果。

例如：

- 它可以判断是否需要 `narrative-segmenter`；
- 不能判断叙事空间应该切成几个；
- 可以判断是否需要视频片段编组；
- 不能自己决定哪些分镜属于同一片段；
- 可以判断是否需要生成视频提示词；
- 不能自己编写最终视频提示词。

约束：

- 选择 Agent 只返回工具 id、参数、原因和前置检查结果；
- 业务内容只由对应专业 Agent 生成；
- 选择 Agent 不得写入 `source_text`、分段正文或提示词正文。

### 3.8 工具备注即使补齐仍不能保证不误选

新增选择 Agent 后，工具文件名仍然不能作为主要判断依据。每个工具的描述必须说明：

- 做什么；
- 需要什么前置条件；
- 会产生什么结果；
- 是否修改数据；
- 是否清理 AI 产物；
- 是否产生费用；
- 什么情况下不应该使用；
- 容易与哪个工具混淆。

参数字段也必须有 description。能枚举的参数必须使用 `enum`，例如：

- `scope`；
- `target_type`；
- `narrative_space_id` 与 `video_segment_id` 的互斥语义；
- `status` 和 `record_status` 的合法值。

当前运行时会把工具 YAML 的 `description` 和 `parameters` 转成模型的 function schema，因此备注必须写在运行时实际加载的字段中，不能只新增一个未被 loader 读取的自定义字段。

### 3.9 当前选择上下文可能丢失

三栏工作台中，用户可能已经选中了：

```text
第 3 集 → 第 2 个叙事空间 → 视频片段 1 → 分镜 4
```

如果只把用户输入文字发给 Agent，Agent 还需要重新猜 id，容易操作错对象。

请求必须携带结构化 selection：

```json
{
  "project_id": "sprj_xxx",
  "selection": {
    "type": "video_segment",
    "id": "svs_xxx",
    "narrative_space_id": "sns_xxx",
    "episode_id": "sep_xxx"
  },
  "message": "重新生成这个片段"
}
```

约束：

- 当前选中对象由前端明确传递；
- 服务端仍然校验对象之间的真实归属；
- 用户文字和 selection 冲突时不能静默选择其中一个，应提示用户；
- 切换项目或页面后不得继续复用旧 selection。

### 3.10 任务恢复信息不足

「继续上次任务」要求 Agent 能理解 job 的阶段和失败位置。只返回 job id 和最终状态不够。

至少需要记录：

- job kind；
- 业务对象 id；
- dedupe key；
- 当前步骤；
- 输入摘要；
- 失败错误；
- 是否可重试；
- 已产生的结果；
- 是否等待人工确认。

恢复时必须从失败步骤继续，不能无条件从头执行，也不能重复生成已经确认的内容。

### 3.11 并发和幂等问题

用户可能同时从画布、右侧对话框和批量页面发起同一操作。

需要防止：

- 同一空间同时进行两次片段编组；
- 同一片段同时生成两版提示词；
- 旧请求覆盖新请求；
- 两个 Agent 同时清理 AI 产物；
- 一个页面显示成功，另一个页面仍显示运行中。

约束：

- 写工具必须有稳定 dedupe key；
- 运行中任务不能重复提交；
- 确认操作必须幂等；
- 清理 AI 产物必须限定 tenant、project 和目标对象；
- SSE、画布和列表页必须以服务端状态为准。

### 3.12 确认、反悔和费用边界不清

`confirm`、`revert`、生图、生视频不是同一种风险：

- 确认会改变版本状态；
- 反悔会恢复历史快照；
- 生视频可能产生费用；
- 重跑可能清理未确认 AI 结果；
- confirmed 产物不能被普通重跑覆盖。

约束：

- 选择 Agent 可以建议确认，但不能无提示执行确认；
- 反悔必须携带明确的 revision id；
- 付费操作和覆盖操作在工具描述中标明；
- 后端根据目标类型执行最终风险校验；
- 每次确认、反悔、付费生成都写审计记录。

### 3.13 Agent 输出和前端状态可能不一致

选择 Agent 或专业 Agent 返回成功，不代表浏览器中的画布和左侧树已经更新。

约束：

- 工具返回业务对象 id、状态和版本；
- 前端收到 step 后按对象 id 更新节点；
- 重要操作完成后重新拉取对应 scope；
- 不能只依赖 SSE 的文字消息更新状态；
- 页面刷新后必须以数据库快照恢复，而不是依赖内存状态。

### 3.14 错误信息不足导致 Agent 无法纠正

`没有分镜`、`操作失败` 这类错误不足以指导下一步。

错误应包含：

- 失败工具；
- 目标对象；
- 缺少的前置条件；
- 当前状态；
- 推荐的下一步；
- 是否可以重试。

示例：

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

以下规则由服务端保证，不能只写在 Agent prompt 中：

1. 工具参数和资源归属必须校验；
2. 写操作执行前必须重新检查前置条件；
3. `confirmed` 产物不能被普通重跑覆盖；
4. AI 产物清理必须限定目标范围；
5. 同一业务对象的任务必须幂等；
6. 付费生成和覆盖操作需要明确确认；
7. 选择 Agent 不得直接写入业务正文；
8. 任务达到循环或重试上限后必须停止；
9. 所有关键变更必须记录审计信息；
10. 前端展示以服务端最终状态为准。

## 5. 推荐的选择结果协议

选择 Agent 只返回结构化决策，不返回大段解释：

```json
{
  "decision": "delegate",
  "agent_id": "shot-planner",
  "tool_id": "plan-video-segments",
  "arguments": {
    "project_id": "sprj_xxx",
    "narrative_space_id": "sns_xxx"
  },
  "reason": "该空间已有分镜，但尚无未确认视频片段",
  "preconditions_checked": [
    "project_exists",
    "narrative_space_exists",
    "shots_exist",
    "no_confirmed_video_segments",
    "no_running_same_job"
  ],
  "requires_user_confirmation": false
}
```

`decision` 只允许：

- `inspect`：需要补充状态；
- `delegate`：选择工具或专业 Agent；
- `ask`：缺少用户信息；
- `confirm`：需要用户确认后才能继续；
- `stop`：当前状态不允许继续。

## 6. 实施验收

选择 Agent 上线前至少验证以下场景：

1. 只有剧本，没有资产：不能直接规划分镜；
2. 有资产，没有叙事空间：先解析或切分结构；
3. 有分镜，没有视频片段：选择片段编组；
4. 有片段，没有视频提示词：选择提示词生成；
5. 有确认片段：普通重跑必须停止；
6. 两个相同请求并发：只能产生一个有效任务；
7. 用户请求含糊：先询问，不自动执行完整链路；
8. job 中途失败：能定位失败步骤并给出下一步；
9. 选择结果过期：执行前校验失败并重新选择；
10. 画布和列表页同时操作：最终状态一致。

## 7. 结论

工具选择 Agent 可以提高工具选择的准确性，但它不是业务规则的替代品。

正确的职责关系是：

```text
工具备注帮助模型理解能力
inspect 提供当前事实
tool-selector 选择下一步
router 负责委派
业务工具负责最终校验
```

如果缺少最后一层服务端校验，选择 Agent 越准确，错误操作反而越容易被自动执行。因此实施顺序应当是：

1. 先补齐工具备注和参数描述；
2. 再补齐 inspect 返回的状态；
3. 再落实工具执行前的前置条件校验；
4. 最后接入 tool-selector；
5. 最后接入三栏工作台的 selection 上下文。
