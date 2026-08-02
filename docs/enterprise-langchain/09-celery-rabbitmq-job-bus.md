# 平台作业总线：Celery + RabbitMQ（统一方法）

> **已决策**：异步作业 **只用 Celery + RabbitMQ**，全局替换现有 Redis Stream（`queue_stream` / `apps.worker` / `script_job_*`）。  
> 本文确立统一用法，后续所有「投递后台任务、周期调度、长耗时生成」均按此模式扩展，禁止再开第二套队列。

关联：

- 生成可靠性细节：[../business-script-material/09-generation-async-reliability.md](../business-script-material/09-generation-async-reliability.md)
- 方舟生图/生视频：[../business-script-material/08-ark-image-video-integration.md](../business-script-material/08-ark-image-video-integration.md)

---

## 1. 决策

| 项 | 选定 | 说明 |
|----|------|------|
| Broker | **RabbitMQ** | 任务投递、ACK、多队列路由 |
| 执行器 | **Celery** | Worker 消费 + Beat 周期任务 |
| Result backend | **Redis**（可选）或禁用 | 业务结果以 MySQL 为准，不依赖 Celery result |
| 业务状态源 | **MySQL**（`job_run` / `generation_task` 等） | claim、阶段快照、对账只认 DB |
| 废弃 | Redis Stream 作业路径 | `enqueue_script_job`、`read_script_jobs`、`apps.worker` Stream 循环 |

Redis **保留**用途：缓存、限流、会话等；**不再**作为作业总线。

---

## 2. 统一原则（必须遵守）

1. **只通过封装投递**  
   业务代码禁止直接 `celery_app.send_task(...)` 散落；统一走 `packages.infra.jobs`（名称以落地为准）的 `enqueue_*` / `delay_*`。

2. **DB 是真相，队列是通知**  
   先写/更新业务表（或 `job_run`），再投递 Celery；Worker 只带 **主键 ID**，进任务后重新读库。禁止把大 payload 只放在消息里当唯一来源。

3. **短任务 vs 长等待拆开**  
   - 短任务：一个 Celery task 内跑完（秒～数十秒级）。  
   - 长耗时生成：submit / wait（Beat 轮询）/ finalize 三段，**禁止** task 内 `sleep` 长轮询上游。

4. **幂等与 claim**  
   可重入任务必须能靠 DB 状态 + claim 挡住双执行；Celery `acks_late` + 业务 claim 双保险。

5. **队列按职责命名，按进程消费**  
   见 §3；新增任务先选已有队列，不够再开新队列并补 Worker 部署。

6. **无第二套总线**  
   不再引入 Kafka「只给生成用」、不再保留 Stream「过渡双写」作为长期方案；迁移期可短双写，迁完删 Stream。

---

## 3. 队列与进程拓扑

### 3.1 队列

| 队列名 | 用途 | 示例任务 |
|--------|------|----------|
| `sync` | 短业务作业 | parse、structure、segment、material/shot/prompt 规划、index |
| `gen.submit` | 生成：提交上游 | 创建赏舞/方舟任务，写 `provider_task_id` |
| `gen.finalize` | 生成：落库完结 | 下载、OSS、`material_image`/`video_job`、完结 `job_run` |
| `default` | 杂项/未分类（尽量少用） | 运维脚本、一次性修补 |

### 3.2 进程（compose / 部署）

| 进程 | 命令形态 | 消费队列 |
|------|----------|----------|
| API | uvicorn | 不消费；只 `enqueue` |
| celery-worker-sync | `celery -A ... worker -Q sync -c N` | `sync` |
| celery-worker-gen | `celery -A ... worker -Q gen.submit,gen.finalize -c M` | 生成两队列 |
| celery-beat | `celery -A ... beat` | 不消费；只发周期任务 |

本地与 Docker 均提供上述角色；**禁止**一个「全能 worker」长期混跑全部队列导致生成拖死短任务（调试可临时 `-Q sync,gen.submit,gen.finalize`）。

---

## 4. 统一代码骨架（约定）

落地时包路径建议：

```text
packages/infra/celery_app.py     # Celery 实例、序列化、队列声明
packages/infra/jobs/
  __init__.py                    # 对外 enqueue API
  sync_tasks.py                  # sync 队列任务
  gen_tasks.py                   # submit / finalize
  beat_schedule.py               # 10s / 30s / 5min
```

### 4.1 投递短业务作业（替换 `enqueue_script_job`）

```text
# 业务侧（job_service.submit_job 末尾）
1. INSERT/拿到 job_run.id（status=queued）
2. jobs.enqueue_sync_job(job_run_id)
   → celery send to queue=sync, task=sync.run_job_run, args=[job_run_id]
```

```text
# sync.run_job_run(job_run_id)
1. DB mark_running（条件更新，失败则 return）
2. job_dispatch.execute_job(...)  # 现有逻辑，生成类除外
3. mark_done / mark_failed
```

### 4.2 投递长耗时生成

```text
# submit_job(kind=render_*)
1. 写 job_run + generation_task(status=pending)
2. 不直接长跑；等 Beat 按槽位投递，或可选立即 jobs.enqueue_gen_submit(task_id)（仍受 claim/槽位约束）
```

```text
# Beat 每 10s：gen.dispatch_pending
按租户槽位 claim pending → enqueue gen.submit

# gen.submit_one(task_id)
claim → 调适配器创建上游 → waiting_provider → 写 stage_snapshot

# Beat 每 30s：gen.poll_waiting
批量 claim waiting → 单次查上游 → 成功则 enqueue gen.finalize；失败则 failed

# gen.finalize_one(task_id)
下载 OSS → 写业务表 → succeeded → 完结 job_run
```

### 4.3 Beat 周期（固定）

| 周期 | Task | 职责 |
|------|------|------|
| 10s | `gen.dispatch_pending` | 租户槽位 + 投递 submit |
| 30s | `gen.poll_waiting` | 批量短轮询上游 |
| 5min | `gen.reconcile` | 卡住 30min 回查；超过 2h 强制失败 + 退款钩子 |

具体状态机、claim、快照字段见业务文档 09。

### 4.4 任务函数约定

```text
@celery_app.task(name="sync.run_job_run", bind=True, acks_late=True)
def run_job_run(self, job_run_id: str) -> None: ...

# 命名：{域}.{动作}
# 参数：只传 ID（str）
# 返回：None 或小 dict；前端不读 Celery result，读 MySQL
```

---

## 5. 配置（`.env` 形态）

```text
# 作业总线（Celery + RabbitMQ）
CELERY_BROKER_URL=amqp://user:pass@rabbitmq:5672//
CELERY_RESULT_BACKEND=         # 可空；业务结果走 MySQL
CELERY_TASK_DEFAULT_QUEUE=sync
CELERY_TASK_ACKS_LATE=true
CELERY_WORKER_PREFETCH_MULTIPLIER=1   # 长任务友好，避免预取囤积

# 生成槽位（Scheduler/Beat 使用）
GEN_MAX_INFLIGHT_PER_TENANT=3
GEN_SUBMIT_BATCH=20
GEN_POLL_BATCH=50
```

删除/停止使用：`SCRIPT_JOB_STREAM_KEY`、`SCRIPT_JOB_GROUP`、`QUEUE_STREAM_KEY` 作为作业总线（ingest 若仍用 Stream 需单独评估，默认一并迁 Celery `sync` 或独立队列 `ingest`）。

---

## 6. 全局替换步骤（实施顺序）

1. **基础设施**：compose 增加 RabbitMQ；装 `celery`、`amqp` 依赖。  
2. **搭骨架**：`celery_app` + 空 `sync.run_job_run` 打通联调。  
3. **切短任务**：`job_service.submit_job` 改为 Celery；`apps.worker` 改为 celery-worker-sync（或删掉 Stream 循环）。  
4. **切生成**：按 09 建 `generation_task` + `gen.*` 任务 + Beat。  
5. **拆 render**：去掉适配器内长 `sleep` 轮询。  
6. **下线 Stream**：删除 `queue_stream` 作业 API、compose 中旧 worker command、相关 env。  
7. **文档与验收**：所有新异步能力只登记到本文队列表。

迁移期允许「写 DB + 双投递 Stream/Celery」最多一个迭代，之后只保留 Celery。

---

## 7. 以后怎么加新异步能力（模板）

1. 是否长等待上游？  
   - 否 → `sync`（或新建短队列）一个 task，参数只传业务 ID。  
   - 是 → 扩展 `generation_task` 或同构表 + `*.submit` / Beat poll / `*.finalize`。  
2. 在 `packages/infra/jobs` 增加 task，**登记队列名**。  
3. 业务服务只调用 `jobs.enqueue_xxx(id)`。  
4. 需要周期扫库 → 只加 Beat 条目，不新起常驻「自写 while True」进程（除非 Beat 不够用再开特例并写明原因）。

---

## 8. 非目标

- Redis Stream 与 Celery 长期并存  
- 用 Celery result backend 替代 `job_run` 查询  
- Worker 内对上游 sleep 长轮询  
- 每个业务模块私自 `Celery()` 多实例  

---

## 9. 验收（总线级）

- [ ] parse 等短任务仅经 RabbitMQ + celery-worker-sync  
- [ ] 生视频等待期间 gen worker 不阻塞（无长 sleep）  
- [ ] Beat 三周期任务在 Flower/日志可见  
- [ ] 杀死 worker 再拉起：DB 状态可恢复，不重复创建上游（有 `provider_task_id`）  
- [ ] 代码库无新增 Redis Stream 作业投递  
