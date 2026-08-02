# 长耗时生成：异步调度与可靠性

> 目标：生图 / 生视频（赏舞、方舟 Seedream/Seedance）不再占用 Worker 做「sleep 长轮询」，改为 **提交与轮询分离**、可 claim、可对账、可排查。  
> **作业总线已决策为 Celery + RabbitMQ（全局唯一）**，统一方法见 [../enterprise-langchain/09-celery-rabbitmq-job-bus.md](../enterprise-langchain/09-celery-rabbitmq-job-bus.md)。  
> 上游协议见 [08-ark-image-video-integration.md](./08-ark-image-video-integration.md)。

---

## 1. 现状问题

当前链路（`job_run` + Redis Stream + `apps.worker`）：

```text
submit_job → Stream → worker process_job_message
  → render_service 提交上游
  → client.poll_task 内 asyncio.sleep 长轮询（可达数分钟）
  → 下载 OSS → mark_done
```

痛点：Worker 被 sleep 占满、重启难恢复、无租户槽位、无对账。  
全局替换后：**不再使用 Redis Stream 作作业总线**。

---

## 2. 目标语义

| 能力 | 要求 |
|------|------|
| sync / async 双队列 | 短任务与长耗时生成分流（Celery queue：`sync` / `gen.submit` / `gen.finalize`） |
| 租户并发槽位 | 限制同时 in-flight 生成数 |
| 批量投递 | Beat 每 10s 按槽位 claim `pending` → `gen.submit` |
| 批量短轮询 | Beat 每 30s 批量查上游终态；**禁止** task 内长 sleep |
| claim 乐观锁 | DB 条件更新，防重复提交/完结 |
| 阶段快照 | MySQL `stage_snapshot` JSON |
| 对账兜底 | 每 5min：卡住 30min 回查；超过 2h 强制失败 + 退款钩子 |

---

## 3. 架构（Celery + RabbitMQ）

```text
 API / Agent
      │
      ├─ 短任务 ──写 job_run──► enqueue sync.run_job_run ──► celery-worker-sync
      │
      └─ 生图/生视频 ──写 job_run + generation_task(pending)
                              │
              celery-beat ────┤ 10s  dispatch_pending → gen.submit
                              │ 30s  poll_waiting     → gen.finalize（成功时）
                              │ 5min reconcile
                              │
              celery-worker-gen ◄── 队列 gen.submit / gen.finalize
                              │
                              ├ submit：创建上游，waiting_provider
                              └ finalize：OSS + 业务表 + job_run 完结
```

- **等待上游**只存在于 DB 状态 + Beat 短轮询，不占用 worker 进程睡眠。  
- `job_run`：前端进度与去重外壳。  
- `generation_task`：生成生命周期与 claim/快照。

---

## 4. 队列与任务名

| 队列 | Celery task（约定） | 消息 |
|------|---------------------|------|
| `sync` | `sync.run_job_run` | `job_run_id` |
| `gen.submit` | `gen.submit_one` | `generation_task_id` |
| `gen.finalize` | `gen.finalize_one` | `generation_task_id` |
| （Beat） | `gen.dispatch_pending` / `gen.poll_waiting` / `gen.reconcile` | 无业务 ID |

投递一律经 `packages.infra.jobs` 封装（见平台总线文档），业务不直接碰 Celery API。

生成类 `job_run.kind`：`render_material_image`、`render_video`。  
创建后写 `generation_task(pending)`，**不再**端到端长跑。

---

## 5. 数据模型：`generation_task`

MySQL 表（JSON 快照，等价参考设计中的 JSONB）。

| 字段 | 说明 |
|------|------|
| `id` / `tenant_id` / `project_id` / `job_run_id` | 关联 |
| `kind` | `image` / `video` |
| `provider` | `shangwu` / `volcengine_ark` |
| `model_name` | 提交时快照 |
| `biz_ref_type` / `biz_ref_id` | `material_prompt` / `video_prompt` + id |
| `status` | 见状态机 |
| `provider_task_id` | 上游任务 ID |
| `claim_owner` / `claim_until` | 乐观锁 |
| `attempt` | 推进次数 |
| `stage_snapshot` | JSON 阶段与事件 |
| `error` / `oss_uri` / `result_url` | 结果与排查 |
| `submitted_at` / `last_polled_at` / 时间戳 | 对账用 |

索引：`(tenant_id, status, claim_until)`、`(status, last_polled_at)`、`(job_run_id)`、`(provider_task_id)`。

### 5.1 状态机

```text
pending → submitting → waiting_provider → finalizing → succeeded | failed | cancelled
```

方舟 **同步生图**（Seedream）：`submitting` 内拿到 URL 后可直接进 `gen.finalize`，跳过长时间 `waiting_provider`。  
异步上游（赏舞生图/视频、Seedance）：完整走 `waiting_provider` + Beat 轮询。

### 5.2 `stage_snapshot` 示例

```json
{
  "phase": "waiting_provider",
  "provider": "volcengine_ark",
  "provider_status": "running",
  "provider_task_id": "cgt-xxxx",
  "poll_count": 12,
  "events": [
    { "at": "...", "event": "submitted", "provider_task_id": "cgt-xxxx" },
    { "at": "...", "event": "poll", "provider_status": "running" }
  ]
}
```

`events` 保留最近约 50 条。

---

## 6. Claim 乐观锁

```sql
UPDATE generation_task
SET claim_owner = :owner,
    claim_until = :until,
    updated_at = CURRENT_TIMESTAMP(3)
WHERE id = :id
  AND status = :expected_status
  AND (claim_until IS NULL OR claim_until < CURRENT_TIMESTAMP(3));
```

`rowcount == 1` 才可推进。TTL 建议：submit 投递 60s、submit 执行 120s、poll 30s、finalize 180s、对账 60s。  
完成后清空 claim。

---

## 7. Beat 周期

| 周期 | Task | 行为 |
|------|------|------|
| **10s** | `gen.dispatch_pending` | 按租户 `GEN_MAX_INFLIGHT_PER_TENANT` claim `pending` → `gen.submit` |
| **30s** | `gen.poll_waiting` | 批量单次查上游；成功 → `gen.finalize`；失败 → failed + 完结 job_run |
| **5min** | `gen.reconcile` | 见 §8 |

常量示例：`GEN_MAX_INFLIGHT_PER_TENANT=3`，`GEN_SUBMIT_BATCH=20`，`GEN_POLL_BATCH=50`。

Celery worker：`acks_late=true`，`prefetch_multiplier=1`（生成队列）。

---

## 8. 对账与超时

| 条件 | 动作 |
|------|------|
| `waiting_provider` 无进展 ≥ **30 分钟** | claim → 回查上游；成功补 finalize；上游失败则本地 failed |
| 中间态自提交起 ≥ **2 小时** | 强制 failed，快照 `forced_timeout`，完结 job_run，调用退款钩子 |
| claim 过期 | 可被重新 claim |

退款钩子：当前无平台账本，P0 定义 `on_generation_forced_fail` + 日志；可选调上游取消（方舟文档 1521720）。账本接入后只填实现。

---

## 9. 模块改造点

| 模块 | 改造 |
|------|------|
| `packages/infra/celery_app.py` + `jobs/` | 新建；统一 enqueue |
| `job_service.submit_job` | 短任务 → Celery `sync`；生成 → `generation_task` |
| `job_dispatch` / `render_service` | 拆 submit / finalize；删除长 poll 循环 |
| 适配器 | 仅单次 `get_task` / 同步生图 |
| `apps.worker` | 改为 celery worker 或删除 Stream 循环 |
| compose | RabbitMQ + celery-worker-sync + celery-worker-gen + celery-beat |

前端继续看 `job_run`；可选展示 `stage_snapshot.phase`。

---

## 10. 实现顺序

1. 按 [平台总线文档](../enterprise-langchain/09-celery-rabbitmq-job-bus.md) 接通 Celery + RabbitMQ + `sync.run_job_run`（先迁短任务）。  
2. Alembic：`generation_task`。  
3. `gen.submit_one` / `gen.finalize_one` + 拆 `render_service`。  
4. Beat：dispatch / poll / reconcile。  
5. 下线 Redis Stream 作业路径。  
6. 接方舟双 provider（08）复用同一调度。

---

## 11. 验收

- [ ] 多条生视频并发时，worker 不因等待被 sleep 占满  
- [ ] 杀 gen worker 再拉起：`waiting_provider` 由 Beat 继续 poll，不重复创建上游  
- [ ] 双 Beat/双 worker 下 claim 防双 finalize  
- [ ] 30min+ 对账能纠偏；2h 强制 failed + 钩子  
- [ ] 短任务走 `sync`，不被生成队列拖死  
- [ ] 无新增 Stream 作业投递  

---

## 12. 非目标

- Redis Stream 与 Celery 长期双写  
- Celery result 替代 `job_run` 查询  
- task 内对上游长 sleep  
- 本阶段完整计费账本（仅退款钩子）  
