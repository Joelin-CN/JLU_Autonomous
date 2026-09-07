# API 接口文档（前端本地速查）

> **权威来源**：完整契约、类型映射、安全与错误处理见 **[../../docs/design/api.md](../../docs/design/api.md)**。本文件是前端本地的精简速查，与代码 (`electron/types.ts`、`electron/python/pythonBridge.ts`) 对齐。

接口分两类：**请求-响应（invoke）通道**（30 个，含 2 个 backend-settings 别名）和 **实时推送事件**（8 种）。

> 所有 invoke 通道使用 **Electron 内部类型**：账号 ID 为 `number`。渲染侧 `ChaoxingApi`（`string` ID、UI 形态类型）由 `ipcClient.ts` 做映射。

---

## 一、请求-响应通道（Renderer → Main，invoke）

### 1. 任务控制

#### `job:start` — 启动任务

```
请求: StartJobPayload
响应: { jobId: string }
```

```typescript
// Electron 层入参（ipcClient 在发送时附带 objective/strategy/options，但 handler 仅读取下列字段）
interface StartJobPayload {
  accountIds: number[]
  courseIds?: string[]
  mode?: 'full' | 'scan_only' | 'solve_only'
}
```

校验：`accountIds` 非空、≤50、正整数；RAM 安全检查（每账号 ~350MB，≤70% 空闲内存）；单任务互斥；500ms 限流。

#### `job:pause` / `job:resume` / `job:stop` — 全局运行控制

```
请求: string (jobId)
响应: void
```

分别向 Python 子进程发送 `PAUSE\n` / `RESUME\n` / `STOP\n`。

#### `job:pause-selected` / `job:resume-selected` / `job:stop-selected` — 逐账号控制

```
请求: JobControlPayload { jobId: string, accountIds?: number[] }
响应: void
```

校验每个 accountId 属于该 job。**选中集合 == 任务全部账号** → 降级为全局控制；**真子集 → 抛错**（当前 Python 后端无逐账号信令）。Mock 模式真实支持真子集。

#### `job:status` — 查询任务状态

```
请求: string (jobId)
响应: JobStatus
```

```typescript
interface JobStatus {
  jobId: string
  status: 'running' | 'paused' | 'completed' | 'stopped' | 'error'
  phase: JobPhase
  progress: number           // 0–100
  message?: string
  startedAt?: string         // ISO 8601
  finishedAt?: string        // ISO 8601
  accountIds: number[]
  courseIds?: string[]
  phaseIndex?: number
  lanes?: JobLaneStatus[]
}

interface JobLaneStatus {
  accountId: number
  status: 'pending' | 'running' | 'paused' | 'completed' | 'stopped' | 'error'
  progress: number
  currentTask?: string
  currentPhase?: string
  errorMessage?: string
}

type JobPhase =
  | 'idle' | 'login' | 'scan_courses' | 'process_sections'
  | 'solve_quiz' | 'completed' | 'paused' | 'stopped' | 'error'
```

---

### 2. 课程与扫描

#### `courses:scan` — 扫描课程

```
请求: ScanCoursesPayload { accountIds: number[], courseIds?: string[] }
响应: Course[]
```

#### `courses:list` — 获取账号课程列表

```
请求: number (accountId)   // 注意：handler 拒绝 0
响应: Course[]
```

```typescript
interface Course {
  id: string
  name: string
  accountId: number
  courseId: string
  classId?: string
  progress: number           // 0–100
  status: 'not_started' | 'in_progress' | 'completed' | 'failed'
  sections?: CourseSection[]
  lastActivity?: string
}

interface CourseSection {
  id: string
  title: string
  type: 'video' | 'quiz' | 'document' | 'discussion' | 'other'
  status: 'pending' | 'completed' | 'failed' | 'skipped'
  progress: number           // 0–100
}
```

> ✅ `courses:*` 已接真实后端：`python -m chaoxing.courses --account N` 读取扫描后落盘的发现状态；未扫描过返回空列表（`scanned=false`）。

---

### 3. 账号

#### `accounts:list` — 获取所有账号

```
请求: void
响应: Account[]
```

```typescript
interface Account {
  id: number
  username: string
  nickname?: string
  avatar?: string
  school?: string
  enabled: boolean
  createdAt: string
  updatedAt: string
}
```

#### `accounts:status` — 获取单个账号状态

```
请求: number (accountId)
响应: AccountStatus
```

```typescript
interface AccountStatus {
  accountId: number
  loggedIn: boolean
  scanning: boolean
  running: boolean
  lastScanAt?: string
  courseCount: number
  completedCount: number
}
```

> ✅ `accounts:list` 已接真实后端（`python -m chaoxing.accounts`）；⚠️ `accounts:status` 仍为桩数据（仅 account 1，UI 未调用）。

---

### 4. 设置

#### `settings:get` / `backend-settings:get` — 读取设置

```
请求: void
响应: Settings
```

```typescript
interface Settings {
  pythonPath: string
  maxWorkers: number
  headless: boolean
  browserTimeout: number
  quizSolver: 'doubao'
  logLevel: 'debug' | 'info' | 'warn' | 'error'
  accountsFilePath: string
  concurrencyTarget: number | null
  perAccountEstimateGB: number
  notifications: boolean
  logRetention: number
  pageLoadTimeout: number
  snapshotTimeout: number
  clickTimeout: number
  videoWatchTimeout: number
  quizAnswerTimeout: number
  quizRetryCount: number
  targetAccuracy: number
}
```

#### `settings:set` / `backend-settings:set` — 更新设置

```
请求: Partial<Settings>
响应: void
```

> `settings:*` 与 `backend-settings:*` 共享同一份磁盘存储 (`userData/settings.json`)。

---

### 5. 关注队列（工单）

#### `tickets:list` — 获取工单列表

```
请求: void
响应: Ticket[]   // 当前为空内存数组
```

```typescript
interface Ticket {
  id: string
  jobId: string
  type: 'captcha' | 'verification' | 'warning' | 'error'
  title: string
  message: string
  imageBase64?: string
  options?: string[]
  resolved: boolean
  resolution?: string
  createdAt: string           // ISO 8601
  resolvedAt?: string
}
```

#### `tickets:resolve` — 解决工单

```
请求: (ticketId: string, resolution: string)   // 两个位置参数
响应: void
```

### 6. 余额 / AI / 账号管理 / 系统资源（2026-08 新增通道）

| 通道 | 请求 | 响应 |
|------|------|------|
| `balance:query` | 无 | `Balance`（火山引擎现金余额） |
| `ai:status` / `ai:set` / `ai:test` | `{ apiKey?, model }` | AI 配置状态 / 保存 / 连通性测试 |
| `accounts:add` / `accounts:edit` / `accounts:remove` | 账号载荷 | void（原子写当前账号文件） |
| `accounts:default-path` | 无 | 默认账号文件绝对路径 |
| `dialog:open-file` | 无 | 文件选择器结果（账号文件） |
| `system:resources` | 无 | RAM / CPU / 运行时长（Node `os` 采样） |
| `memory:plan` | 无 | 按当前机器状态计算的并发计划 |
| `backend-settings:get` / `backend-settings:set` | 无 / `Partial<Settings>` | 与 `settings:*` 共用同一份 `userData/settings.json` |

---

## 二、实时推送事件（Main → Renderer）

> Python 后端通过 **stdout 输出 NDJSON**（每行一个 JSON 对象，含 `type` 判别字段）。PythonBridge 解析后通过 `webContents.send(channel, event)` 把**原始 `Python*Event` 对象**推给渲染进程。控制信号 (`PAUSE`/`RESUME`/`STOP`) 经 stdin 下行。

| type | IPC 通道 | 触发时机 |
|------|---------|---------|
| `PROGRESS` | `on-progress` | 任务进度更新（高频） |
| `PHASE` | `on-phase-change` | 阶段切换（中频） |
| `LOG` | `on-log` | 日志输出（高频） |
| `MEMORY` | `on-memory` | 内存预算快照（运行中 5 秒一次） |
| `TICKET` | `on-ticket` | 需要人工介入（低频） |
| `RESULT` | `on-result` | 自定义结果数据（低频） |
| `ERROR` | `on-error` | 异常发生（按需） |
| `DONE` | `on-completed` | 全部完成（1 次） |

### `PROGRESS` — `on-progress`

```json
{ "type": "PROGRESS", "jobId": "job_...", "percent": 45, "message": "正在处理：高等数学 第3章", "phase": "solve_quiz", "phaseIndex": 3 }
```

| 字段 | 类型 | 说明 |
|------|------|------|
| jobId | string | 任务 ID |
| percent | number | 进度 0–100 |
| message | string | 描述文本 |
| phase | string? | 当前阶段（可选） |
| phaseIndex | number? | 阶段序号（可选） |

### `PHASE` — `on-phase-change`

```json
{ "type": "PHASE", "jobId": "job_...", "phase": "solve_quiz", "fromPhase": "process_sections", "phaseIndex": 3 }
```

`phase` / `fromPhase` 取值：`idle` → `login` → `scan_courses` → `process_sections` → `solve_quiz` → `completed` / `paused` / `stopped` / `error`。

### `LOG` — `on-log`

```json
{ "type": "LOG", "jobId": "job_...", "level": "info", "message": "登录成功，账号：138****1234", "timestamp": "2026-06-25T12:00:00.000Z" }
```

`level`：`debug` / `info` / `warn` / `error`。非 JSON 的 stdout 行会被包装为 `LOG`(info)，stderr 行包装为 `LOG`(error，前缀 `[stderr]`)。

### `TICKET` — `on-ticket`

```json
{ "type": "TICKET", "jobId": "job_...", "ticket": { "id": "ticket_001", "jobId": "job_...", "type": "captcha", "title": "需要验证码", "message": "登录出现滑块验证码", "imageBase64": "...", "options": ["手动输入", "跳过此账号"], "resolved": false, "createdAt": "2026-06-25T12:00:05.000Z" } }
```

`ticket.type`：`captcha` / `verification` / `warning` / `error`（渲染侧映射为 severity：`error→critical`、`warning→warning`、其余→`info`）。

### `RESULT` — `on-result`

```json
{ "type": "RESULT", "jobId": "job_...", "data": { /* 自由格式，由后端定义 */ } }
```

### `ERROR` — `on-error`

```json
{ "type": "ERROR", "jobId": "job_...", "error": "登录失败：账号或密码错误", "stack": "Traceback ...", "phase": "login", "recoverable": false }
```

`recoverable` 缺省视为 `false`（不可恢复，终止 job）。

### `DONE` — `on-completed`

```json
{ "type": "DONE", "jobId": "job_..." }
```

> ⚠️ `DONE` 仅携带 `jobId`，**不含完成统计**。渲染侧 `CompletionEvent.results` 在 Electron 路径全为 0。若需真实统计，请通过 `RESULT` 事件单独推送。

### `MEMORY` — `on-memory`

```json
{ "type": "MEMORY", "jobId": "...", "budgetGB": 12.9, "projectChromeGB": 1.1, "perAccountAvgGB": 0.7, "remainingCount": 5, "level": "info", "message": "..." }
```

由后端 `MemoryMonitor` 每 5 秒采样后推送，驱动设置页/仪表盘的预算仪表。

---

## 三、通信架构

```
┌─────────────────────────────────────┐
│         Python 后端（子进程）         │
│     python -m chaoxing.api           │
└────────┬───────────────┬─────────────┘
         │ stdout NDJSON  │ stdin 信号 (PAUSE/RESUME/STOP)
         ▼                ▲
┌─────────────────────────────────────┐
│     Electron Main Process            │
│  electron/python/pythonBridge.ts     │
│  electron/ipc/*.handler.ts           │
└────────┬───────────────┬─────────────┘
         │ IPC push (事件) │ IPC invoke (请求-响应)
         ▼                ▼
┌─────────────────────────────────────┐
│       Vue3 Renderer                  │
│  ipcClient → Pinia Stores → UI       │
└─────────────────────────────────────┘
```

**命令行入口**：`python -m chaoxing.api --job-id <id> --accounts <csv> --mode <full|scan_only|solve_only> [--courses <csv>] [--grade-only] [--content-only] [--max-concurrent <n>] [--budget-gb <gb>] [--system-limit-gb <gb>] [--per-account-estimate-gb <gb>]`

---

## 四、对接优先级

| 优先级 | 接口 | 说明 |
|--------|------|------|
| P0 | `job:start` + stdout 事件流 | 核心执行链路 |
| P0 | `PROGRESS` `PHASE` `LOG` `DONE` | 实时反馈基本事件 |
| P1 | `accounts:list` | 账号列表（课程总览页需要） |
| P1 | `courses:list` `courses:scan` | 课程数据（课程总览页需要） |
| P2 | `job:pause` `job:resume` `job:stop` | 全局运行控制（逐账号控制需后端先支持信令） |
| P2 | `tickets:list` + `TICKET` 事件 | 关注队列 |
| P2 | `RESULT` `ERROR` 事件 | 结果统计与异常通知 |
| P3 | `settings:get` `settings:set` | 设置持久化 |
| P3 | `accounts:status` `job:status` | 状态查询 |
| P3 | `tickets:resolve` | 工单管理 |
