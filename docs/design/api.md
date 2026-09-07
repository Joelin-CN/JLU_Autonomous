# 前后端交互 API 文档 — 超星助手

> **版本**: v1.4
> **更新**: 2026-08-13
> **审计**: 多 Agent 并行全代码库审查 + correctness pass 续轮校正
> **目的**: 定义前端 (Electron + Vue 3) 与后端 (Python/JS 脚本) 之间的完整接口契约，供前后端独立开发和后续仓库融合使用。

> **v1.4 变更**：同步 2026-08-13 代码现状（2026-08-22 修订：invoke 通道 28 个）。Pinia Store 9 个、
> `courses:*` / `accounts:list` 已接真实后端、`--chromium-flags` 已移除、DeepSeek 完全移除
> （AI 仅 doubao）、新增 `MEMORY` 事件与 `system:resources` / `ai:*` / 账号管理 / 文件选择等通道；
> 修正设置映射与已知问题表。

> **v1.3 变更**：新增**余额查询**全链路（§4.7）——`balance:query` IPC 通道 + `balance.handler.ts`（spawn Anaconda 解释器跑 `python -m chaoxing.balance`）+ `getBalance()`（ipcClient / mockClient）+ `DashboardView` 实时余额卡片，替换原硬编码 `¥500`。

> **v1.2 变更**：逐账号运行时控制 (`pauseSelected`/`resumeSelected`/`stopSelected`) 已完整接入 Store / ipcClient / mockClient 与 IPC 层；Electron 模式对真子集显式抛错（见第 7 节）。类型检查迁移到 `vue-tsc 2.x`（兼容 Node 24 + TS 5.9）。多项 v1.1 「已知 Bug」已修复（见第 9.2 节）。v1.2 中的 `mapQuizSolver` 描述已被 v1.4 取代。

---

## 目录

1. [架构总览](#1-架构总览)
2. [Layer 1：前端 API 接口 (`ChaoxingApi`)](#2-layer-1前端-api-接口-chaoxingapi)
3. [Layer 2：Electron IPC 协议](#3-layer-2electron-ipc-协议)
4. [Layer 3：Python 子进程通信协议](#4-layer-3python-子进程通信协议)
5. [类型映射表](#5-类型映射表)
6. [Mock 开发模式](#6-mock-开发模式)
7. [安全规范](#7-安全规范)
8. [错误处理](#8-错误处理)
9. [已知问题与待办](#9-已知问题与待办)

---

## 1. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   Vue 3 前端 (Renderer)                   │
│                                                         │
│  Views / Components  ←→  Pinia Stores (9 stores)        │
│                                │                        │
│                   ChaoxingApi (interface)                │
│                   ├── ElectronApiClient (生产)            │
│                   └── MockApiClient   (开发)              │
└───────────────────────────┬─────────────────────────────┘
                            │ window.electronAPI
                            │ (contextBridge / IPC)
┌───────────────────────────▼─────────────────────────────┐
│                 Electron Main Process                    │
│                                                         │
│  IPC Handlers  ←→  PythonBridge                         │
│  (job / course /    (child_process.spawn)                │
│   status)                 │                             │
│  + RAM safety check       │                             │
│  + Rate limiter (500ms)   │                             │
└───────────────────────────┬─────────────────────────────┘
                            │ stdin/stdout JSON-line
┌───────────────────────────▼─────────────────────────────┐
│              Python 后端 (子进程)                          │
│                                                         │
│  python -m chaoxing.api (JSON-line 入口)                 │
│  ├── orchestrator.py (多账号编排)                        │
│  ├── solvers/ (quiz + content)                           │
│  └── AI 后端 (Doubao API)                                │
└─────────────────────────────────────────────────────────┘
```

**数据流方向**: Vue Store → ElectronApiClient → IPC invoke → Main Handler → PythonBridge → Python 子进程 → 超星平台

**事件流方向**: Python 子进程 → stdout JSON → PythonBridge 解析 → IPC push → ElectronApiClient 回调 → Pinia Store

---

## 2. Layer 1：前端 API 接口 (`ChaoxingApi`)

定义文件: `frontend/src/shared/lib/types.ts` (`ChaoxingApi` interface)

这是面向 Pinia Store 的最高层抽象接口，所有 Store 通过 `createApiClient()` 获取实例。

**工厂逻辑** (`apiClient.ts`):
- 检测 `window.electronAPI` 存在 → 返回 `ElectronApiClient` (IPC 桥接)
- 否则 → 返回 `MockApiClient` (浏览器开发模式)

### 2.1 任务控制 (Job Management)

#### `startJob(payload: StartJobPayload): Promise<JobHandle>`

启动一个新的自动化任务。

**请求参数 (`StartJobPayload`)**:
```typescript
interface StartJobPayload {
  objective: ObjectiveType    // 'catchup' | 'exam-sprint' | 'maintenance' | 'custom'
  strategy: StrategyType      // 'balanced' | 'careful' | 'overnight' | 'surgical'
  mode: ModeType              // 'course-scan' | 'section-scan' | 'single-exec' | 'batch-exec' | 'full-auto' | 'dry-run'
  courses: string[]           // 课程 ID 列表
  accounts: string[]          // 账号 ID 列表
  options?: Record<string, unknown>  // 扩展选项，透传到后端（如 { focus: 'quiz' | 'content' }）
}
```

**返回 (`JobHandle`)**:
```typescript
interface JobHandle {
  jobId: string
  status: ExecutionStatus     // 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'stopped'
  createdAt: number           // Unix timestamp (ms)
  startedAt?: number
  completedAt?: number
  objective: ObjectiveType
  strategy: StrategyType
  mode: ModeType
  courseCount: number
  accountCount: number
  progress: number            // 0–100
  phaseIndex: number
  phases: RuntimePhase[]
  lanes: AccountLane[]
}

interface RuntimePhase {
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  progress: number            // 0–100
  message?: string
}

interface AccountLane {
  accountId: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'paused' | 'stopped'
  progress: number            // 0–100
  currentTask?: string
  currentPhase?: string
  startedAt?: number
  errorMessage?: string
}
```

**mode 映射 (前端 → 后端)**:
| 前端 ModeType | 后端 mode 字符串 | 说明 |
|---------------|-----------------|------|
| `'course-scan'` | `'scan_only'` | 仅扫描课程结构 |
| `'section-scan'` | `'scan_only'` | 仅扫描章节 |
| `'dry-run'` | `'scan_only'` | 模拟运行 |
| `'batch-exec'` | `'solve_only'` | 仅刷题/仅内容 |
| `'full-auto'` | `'full'` | 全自动处理 |
| `'single-exec'` | `'full'` | 单任务执行 |

**错误**:
- 已有任务运行中时抛出 `Error("Job xxx is already running. Stop it first.")`
- 账号超过 50 个时抛出限制错误
- RAM 不足时抛出详细的内存警告（含建议值）

**前端触发位置**: `CourseAtlasView.vue` (startJob/startFullAuto 函数) → `execution.store.ts` (startJob action)

---

#### `pauseJob(jobId: string, accountIds?: string[]): Promise<void>`

暂停任务。支持全局暂停或按账号选择性暂停。

**参数**:
- `jobId`: 任务 ID
- `accountIds` (可选): 要暂停的账号 ID 列表。不传则暂停全部。

**路由逻辑** (`ipcClient.ts`): 传入非空 `accountIds` 时路由到 `pauseSelected`，否则路由到全局 `pauseJob`。

**行为**:
- 全局暂停: 向 Python 子进程发送 `PAUSE` 信号，设置 job.status 为 `'paused'`，停止所有 lane 计时器
- 按账号暂停: 仅停止指定 lane 的计时器；job 整体状态保持 `'running'`（仍有活跃 lane）

**模式差异**:
- **Mock 模式**: 完整支持真子集暂停（仅暂停匹配的 lane）
- **Electron 模式**: 选中集合 == 任务全部账号时降级为全局暂停；**真子集抛错**（当前 Python 后端不支持逐账号控制，见第 7 节）

**错误**: 任务不存在 / 账号不属于任务 / 真子集（Electron） 时抛出

**前端触发位置**: `ExecutionStudioView.vue` (handlePause / pauseSelectedLanes) → `execution.store.ts` (pauseJob / pauseSelectedLanes action)

---

#### `resumeJob(jobId: string): Promise<void>`

恢复整个暂停的任务。向 Python 子进程发送 `RESUME` 信号。

**行为**:
- 设置 job.status 为 `'running'`
- 将所有 paused 状态的 lane 恢复为 `'running'`
- 重新启动整体计时器和 lane 计时器

> **计时器累计**（v1.2 已修复）：全局计时器通过 `activeElapsedBase` 累加暂停前已用时长，lane 计时器通过 `stopLaneTimer` 在暂停时落账到 `laneElapsedMs`。暂停期间的时间不再丢失。

**错误**: 无活跃 Python 进程时抛出 `Error("No active Python process. The job cannot be resumed.")`

**前端触发位置**: `ExecutionStudioView.vue` ("全部继续" 按钮) → `execution.store.ts` (resumeJob action)

---

#### `resumeSelected(jobId: string, accountIds: string[]): Promise<void>`

恢复选中的暂停 lane。

- **Mock 模式**: 恢复匹配的 paused lane，并在并发上限内激活 pending lane
- **Electron 模式**: 选中集合 == 全部账号时降级为全局 `resumeJob`；真子集抛错

**前端触发位置**: `ExecutionStudioView.vue` ("继续选中" 按钮) → `execution.store.ts` (resumeSelectedLanes action)

---

#### `stopJob(jobId: string, accountIds?: string[]): Promise<void>`

停止任务。支持全局停止或按账号选择性停止。

**参数**:
- `jobId`: 任务 ID
- `accountIds` (可选): 要停止的账号 ID 列表。不传则停止全部。

**行为**:
- 全局停止: 向 Python 发送 `STOP` 信号 → 5s SIGTERM → 8s SIGKILL，设置 job.status 为 `'stopped'`，注销所有事件监听
- 按账号停止: 将指定 lane 状态设为 `'stopped'`；若所有 lane 都已停止，则停止 job 和事件监听

> **类型修正**（v1.2 已修复）：`AccountLane.status` 类型联合现已包含 `'stopped'`，不再使用 `as any` 绕过类型检查。

**模式差异**: 同 `pauseJob` —— Mock 支持真子集，Electron 真子集抛错。

**错误**: 任务不存在 / 真子集（Electron） 时抛出

**前端触发位置**: `ExecutionStudioView.vue` (handleStop / stopSelectedLanes) → `execution.store.ts` (stopJob / stopSelectedLanes action)

---

#### `pauseSelected` / `stopSelected`

签名: `(jobId: string, accountIds: string[]): Promise<void>`。语义同上述按账号控制，是 `pauseJob`/`stopJob` 携带 `accountIds` 时的显式入口。`execution.store.ts` 的 `pauseSelectedLanes` / `stopSelectedLanes` 会先按 lane 状态过滤（pause 仅取 running，stop 取 running/paused/pending）再调用。

---

#### `getJobStatus(jobId: string): Promise<JobHandle>`

查询任务当前状态。返回完整的 JobHandle（含 phases 和 lanes）。

**错误**: 任务不存在时抛出 `Error("Job xxx not found")`

---

### 2.2 数据查询 (Data Queries)

#### `scanCourses(accountIds?: string[]): Promise<Course[]>`

触发课程扫描（浏览器自动化），返回发现的课程列表。

```typescript
interface Course {
  id: string
  name: string
  teacher?: string
  coverUrl?: string
  progress: number           // 0–100
  totalSections: number
  completedSections: number
  sections?: SectionDef[]
  accountId?: string
  url?: string
}

interface SectionDef {
  id: string
  name: string
  parentId?: string
  children?: SectionDef[]
  completed: boolean
  type?: string              // 'video' | 'quiz' | 'document' | 'discussion' | 'other'
  duration?: number
}
```

**当前状态**: ✅ 已接真实后端——`courses:scan` 读取 `python -m chaoxing.courses` 落盘的发现状态（实际扫描经 `job:start --mode scan_only` 触发）。

**前端触发位置**: `CourseAtlasView.vue` (scanClicked / "一键扫描") → `course.store.ts` (scanCourses action)

---

#### `getCourses(accountId?: string): Promise<Course[]>`

获取指定账号的已缓存课程列表。不传 `accountId` 则返回所有账号的课程。

**当前状态**: ✅ 已接真实后端——读取 `discovered_courses_chaoxing-chrome-N.json`；未扫描返回空列表。

**前端触发位置**: `CourseAtlasView.vue` (onMounted, fire-and-forget) → `course.store.ts` (fetchCourses action)

---

#### `getAccounts(): Promise<Account[]>`

获取所有配置的账号。

```typescript
interface Account {
  id: string
  username: string           // 手机号
  displayName: string
  status: AccountStatus      // 'online' | 'offline' | 'error' | 'checking'
  avatar?: string
  lastChecked?: number       // Unix timestamp (ms)
  errorMessage?: string
}
```

**当前状态**: ✅ 已接真实后端——`python -m chaoxing.accounts` 读取当前生效账号文件。

**前端触发位置**: `App.vue` (onMounted), `DashboardView.vue` (onMounted), `CourseAtlasView.vue` (onMounted)

---

#### `getAccountStatus(accountId: string): Promise<Account>`

获取单个账号的实时状态（含登录态、是否在扫描、课程计数等）。

**当前状态**: ⚠️ 仍为桩数据（仅 account 1，当前 UI 未调用）。

---

### 2.3 配置与工单 (Settings & Tickets)

#### `getSettings(): Promise<Settings>`

```typescript
interface Settings {
  theme: 'light' | 'dark'
  language: string              // 'zh-CN'
  maxConcurrency: number        // 1-8 (前端) → Electron 层映射为 maxWorkers
  quizSolver: AIProvider        // 仅 'doubao'（DeepSeek/OpenAI/Gemini/Qwen 已移除）
  quizRetryCount: number        // 0-10
  logRetention: number          // days，启动时清理 data/logs
  notifications: boolean        // 桌面通知
  debugMode: boolean
  headless: boolean             // 无头浏览器
  targetAccuracy: number        // 60-100 (仅前端，未同步到后端)
  accountsFilePath: string
  concurrencyTarget: number | null
  perAccountEstimateGB: number
  pythonPath: string            // 空 = 使用 PATH 上的 python
  pageLoadTimeout: number
  snapshotTimeout: number
  clickTimeout: number
  videoWatchTimeout: number
  quizAnswerTimeout: number
}
```

**持久化**:
- 前端: `localStorage` key `'chaoxing-assistant-settings'`
- 后端: Electron `userData/settings.json`

**注意**: 前端 `Settings` 与 Electron 后端 `Settings` 是两个不同的接口，存在字段差异。
`videoSpeed` / `sectionDelay` / `autoResolveCaptcha` 死开关已于 2026-08-13 移除；
超时项、重试、日志保留、通知等通过 `CHAOXING_TIMEOUT_*` / `CHAOXING_RETRY_*` 环境变量注入后端。

---

#### `setSettings(settings: Settings): Promise<void>`

持久化设置。前端通过 1 秒防抖 (`debouncedSync`) 自动同步到后端。

**流**: `settings.store.ts` watch → `saveToStorage()` (localStorage) + `debouncedSync()` (1s debounce → `api.setSettings()`)

**同步方向**: 单向（前端 → 后端）。后端设置变更不会主动推送到前端。

---

#### `getTickets(): Promise<Ticket[]>`

```typescript
interface Ticket {
  id: string
  title: string
  message: string
  severity: TicketSeverity     // 'info' | 'warning' | 'critical'
  courseId?: string
  accountId?: string
  resolved: boolean
  resolvedAt?: number          // Unix timestamp (ms)
  resolution?: string
  createdAt: number
}
```

**前端触发位置**: `App.vue` (onMounted), `DashboardView.vue` (onMounted) → `attention.store.ts` (fetchTickets action)

---

#### `resolveTicket(ticketId: string, resolution: string): Promise<void>`

标记工单为已解决。在 `tickets` 数组中原地修改 `ticket.resolved = true`。

**前端触发位置**: `AttentionQueueView.vue` (resolveTicket / "处理完成" 按钮) → `attention.store.ts` (resolveTicket action)

---

#### `getBalance(): Promise<Balance>`

查询火山引擎（豆包）账户的现金余额。**与任务流程完全解耦**——不依赖运行中的 job，独立 spawn
Anaconda 解释器执行 `python -m chaoxing.balance`（详见 §4.7）。

**返回 (`Balance`)**:
```typescript
interface Balance {
  provider: string
  accountId: number
  availableBalance: string   // 金额字段均为 string，保留小数精度
  cashBalance: string
  creditLimit: string
  arrearsBalance: string
  freezeAmount: string
  currency: string           // 固定 'CNY'
  checkedAt: number          // epoch ms（后端 ISO `checkedAt` 解析而来）
}
```

**模式差异**:
- **Electron 模式**: `balance:query` → `balance.handler.ts` spawn Anaconda 解释器，解析单行 `BALANCE`/`ERROR` JSON
- **Mock 模式**: 返回固定模拟余额（`¥326.50`），无网络请求

**错误**: 解释器缺失 / 凭证文件缺失 / SDK 未装 / 30s 超时 时抛出（中文提示）。前端在 Dashboard 卡片
上以「余额查询失败：<原因>」展示，不阻塞页面其余加载。

**前端触发位置**: `DashboardView.vue` (onMounted, fire-and-forget `loadBalance()`)

---

### 2.4 事件订阅 (Event Subscriptions)

所有事件订阅方法返回一个清理函数（调用即取消订阅）。前端 `execution.store.ts` 在 `registerEventListeners()` 中统一管理所有订阅。

#### `onProgress(cb: (e: ProgressEvent) => void): () => void`

```typescript
interface ProgressEvent {
  jobId: string
  phase: string
  phaseIndex: number
  percent: number
  message: string
  timestamp: number
  laneId?: string            // 多账号时标识具体账号
}
```

**前端处理**: `execution.store.ts` 更新整体 `progress`（非终态事件封顶 99%），并触发一次
`getJobStatus` 拉取最新泳道/阶段状态（`refreshStatus`）。

---

#### `onPhaseChange(cb: (e: PhaseChangeEvent) => void): () => void`

```typescript
interface PhaseChangeEvent {
  jobId: string
  fromPhase: string
  toPhase: string
  phaseIndex: number
  timestamp: number
}
```

**前端处理**: 主进程按 `PHASE_RANK`（login/scan_courses→0，process_sections/solve_quiz→3，
completed→4，归一 0..4 缩放到当前模式阶段数）推导 `job.phaseIndex` 后随事件下发；
`execution.store.ts` 用 `applyPhaseToSteps(toPhase)` 即时推进阶段时间线（打 ✓）。

---

#### `onLog(cb: (line: { level: string; message: string; timestamp: number }) => void): () => void`

日志实时推送。前端转发到 `logStore.addLog(level, message)`。

**前端处理**:
- `execution.store.ts` 在 `registerEventListeners()` 中订阅
- 日志存储上限: 500 条 (`log.store.ts` MAX_LINES = 500)
- 溢出策略: 保留最新 500 条 (`slice(-MAX_LINES)`)
- 日志 ID 全局自增 (`nextId++`)

---

#### `onTicket(cb: (ticket: Ticket) => void): () => void`

实时推送新工单。前端转发到 `attentionStore.addTicket(ticket)`。

**前端处理**:
- 新工单 `unshift` 到 tickets 数组头部
- 工单存储上限: 200 条 (`attention.store.ts` MAX_TICKETS = 200)
- 溢出策略: 保留最新 200 条 (`slice(0, MAX_TICKETS)`)
- ⚠️ 无去重: 同一 ticket ID 可能重复添加

---

#### `onCompleted(cb: (e: CompletionEvent) => void): () => void`

```typescript
interface CompletionEvent {
  jobId: string
  success: boolean
  results: {
    totalSections: number
    completedSections: number
    failedSections: number
    totalQuizzes: number
    solvedQuizzes: number
    failedQuizzes: number
    durationMs: number
  }
  timestamp: number
}
```

**前端处理**: `execution.store.ts` — 成功时设置 `status = 'completed'`、`progress = 100`、`endTime = Date.now()`。无论成功失败都停止所有计时器。

> ⚠️ **Electron 路径限制**：后端 `DONE` 事件只携带 `jobId`，不含统计数据。`ElectronApiClient.onCompleted` 因此把 `success` 硬编码为 `true`，`results` 全部字段置 0。若需要真实完成统计（题数/正确率/耗时），后端应改为通过 `RESULT` 事件单独推送，或扩展 `DONE` 负载并相应更新 `ipcClient.ts`。Mock 模式会填充真实模拟统计。

---

#### `onError(cb: (e: ErrorEvent) => void): () => void`

```typescript
interface ErrorEvent {
  jobId: string
  error: string
  phase: string
  recoverable: boolean
  timestamp: number
}
```

**前端处理**: `execution.store.ts` — 设置 `error`；若 `!recoverable`，则设置 `status = 'error'` 并停止所有计时器。

---

#### `onResult(cb: (data: unknown) => void): () => void`

接收 Python 后端发来的自定义结果数据。自由格式，由后端定义结构。

**Electron IPC 层**: `on-result` 通道推送 `PythonResultEvent { type: 'RESULT', jobId: string, data: unknown }`

---

### 2.5 生命周期

#### `dispose(): void`

释放当前 API 客户端实例注册的所有事件监听器。

#### `removeAllListeners(): void`

清除该 API 客户端实例注册的所有监听器。当前实现等同于 `dispose()`。

> **注意**：渲染侧 `ChaoxingApi.removeAllListeners()` 不接受参数；Electron `preload.ts` 暴露的 `electronAPI.removeAllListeners(channel: string)` 接受通道名，但渲染层不直接调用它（统一走 `dispose()` 释放存储的 cleanup 函数）。

> **资源释放**（v1.2 已修复）：`execution.store.ts` 的 `unregisterEventListeners()` 现已调用 `api.dispose()`，`reset()` 经由 `unregisterEventListeners()` 一并释放，不再残留通道级监听器。

---

## 3. Layer 2：Electron IPC 协议

定义文件: `frontend/electron/types.ts`

### 3.1 通道列表

```typescript
const IPC_CHANNELS = {
  // Renderer → Main (invoke) — 30 个通道
  JOB_START:               'job:start',
  JOB_PAUSE:               'job:pause',
  JOB_RESUME:              'job:resume',
  JOB_STOP:                'job:stop',
  JOB_PAUSE_SELECTED:      'job:pause-selected',
  JOB_RESUME_SELECTED:     'job:resume-selected',
  JOB_STOP_SELECTED:       'job:stop-selected',
  JOB_STATUS:              'job:status',
  COURSES_SCAN:            'courses:scan',
  COURSES_LIST:            'courses:list',
  ACCOUNTS_LIST:           'accounts:list',
  ACCOUNTS_STATUS:         'accounts:status',
  SETTINGS_GET:            'settings:get',
  SETTINGS_SET:            'settings:set',
  TICKETS_LIST:            'tickets:list',
  TICKETS_RESOLVE:         'tickets:resolve',
  JOB_RESOLVE_TICKET:      'job:resolve-ticket',
  BALANCE_QUERY:           'balance:query',
  SYSTEM_RESOURCES:        'system:resources',
  MEMORY_PLAN:             'memory:plan',
  AI_STATUS:               'ai:status',
  AI_SET:                  'ai:set',
  AI_TEST:                 'ai:test',
  ACCOUNTS_ADD:            'accounts:add',
  ACCOUNTS_EDIT:           'accounts:edit',
  ACCOUNTS_REMOVE:         'accounts:remove',
  ACCOUNTS_DEFAULT_PATH:   'accounts:default-path',
  DIALOG_OPEN_FILE:        'dialog:open-file',
  SYSTEM_VALIDATE_PYTHON:  'system:validate-python',

  // Main → Renderer (push) — 8 个通道
  ON_PROGRESS:      'on-progress',
  ON_PHASE_CHANGE:  'on-phase-change',
  ON_LOG:           'on-log',
  ON_TICKET:        'on-ticket',
  ON_COMPLETED:     'on-completed',
  ON_ERROR:         'on-error',
  ON_RESULT:        'on-result',
  ON_MEMORY:        'on-memory',
} as const
```

> `backend-settings:get/set` 已于 2026-08-22 移除（与 `settings:get/set` 完全重复且零调用），
> invoke 通道总数 30 → 28；同日新增 `system:validate-python`（Python 路径行内校验）。
> `job:resolve-ticket`（验证码回传，见 §4.2）、`balance:query`（余额查询，见 §4.7）、
> `system:resources` / `memory:plan` / `ai:*` / 账号管理 / `dialog:open-file` 均为独立通道。

**2026-08 新增通道速查**

| 通道 | 说明 |
|------|------|
| `system:resources` | 实时 RAM/CPU/运行时长（Node `os` 采样，无 Python） |
| `memory:plan` | 空闲时按当前机器状态计算的并发计划 |
| `ai:status` / `ai:set` / `ai:test` | AI 配置读取 / 原子写 `doubao.txt` / 方舟连通性测试 |
| `accounts:add` / `accounts:edit` / `accounts:remove` / `accounts:default-path` | 账号文件原子增删改 + 默认路径 |
| `dialog:open-file` | 文件选择器（自定义账号文件） |
| `on-memory` | 后端 `MEMORY` 事件推送（预算仪表） |

### 3.2 Invoke 通道详情

#### `job:start`

- **方向**: Renderer → Main
- **请求**: `StartJobPayload { accountIds: number[], courseIds?: string[], mode?: 'full' | 'scan_only' | 'solve_only' }`
- **返回**: `{ jobId: string }`
- **限流**: 500ms 冷却
- **校验**:
  - `accountIds`: 必填，最多 50 个，必须为正整数（支持 string → parseInt 转换）
  - **RAM 安全检查**: 启动前按 `(总内存 − 基线) × 75%` 与 CPU 线程数计算最大并发，超预算账号排队分批执行；运行中每 5 秒实测收紧。
  - **互斥检查**: 同一时间只允许一个活跃任务
- **行为**: 创建 Job 记录 → 创建 PythonBridge → 绑定事件 → spawn Python 子进程

#### `job:pause`

- **方向**: Renderer → Main
- **请求**: `jobId: string`
- **返回**: `void`
- **限流**: 500ms 冷却
- **行为**: 向 Python 发送 `PAUSE\n` 信号，更新 job.status 为 `'paused'`

#### `job:resume`

- **方向**: Renderer → Main
- **请求**: `jobId: string`
- **返回**: `void`
- **限流**: 500ms 冷却
- **行为**: 向 Python 发送 `RESUME\n` 信号，更新 job.status 为 `'running'`，job.phase 重置为 `'idle'`（实际阶段由下一个 PHASE 事件更新）
- **错误**: 无活跃 Python 进程时抛出

#### `job:stop`

- **方向**: Renderer → Main
- **请求**: `jobId: string`
- **返回**: `void`
- **限流**: 500ms 冷却
- **行为**: 向 Python 发送 `STOP\n` 信号 → 5s 后 SIGTERM → 8s 后 SIGKILL，更新 job 状态，清理 bridge 引用

#### `job:pause-selected` / `job:resume-selected` / `job:stop-selected`

- **方向**: Renderer → Main
- **请求**: `JobControlPayload { jobId: string; accountIds?: number[] }`
- **返回**: `void`
- **校验** (`validateControlPayload`): 解析 job，校验 `accountIds`（非空、正整数、≤50），并验证**每个 accountId 都属于该 job**（否则抛 `Account X is not part of job Y`）
- **行为**:
  - 当 `accountIds.length === job.accountIds.length`（选中即全集）→ 降级为对应的全局 `pauseWholeJob` / `resumeWholeJob` / `stopWholeJob`
  - 否则（真子集）→ 调用 `selectedControlUnsupported()`，**抛出**:
    > `Per-account runtime control is not supported by the current Python backend. Use the global pause/resume/stop controls in Electron mode.`
- **设计依据**: 当前 PythonBridge 只有整进程级 `PAUSE`/`RESUME`/`STOP`，无逐账号信令。Electron 模式选择**显式失败而非伪造逐账号成功**，等后端支持真正的逐账号控制后再放开。Mock 模式因为是纯前端模拟，能够真实实现逐 lane 控制（见第 6/7 节）。

#### `job:status`

- **方向**: Renderer → Main
- **请求**: `jobId: string`
- **返回**: `JobStatus`

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
  | 'idle' | 'login' | 'scan_courses'
  | 'process_sections' | 'solve_quiz'
  | 'completed' | 'paused' | 'stopped' | 'error'
```

> `ElectronApiClient.getJobStatus` 会将 `JobStatus` 重整为渲染侧 `JobHandle`：`phases`/`objective`/`strategy`/`createdAt` 取自 `startJob` 时缓存的 `currentHandle`（后端 `JobStatus` 不携带这些字段），`startedAt`/`finishedAt`(→`completedAt`) 由 ISO 字符串解析为 epoch ms。

#### `courses:scan`

- **方向**: Renderer → Main
- **请求**: `ScanCoursesPayload { accountIds: number[], courseIds?: string[] }`
- **返回**: `Course[]`（Electron 内部类型）
- **当前状态**: ✅ 已接真实后端——`python -m chaoxing.courses --account N` 读取发现状态；未扫描返回空列表（`scanned=false`）

```typescript
interface Course {
  id: string
  name: string
  accountId: number
  courseId: string          // 课程在超星平台的 ID
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

#### `courses:list`

- **方向**: Renderer → Main
- **请求**: `accountId: number`
- **返回**: `Course[]`
- **当前状态**: ✅ 已接真实后端（同上）

#### `accounts:list`

- **方向**: Renderer → Main
- **请求**: 无
- **返回**: `Account[]`（Electron 内部类型）
- **当前状态**: ✅ 已接真实后端——`python -m chaoxing.accounts` 读取当前账号文件

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

#### `accounts:status`

- **方向**: Renderer → Main
- **请求**: `accountId: number`
- **返回**: `AccountStatus`
- **当前状态**: ⚠️ 仍为桩数据（仅 account 1，当前 UI 未调用）

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

#### `settings:get` / `settings:set`

- **方向**: Renderer → Main
- **请求**: `settings:get` 无参数；`settings:set` 接受 `Partial<Settings>`
- **返回**: `Settings` 对象（Electron 后端类型）
- **持久化**: Electron `userData/settings.json`
- **类型**: Electron 层 `Settings` 包含 `pythonPath`, `maxWorkers`, `headless`, `browserTimeout`, `quizSolver`（仅 `doubao`）, `logLevel`, 账号文件路径、内存并发、超时/重试等字段

```typescript
interface Settings {
  pythonPath: string           // Python 解释器路径，默认 '' = PATH 上的 python
  maxWorkers: number           // 最大并发 worker 数，默认 2
  headless: boolean            // 无头浏览器模式
  browserTimeout: number       // 浏览器超时 (ms)，默认 30000
  quizSolver: 'doubao'         // DeepSeek/本地已移除
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

#### `tickets:list`

- **方向**: Renderer → Main
- **请求**: 无
- **返回**: `Ticket[]`（内存数组拷贝）

#### `tickets:resolve`

- **方向**: Renderer → Main
- **请求**: `ticketId: string, resolution: string`
- **返回**: `void`
- **行为**: 原地修改 ticket 的 `resolved`/`resolution`/`resolvedAt` 字段

#### `backend-settings:get` / `backend-settings:set`

- **方向**: Renderer → Main
- **行为**: 与 `settings:get/set` 共享同一存储后端，读取/写入 `Settings` JSON 文件
- **注意**: 两个 settings 通道对（`settings:*` 和 `backend-settings:*`）操作同一份数据和文件，仅通道名不同

### 3.3 Push 通道详情

所有 Push 通道为 **Main → Renderer** 单向推送，通过 `webContents.send()` 发送。

#### `on-progress`

- **Payload**: `PythonProgressEvent`
```typescript
interface PythonProgressEvent {
  type: 'PROGRESS'
  jobId: string
  percent: number
  message: string
  phase?: string
  phaseIndex?: number
}
```

#### `on-phase-change`

- **Payload**: `PythonPhaseEvent`
```typescript
interface PythonPhaseEvent {
  type: 'PHASE'
  jobId: string
  phase: JobPhase
  fromPhase?: JobPhase
  phaseIndex?: number
}
```

#### `on-log`

- **Payload**: `PythonLogEvent`
```typescript
interface PythonLogEvent {
  type: 'LOG'
  jobId: string
  level: 'debug' | 'info' | 'warn' | 'error'
  message: string
  timestamp: string          // ISO 8601
}
```

#### `on-ticket`

- **Payload**: `PythonTicketEvent`
```typescript
interface PythonTicketEvent {
  type: 'TICKET'
  jobId: string
  ticket: Ticket              // Electron 层 Ticket 类型
}

// Electron 层 Ticket
interface Ticket {
  id: string
  jobId: string
  type: 'captcha' | 'verification' | 'warning' | 'error'
  title: string
  message: string
  imageBase64?: string        // 验证码截图
  options?: string[]
  resolved: boolean
  resolution?: string
  createdAt: string           // ISO 8601
  resolvedAt?: string
}
```

#### `on-completed`

- **Payload**: `PythonDoneEvent`
```typescript
interface PythonDoneEvent {
  type: 'DONE'
  jobId: string
}
```

#### `on-error`

- **Payload**: `PythonErrorEvent`
```typescript
interface PythonErrorEvent {
  type: 'ERROR'
  jobId: string
  error: string
  stack?: string
  phase?: JobPhase
  recoverable?: boolean
}
```

> `recoverable` 缺省（`undefined`）会被 `ElectronApiClient.onError` 转为 `false`，即默认视为不可恢复并终止 job。

#### `on-result`

- **Payload**: `PythonResultEvent`
```typescript
interface PythonResultEvent {
  type: 'RESULT'
  jobId: string
  data: unknown               // 自由格式
}
```

---

## 4. Layer 3：Python 子进程通信协议

实现文件: `frontend/electron/python/pythonBridge.ts`

### 4.1 进程启动

```
spawn('python', ['-m', 'chaoxing.api', ...args], {
  stdio: ['pipe', 'pipe', 'pipe'],
  env: {
    PYTHONUNBUFFERED: '1',
    ...allowedEnv           // 仅白名单环境变量
  }
})
```

**入口**: `python -m chaoxing.api`（后端 repo 提供）

**命令行参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| `--job-id` | `string` | 任务唯一标识 |
| `--accounts` | `string` | 逗号分隔的账号 ID 列表 |
| `--mode` | `string` | `full` / `scan_only` / `solve_only` |
| `--courses` | `string` | 逗号分隔的课程 ID 列表（可选） |
| `--max-concurrent` | `int` | 运行时信号量大小（Electron 按内存/CPU 计划计算） |
| `--budget-gb` | `float` | 项目内存预算（GB） |
| `--system-limit-gb` | `float` | 系统已用内存急停阈值 |
| `--per-account-estimate-gb` | `float` | 初始单 Chrome 实例估算 |

**Chromium 内存优化参数**（由 Bridge 自动注入）:
```
--renderer-process-limit=1
--disable-dev-shm-usage
--max-old-space-size=512
```

**环境变量白名单**（与 `frontend/electron/python/pythonBridge.ts` 的注入列表一一对应）:

| 变量 | 说明 |
|------|------|
| `PYTHONUNBUFFERED=1` | 强制无缓冲输出（必需） |
| `CHAOXING_WORKSPACE` | 项目工作目录（dev=backend/，打包=userData/workspace） |
| `CHAOXING_DATA_DIR` | 运行数据根（dev=仓库 data/，打包=userData/data） |
| `CHAOXING_HEADED` | 浏览器可见模式 (`"1"` / `"0"`) |
| `CHAOXING_ACCOUNTS_FILE` | 账号凭证文件覆盖路径（系统设置下发） |
| `CHAOXING_TIMEOUT_PAGE_LOAD` | 页面加载超时（秒） |
| `CHAOXING_TIMEOUT_SNAPSHOT` | 快照超时（秒） |
| `CHAOXING_TIMEOUT_CLICK_ACTION` | 点击超时（秒） |
| `CHAOXING_TIMEOUT_VIDEO_WATCH` | 视频观看超时（秒） |
| `CHAOXING_TIMEOUT_QUIZ_ANSWER` | 答题超时（秒） |
| `CHAOXING_TIMEOUT_SECTION_COMPLETE` | 章节完成超时（秒） |
| `CHAOXING_RETRY_QUIZ_MAX` | 每题最大重试 |
| `CHAOXING_RETRY_TARGET_SCORE` | 目标正确率 |
| `PATH`, `SYSTEMROOT`, `SYSTEMDRIVE`, `TEMP`, `TMP` | 系统基础变量 |
| `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH` | 用户路径变量 |
| `PYTHONPATH`, `PYTHONHOME` | Python 环境变量 |

超时/重试变量由前端按系统设置注入；后端解析见 `backend/chaoxing/config.py`（`_env_int`，JSON 值可被 env 覆盖）。

> ⚠️ **安全约束**: 仅白名单环境变量透传。`ARK_API_KEY`、`DOUBAO_TOKEN` 等凭据类环境变量被显式排除。

### 4.2 stdin 控制信号

主进程通过 stdin 向 Python 子进程发送控制命令。两类格式共用同一条 stdin 通道：

**(a) 明文控制信号**（逐行，大小写不敏感）：

| 信号 | 格式 | 说明 |
|------|------|------|
| `PAUSE` | `PAUSE\n` | 暂停执行（Python 在安全点调用 `check_signals()` 检测） |
| `RESUME` | `RESUME\n` | 恢复执行 |
| `STOP` | `STOP\n` | 优雅停止（设置 `SHUTDOWN_FLAG`，线程在安全点退出） |

**(b) JSON 控制命令**（逐行，以 `{` 开头的行按 JSON 解析）：

| `type` | 说明 |
|--------|------|
| `RESOLVE_TICKET` | 回传一个人工介入工单的处理结果（验证码答案 / 跳过） |

`RESOLVE_TICKET` payload —— 提交答案：

```json
{"type":"RESOLVE_TICKET","ticketId":"captcha_0_1719312000","accountId":0,"answer":"AB12"}
```

`RESOLVE_TICKET` payload —— 跳过此课程：

```json
{"type":"RESOLVE_TICKET","ticketId":"captcha_0_1719312000","accountId":0,"action":"skip"}
```

- 前端**只需发送 `accountId`**，不必知道后端文件名。后端按 `accountId` 路由，
  把 `answer`（或跳过哨兵 `__SKIP__`）写入对应账号的验证码答案文件，由内容处理器的
  兜底轮询循环读取并提交。
- `answer` 与 `action:"skip"` 二选一；缺字段 / 非法 JSON 后端容错（记 `warn` 日志，不崩溃、不中断任务）。
- `ticketId` 透传回去便于前端关联，后端当前按 `accountId` 路由（每账号同一时刻只有一个验证码工单）。

> ⚠️ **已废弃**：旧版基于本地文件标志位（`P`/`Q` 文件）的暂停/停止机制已移除。
> 所有控制信号（`PAUSE`/`RESUME`/`STOP`）与 `RESOLVE_TICKET` **统一走 stdin**。

### 4.3 stdout JSON-line 事件协议

Python 子进程通过 stdout 输出 **每行一个 JSON 对象**。主进程逐行解析并分发到对应的事件通道。

#### `PROGRESS` — 进度更新

```json
{
  "type": "PROGRESS",
  "jobId": "job_1719312000000_a1b2c3",
  "percent": 45,
  "message": "正在处理：高等数学 第3章"
}
```

**触发时机**: 完成任务步骤时实时推送。

---

#### `PHASE` — 阶段切换

```json
{
  "type": "PHASE",
  "jobId": "job_1719312000000_a1b2c3",
  "phase": "solve_quiz"
}
```

**phase 枚举值**: `idle` → `login` → `scan_courses` → `process_sections` → `solve_quiz` → `completed` / `paused` / `stopped` / `error`

---

#### `LOG` — 日志输出

```json
{
  "type": "LOG",
  "jobId": "job_1719312000000_a1b2c3",
  "level": "info",
  "message": "登录成功，账号：138****1234",
  "timestamp": "2026-06-25T12:00:00.000Z"
}
```

**level 枚举**: `debug` | `info` | `warn` | `error`

> **注意**: stderr 输出也会被包装为 `LOG` 事件（level=`error`, message 前缀 `[stderr]`）。
> 非 JSON 格式的 stdout 行也会被包装为 `LOG` 事件（level=`info`）。

---

#### `TICKET` — 工单通知

```json
{
  "type": "TICKET",
  "jobId": "job_1719312000000_a1b2c3",
  "ticket": {
    "id": "captcha_0_1719312000",
    "jobId": "job_1719312000000_a1b2c3",
    "type": "captcha",
    "accountId": 0,
    "title": "需要人工输入验证码",
    "message": "账号 0 在反爬验证码处受阻，AI 识别失败，请人工输入",
    "imageBase64": "data:image/png;base64,iVBORw0KGgo...",
    "options": ["输入验证码", "跳过此课程"],
    "resolved": false,
    "createdAt": "2026-06-25T12:00:05.000Z"
  }
}
```

**ticket.type 枚举**: `captcha` | `verification` | `warning` | `error`

**验证码人工介入链路**（已接通，`check_anti_spider()` 实际发射）：

1. 后端遇到反爬验证码且 AI（豆包 OCR）识别失败 → 进兜底循环**之前** emit 一次
   `resolved:false` 的工单，`imageBase64` 直接内嵌验证码图的 base64（不传路径，
   前端跨进程不共享文件系统），`accountId` 标明是哪个账号受阻。
2. 前端弹窗展示图片，用户输入答案或选择跳过 → 经 stdin 回传 `RESOLVE_TICKET`（见 §4.2）。
3. 后端兜底循环（5s 轮询，最多 10 分钟）读到答案后自动填入并提交。
4. **作废/完结**：后端在以下三种情况各再 emit 一条**同 `id`**、`resolved:true` 的工单，
   附 `resolution` 字段，前端据此关闭输入框：
   - `"resolution":"solved"` —— 已成功提交（答案文件或用户在 Chrome 窗口手动解出）。
   - `"resolution":"skipped"` —— 用户选择跳过此课程。
   - `"resolution":"timeout"` —— 10 分钟超时未解出。

> 验证码答案文件由**后端全权负责清理**（成功 / 跳过 / 超时三种都会删除答案文件与图片），
> 前端无脏数据风险。
>
> 注：登录阶段的验证码（`platform.captcha.solve_captcha()`）目前**没有**人工介入兜底，
> 仅 AI 自动识别；本链路只覆盖内容处理阶段的反爬验证码。

---

#### `RESULT` — 结果数据

```json
{
  "type": "RESULT",
  "jobId": "job_1719312000000_a1b2c3",
  "data": {
    "courseName": "高等数学",
    "quizStats": {
      "totalQuestions": 50,
      "correctAnswers": 48,
      "accuracy": 0.96
    }
  }
}
```

**data 字段**: 自由格式，由后端定义结构。

---

#### `ERROR` — 错误信息

```json
{
  "type": "ERROR",
  "jobId": "job_1719312000000_a1b2c3",
  "error": "登录失败：账号或密码错误",
  "stack": "Traceback (most recent call last):\n  ..."
}
```

**stack 字段**: 可选，仅在有 Python traceback 时提供。

---

#### `DONE` — 任务完成

```json
{
  "type": "DONE",
  "jobId": "job_1719312000000_a1b2c3"
}
```

**触发时机**: 所有课程处理完毕，正常退出。

### 4.4 生命周期管理

```
启动 → [PROGRESS/PHASE/LOG/TICKET 事件流] → DONE
                                           → ERROR → exit(code ≠ 0)
                                           → STOP 信号 → SIGTERM → SIGKILL

安全保护:
  - 2 小时硬超时: SIGTERM → 5s → SIGKILL
  - 停止流程: STOP 信号 → 5s SIGTERM → 8s SIGKILL
  - 崩溃检测: exit code ≠ 0 且未标记 completed/stopped → 视为 error
  - 应用退出流程: STOP 信号 → 轮询 10s（1s 间隔）→ taskkill /f /pid /t
  - Chromium 清理: 应用退出时 taskkill /f /im chromium.exe /t
```

### 4.5 非 JSON 行处理

对于无法解析为 JSON 的 stdout 行，包装为 LOG 事件:
```typescript
{
  type: 'LOG',
  jobId: 'main',
  level: 'info',
  message: '<原始行内容>',
  timestamp: '<当前时间 ISO>'
}
```

### 4.6 TypeScript 类型定义参考

```typescript
// 所有事件类型的联合
type PythonBridgeEvent =
  | PythonProgressEvent
  | PythonLogEvent
  | PythonPhaseEvent
  | PythonTicketEvent
  | PythonResultEvent
  | PythonErrorEvent
  | PythonDoneEvent

// 事件类型判别 (type guard)
const KNOWN_TYPES = ['PROGRESS', 'LOG', 'PHASE', 'TICKET', 'RESULT', 'ERROR', 'DONE']
```

---

### 4.7 余额查询子命令 (`python -m chaoxing.balance`)

查询火山引擎（豆包所属）账户的**现金余额**。这是一条**独立的 CLI 命令**，与任务流程
(`chaoxing.api`) 完全解耦：它**不接受** `--job-id/--accounts/--mode` 参数，不发任务事件流，
只向 stdout 输出**一行 JSON** 后退出。

> **前端已接入**（见 §9.2）：`balance:query` IPC 通道 + `balance.handler.ts` + `getBalance()`
> 全链路实现，`DashboardView` 顶部「💳」卡片展示实时余额。Mock 模式返回模拟值，无需后端即可看 UI。

**启动方式（重要）**：余额查询依赖 `volcengine-python-sdk`，该 SDK 预装在专用 conda 环境 `chaoxing-backend`。
Electron 主进程解析余额查询解释器的顺序：

1. `CHAOXING_BALANCE_PYTHON` 环境变量（显式覆盖，最优先）；
2. `Settings.pythonPath`（默认已指向 `chaoxing-backend` 环境的 `python.exe`；若配置的是不存在的绝对路径会自动跳过）；
3. `PATH` 上的 `python`。

主进程会在控制台打印实际选用的解释器，便于排查「SDK 未安装 / 解释器不存在」类问题。手工验证：

```bash
# 推荐：专用 conda 环境（可用环境变量 CHAOXING_BALANCE_PYTHON 覆盖）
conda activate chaoxing-backend
python -m chaoxing.balance
```

**成功输出**（stdout 单行，exit code 0）：

```json
{
  "type": "BALANCE",
  "provider": "doubao",
  "accountId": 2100123456,
  "availableBalance": "100.50",
  "cashBalance": "80.25",
  "creditLimit": "0.00",
  "arrearsBalance": "0.00",
  "freezeAmount": "5.00",
  "currency": "CNY",
  "checkedAt": "2026-06-26T08:30:00.000Z"
}
```

| 字段 | 类型 | 含义 |
|---|---|---|
| `accountId` | number | 火山引擎账户 ID |
| `availableBalance` | string | 可用余额 |
| `cashBalance` | string | 现金余额 |
| `creditLimit` | string | 信用额度 |
| `arrearsBalance` | string | 欠费金额 |
| `freezeAmount` | string | 冻结金额 |
| `currency` | string | 币种，固定 `"CNY"` |
| `checkedAt` | string | 查询时刻 ISO 8601 (UTC, `Z` 结尾) |

> 金额字段全部为 **string**（保留账单 API 的小数精度，不做 number 转换）。渲染侧 `Balance` 类型
> 仅把 `checkedAt` 由 ISO 解析为 epoch ms，其余字段直通。

**失败输出**（stdout 单行，exit code 1）：

```json
{ "type": "ERROR", "error": "<错误信息>", "detail": "<异常类型名>" }
```

常见 `detail`：`ConfigError`（凭证文件缺失 / AK/SK 解析失败）、
`AIBackendError`（SDK 未安装时提示改用 `chaoxing-backend` 解释器，或 API 调用失败）。

> stdout 严格单行 JSON（前端可直接 `JSON.parse`）；调试信息只走 stderr。
> Electron 侧 `balance.handler.ts` 取**最后一条非空 stdout 行**解析，并设 30s 超时；
> 找不到解释器（ENOENT）时返回中文提示，建议设 `CHAOXING_BALANCE_PYTHON`。

**凭证文件** `data/passwords/volc_billing.txt`（已被 `.gitignore` 忽略，由用户手动放置）：

```
export VOLC_ACCESS_KEY="AK..."
export VOLC_SECRET_KEY="SK..."
region="cn-north-1"          # 可选，默认 cn-north-1
```

> 文件支持 **UTF-8 或 ANSI/GBK** 编码（兼容中文 Windows 记事本默认保存方式）。
>
> 前端展示：失败时 Dashboard 卡片显示简短原因（悬停可看完整错误信息），**点击卡片可重新查询**，
> 无需重启应用。
>
> 注意：这套 AK/SK 走的是火山引擎**账单 OpenAPI**（V4 HMAC 签名），与豆包推理用的
> `ARK_API_KEY`（`data/passwords/doubao.txt`）是**两套独立凭证**，不可混用。
>
> 安全：`balance.handler.ts` 沿用 PythonBridge 的环境变量白名单策略，不向子进程透传
> `ARK_API_KEY` 等凭据；凭证只从 `data/passwords/volc_billing.txt` 读取。

---

## 5. 类型映射表

前端类型 (`types.ts`) 与 Electron IPC 类型 (`electron/types.ts`) 之间的映射关系，由 `ElectronApiClient` (`ipcClient.ts`) 处理。

### 5.1 账号类型映射

| 前端字段 | Electron 字段 | 方向 | 映射逻辑 |
|---------|--------------|------|---------|
| `Account.id: string` | `Account.id: number` | 双向 | `String(id)` ↔ `parseInt(id, 10)` |
| `Account.displayName` | `Account.nickname \|\| Account.username` | 单向 | `nickname ?? username` |
| `Account.status` | `Account.enabled` | 单向 | `enabled → 'online' : 'offline'` |
| `Account.avatar` | `Account.avatar` | 直通 | 直接映射 |
| `Account.lastChecked` | 无 | 仅前端 | `Date.now()` (Mock 模式) |
| `Account.errorMessage` | 无 | 仅前端 | Mock 模式中为固定文案 |

### 5.2 模式映射

| 前端 `ModeType` | 后端 mode 字符串 | 说明 |
|----------------|-----------------|------|
| `'course-scan'` | `'scan_only'` | 仅扫描课程结构 |
| `'section-scan'` | `'scan_only'` | 仅扫描章节 |
| `'dry-run'` | `'scan_only'` | 模拟运行（不实际执行） |
| `'batch-exec'` | `'solve_only'` | 仅刷题或仅内容 |
| `'full-auto'` | `'full'` | 全自动处理 |
| `'single-exec'` | `'full'` | 单任务执行 |

> **反向映射有损** (`mapBackMode`，仅在 `getJobStatus` 缺少缓存时作回退)：`scan_only → course-scan`、`solve_only → batch-exec`、`full → full-auto`。`section-scan`/`dry-run`/`single-exec` 无法回程还原。正常情况下 `getJobStatus` 优先使用 `startJob` 缓存的原始 `mode`，不触发反向映射。

### 5.3 设置映射

| 前端 `Settings` | Electron `Settings` | 映射逻辑 |
|----------------|-------------------|---------|
| `maxConcurrency` | `maxWorkers` | 直接映射 |
| `quizSolver` | `quizSolver` | `mapQuizSolver`：后端任意值统一归一化为 `'doubao'`（DeepSeek 已移除） |
| `debugMode` | `logLevel` | `true → 'debug'`, `false → 'info'` |
| `quizRetryCount` / `targetAccuracy` | `quizRetryCount` / `targetAccuracy` | 经 `CHAOXING_RETRY_*` 环境变量注入后端 |
| 五项超时（page/snapshot/click/video/quiz） | 同名 | 经 `CHAOXING_TIMEOUT_*` 环境变量注入后端 |
| `logRetention` | `logRetention` | 主进程启动时清理 `data/logs` |
| `notifications` | `notifications` | 主进程任务完成/异常桌面通知 |
| `accountsFilePath` / `concurrencyTarget` / `perAccountEstimateGB` / `pythonPath` | 同名 | 直接映射（`pythonPath` 空 = PATH 上的 python） |
| `theme` / `language` | 无 | 仅前端（CSS 自定义属性 / 硬编码 `'zh-CN'`） |

> **注意**：`videoSpeed` / `sectionDelay` / `autoResolveCaptcha` 等死开关已从类型与设置页移除；
> `setSettings` 回写时按上表发送可同步字段，其余前端字段（主题/语言）不持久化到后端。

### 5.4 工单映射

| 前端 `Ticket.severity` | Electron `Ticket.type` | 映射逻辑 |
|----------------------|----------------------|---------|
| `'critical'` | `'error'` | `error → critical` |
| `'warning'` | `'warning'` | 直通 |
| `'info'` | `'captcha'` / `'verification'` | 其余 → `info` |

### 5.5 JobHandle 构造

前端 `JobHandle` 是前端专用类型，Electron IPC 层返回 `JobStatus`。`ElectronApiClient` 负责构造：
- `phases`: 优先复用 `startJob` 时缓存的 `currentHandle.phases`；缺失时根据 `mode` 从 `MODES` 常量（`constants.ts`）生成
- `lanes`: 来自后端 `JobStatus.lanes`（逐 lane 状态、进度、当前任务/阶段、错误信息），账号 ID `number → String`
- `objective`/`strategy`/`createdAt`: 取自缓存的 `currentHandle`（后端不携带）
- `progress`/`phaseIndex`: 从 `JobStatus` 映射
- 时间戳: ISO 字符串 → `Date.getTime()`，后端 `finishedAt` → 前端 `completedAt`

---

## 6. Mock 开发模式

当 `window.electronAPI` 不可用时（纯浏览器环境），`createApiClient()` 自动返回 `MockApiClient`。

### Mock 特性

- **完整模拟**: 所有 invoke 方法 + 8 个事件订阅均有 mock 实现
- **逐账号控制**: Mock 模式真实支持选中 lane 的 暂停/恢复/停止（Electron 真子集会抛错），便于在无后端时验证多账号交互
- **数据生成** (`mockData.ts`):
  - 8 个中国大学账号（含 1 个异常状态）
  - 26 门课程名称池（每账号 4-10 门课）
  - 8 种工单模板（验证码、进度异常、视频速度等）
- **任务模拟**: `setTimeout` tick 循环（800-2200ms 随机间隔），自动推进阶段，发射事件
- **配置持久化**: 写入 `localStorage` key `'chaoxing-assistant-settings'`
- **零依赖**: 不发起任何网络请求

### 开发命令

```bash
cd frontend
npm run dev          # Web 模式 (Mock)，端口 5173
npm run dev:electron # Electron 模式 (真实 IPC + Python)
npm run typecheck    # 类型检查（vue-tsc 2.x；渲染进程 + Node 侧分两次）
```

### 后端开发对接

后端开发者在对接时只需关注 **Layer 3 (Python 子进程协议)**：
1. 入口接收 `--job-id`, `--accounts`, `--mode`, `--courses`, `--max-concurrent`, `--budget-gb`, `--system-limit-gb`, `--per-account-estimate-gb` 参数
2. stdout 按 JSON-line 格式输出 8 种事件类型（含 `MEMORY`）
3. stdin 接收 `PAUSE` / `RESUME` / `STOP` 控制信号
4. 遵守 2 小时超时和优雅停止协议

前端 Mock 模式可独立运行，无需后端即可开发和调试 UI。

---

## 7. 安全规范

### 环境变量隔离

PythonBridge 只透传白名单环境变量，防止凭据泄漏：

```
白名单: PATH, SYSTEMROOT, SYSTEMDRIVE, TEMP, TMP,
        USERPROFILE, HOMEDRIVE, HOMEPATH,
        PYTHONPATH, PYTHONHOME,
        CHAOXING_WORKSPACE, CHAOXING_DATA_DIR, CHAOXING_HEADED,
        CHAOXING_ACCOUNTS_FILE, CHAOXING_TIMEOUT_*, CHAOXING_RETRY_*
强制设置: PYTHONUNBUFFERED=1
```

**禁止透传**: `ARK_API_KEY`, `DOUBAO_TOKEN`, 及其他自定义环境变量。

### 输入校验

- `accountIds`: 必须为正整数数组，最大 50 个（接受 string → parseInt 转换）
- `courseIds`: 字符串数组
- `mode`: 限制为 `full` / `scan_only` / `solve_only`
- **RAM 安全检查**: 按当前机器内存与 CPU 动态计算并发上限，运行中实时采样收紧
- 所有 IPC 调用: 500ms 速率限制

### 进程安全

- 2 小时硬超时防止僵尸进程
- 应用退出时主动 kill Python 进程树（STOP → SIGTERM → SIGKILL → taskkill）
- Windows: 退出时清理孤儿 Chromium 进程 (`taskkill /f /im chromium.exe /t`)
- GPU 禁用: Electron 主进程启动时 `--disable-gpu` + `--disable-gpu-compositing`（防止 NVIDIA 驱动不稳定）

### 渲染进程安全

- `contextIsolation: true` — 渲染进程无法直接访问 Node.js API
- `nodeIntegration: false` — 禁止渲染进程使用 Node.js
- `sandbox: true` — 启用 Electron 沙箱
- **CSP**: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:`

---

## 8. 错误处理

### 错误传播层级

```
Level 1 — IPC 层: 通道未注册 / 参数校验失败 / 速率限制 / RAM 安全检查
Level 2 — PythonBridge 层: 进程启动失败 / stdin 写入失败 / JSON 解析异常
Level 3 — Python 层: 登录失败 / 网络超时 / AI API 错误 / 浏览器崩溃
```

### 错误恢复策略

| 层级 | 错误类型 | 恢复策略 |
|------|---------|---------|
| IPC 层 | 速率限制 | 前端等待 500ms 后重试 |
| IPC 层 | 参数校验失败 | 前端提示用户修正输入 |
| IPC 层 | RAM 安全检查 | 弹窗显示详细内存建议，用户减少账号或关闭应用 |
| Bridge 层 | 进程启动失败 | 报告错误，等待用户手动重试 |
| Bridge 层 | 进程崩溃 (exit code ≠ 0) | 自动标记 job 为 error，清理资源 |
| Python 层 | 可恢复错误 | 通过 `ERROR` 事件推送（`recoverable: true`），Python 内部重试 |
| Python 层 | 不可恢复错误 | 通过 `ERROR` 事件推送（`recoverable: false`），Python 退出 |

### 超时策略

| 超时 | 时间 | 行为 |
|------|------|------|
| Python 进程总时长 | 2 小时 | SIGTERM → 5s → SIGKILL |
| 停止等待 | 5s + 8s | STOP 信号 → SIGTERM → SIGKILL |
| 应用退出等待 | 10s (轮询, 1s 间隔) | 最后手段: `taskkill /f /pid /t` |

### 前端 Store 错误处理模式

所有异步 Store action 使用统一的 try/catch 模式：
```typescript
try {
  loading.value = true
  error.value = null
  const result = await api.someMethod(...)
  // 更新状态
} catch (e: any) {
  error.value = e?.message ?? '操作失败'
} finally {
  loading.value = false
}
```

- `startJob`: catch 中额外停止计时器和事件监听（防止资源泄漏）
- `pauseJob`/`resumeJob`/`stopJob`: catch 中仅设置 error（job 可能仍在运行）
- `setSettings`: 防抖同步的 catch 为静默忽略（后端不可用时不影响前端）
- `loadFromStorage`: JSON 解析异常时静默回退到默认设置

---

## 9. 已知问题与待办

### 9.1 后端待接入 (TODO)

| 模块 | 文件 | 状态 |
|------|------|------|
| 课程扫描/列表 | `electron/ipc/course.handler.ts` | ✅ 已接入 `python -m chaoxing.courses`（读取发现状态） |
| 账号列表 | `electron/ipc/accounts.handler.ts` | ✅ 已接入 `python -m chaoxing.accounts` |
| 账号状态 | `electron/ipc/status.handler.ts` | ⚠️ 仍为桩数据（仅 account 1，UI 未调用） |
| 工单存储 | `electron/ipc/status.handler.ts` | 内存数组，无持久化 |

### 9.2 已实现 / 已修复

**v1.3 新增**

| 类别 | 内容 | 文件 |
|------|------|------|
| 功能 | 余额查询全链路（`balance:query` 通道 + Anaconda spawn + `getBalance` + Dashboard 卡片），替换硬编码 `¥500` | `electron/ipc/balance.handler.ts`、`preload.ts`、`ipcClient.ts`、`mockClient.ts`、`DashboardView.vue` |

**v1.2 修复**

| 原严重度 | 问题 | 修复 |
|--------|------|------|
| 高 | `AccountLane.status` 不含 `'stopped'`，用 `as any` 绕过 | 类型联合已加入 `'stopped'`/`'paused'`，移除 `as any` |
| 高 | Lane 计时器 resume 后从 0 重新计数，暂停期间时间丢失 | `execution.store.ts` 用 `activeElapsedBase` + `stopLaneTimer` 落账累计时长 |
| 中 | 按账号 `pauseJob`/`stopJob` 在 IPC 层未实现 | 已接入 `*_SELECTED` 通道；Electron 真子集显式抛错，Mock 真实支持（见第 7 节） |
| 中 | `course.store.ts` 多账号扫描所有课程存于同一 key | 改为 `coursesByAccount` 按账号 ID 分桶缓存 |
| 低 | `ElectronApiClient.dispose()` 未被 store 调用 | `unregisterEventListeners()` 现调用 `api.dispose()` |

### 9.3 仍存在的已知问题

| 严重度 | 问题 | 位置 |
|--------|------|------|
| 中 | 前端设置无法从后端同步（单向流: 前端→后端），多实例时可能不一致 | `settings.store.ts` |
| 中 | `DONE` 事件不含完成统计，Electron 路径 `CompletionEvent.results` 全为 0、`success` 恒为 true | `ipcClient.ts` (onCompleted) |
| 中 | `campaign.store.ts` 的 `forecast` 计算忽略 `strategy` 和 `mode`（仅用 objective + 课程/账号数） | `campaign.store.ts` |
| 低 | `accounts:status` 仍为桩数据（仅 account 1） | `status.handler.ts` |

### 9.4 工具链说明

- 类型检查已从 `vue-tsc 1.8` 升级到 `vue-tsc 2.x`：旧版在 Node 24 下因补丁 TS 内部字符串失败而崩溃 (`Search string not found: "/supportedTSExtensions = .*(?=;)/"`)，2.x 走正式 API，兼容 Node 24 + TypeScript 5.9。
- `tsconfig` 拆分为渲染进程 (`tsconfig.json`，DOM lib，`src/**`) 与 Node 侧 (`tsconfig.node.json`，node types，`vite.config.ts` + `electron/**`) 两份非重叠配置，`typecheck` 分两次执行，避免 DOM/Node 类型冲突与 composite 项目引用错误 (TS6305/TS6310)。

---

## 附录 A: 文件索引

| 文件 | 内容 |
|------|------|
| `frontend/src/shared/lib/types.ts` | 前端类型定义 + `ChaoxingApi` 接口 |
| `frontend/src/shared/lib/apiClient.ts` | API 客户端工厂（环境检测） |
| `frontend/src/shared/lib/ipcClient.ts` | `ElectronApiClient` 实现（类型映射） |
| `frontend/src/shared/lib/mockClient.ts` | `MockApiClient` 实现（含模拟任务循环） |
| `frontend/src/shared/lib/mockData.ts` | Mock 数据生成器 |
| `frontend/src/shared/lib/constants.ts` | OBJECTIVES / STRATEGIES / MODES / DEFAULT_SETTINGS |
| `frontend/src/shared/lib/designTokens.ts` | 浅色/深色主题 CSS 自定义属性 |
| `frontend/src/shared/lib/formatDuration.ts` | 毫秒 → "Xh Ym Zs" 格式化 |
| `frontend/src/app/stores/execution.store.ts` | 任务执行 Store（事件监听、计时器管理、lane 操作） |
| `frontend/src/app/stores/account.store.ts` | 账号 Store（列表、选择） |
| `frontend/src/app/stores/course.store.ts` | 课程 Store（按账号缓存、扫描） |
| `frontend/src/app/stores/campaign.store.ts` | 任务配置 Store（目标/策略/模式 + 预估） |
| `frontend/src/app/stores/captcha.store.ts` | 验证码队列 Store（人工介入弹窗） |
| `frontend/src/app/stores/memory.store.ts` | 内存计划 / MEMORY 事件 Store（预算仪表） |
| `frontend/src/app/stores/settings.store.ts` | 设置 Store（localStorage + 防抖同步） |
| `frontend/src/app/stores/attention.store.ts` | 工单 Store（列表、筛选、解决） |
| `frontend/src/app/stores/log.store.ts` | 日志 Store（缓冲 500 条、级别计数） |
| `frontend/src/views/CourseAtlasView.vue` | 课程总览页（账号选择、课程网格、任务启动） |
| `frontend/src/views/ExecutionStudioView.vue` | 执行监控页（阶段 Stepper、Lane 卡片、统计数据） |
| `frontend/src/views/DashboardView.vue` | 仪表盘（统计卡片、账号矩阵、资源监控、时间线） |
| `frontend/src/views/AttentionQueueView.vue` | 关注队列（工单列表、筛选、预测面板、日志 Feed） |
| `frontend/src/views/SettingsView.vue` | 设置页（AI/浏览器/账号/主题配置） |
| `frontend/src/app/App.vue` | 根布局（AppSidebar + router-view + LogConsole） |
| `frontend/src/router/index.ts` | 路由配置（5 条 hash 路由 + lazy load） |
| `frontend/electron/types.ts` | Electron IPC 类型 + `IPC_CHANNELS` 常量 |
| `frontend/electron/preload.ts` | Context bridge (`window.electronAPI`) |
| `frontend/electron/main.ts` | Electron 主进程（窗口创建、IPC 注册、生命周期） |
| `frontend/electron/ipc/job.handler.ts` | 任务 IPC 处理器（含 RAM 检查、速率限制） |
| `frontend/electron/ipc/course.handler.ts` | 课程 IPC 处理器（读取 Python 发现状态，真实后端） |
| `frontend/electron/ipc/status.handler.ts` | 状态/设置/工单 IPC 处理器 |
| `frontend/electron/ipc/balance.handler.ts` | 余额查询 IPC 处理器（spawn Anaconda 跑 `chaoxing.balance`，§4.7） |
| `frontend/electron/ipc/accounts.handler.ts` | 账号增删改 IPC（`chaoxing.accounts` 子命令） |
| `frontend/electron/ipc/ai.handler.ts` | AI 配置读写与方舟连通性测试 |
| `frontend/electron/ipc/system.handler.ts` | `system:resources` / `memory:plan` |
| `frontend/electron/ipc/dialog.handler.ts` | 文件选择器 |
| `frontend/electron/python/pythonBridge.ts` | Python 子进程桥接器（spawn、事件分发、生命周期） |

## 附录 B: 后端接入检查清单

后端（Python 脚本）开发者接入时应确保：

- [ ] 入口脚本接收 `--job-id`, `--accounts`, `--mode`, `--courses`, `--grade-only`, `--content-only`, `--max-concurrent`, `--budget-gb`, `--system-limit-gb`, `--per-account-estimate-gb` 命令行参数
- [ ] stdout 所有输出为 JSON-line 格式（每行一个 JSON 对象）
- [x] 每个 JSON 对象包含 `type` 字段（`PROGRESS` / `PHASE` / `LOG` / `TICKET` / `RESULT` / `ERROR` / `MEMORY` / `DONE`）
- [ ] `PROGRESS` 事件包含 `jobId`, `percent` (0-100), `message`
- [ ] `PHASE` 事件在阶段切换时发送，`phase` 字段为有效枚举值 (`idle` → `login` → `scan_courses` → `process_sections` → `solve_quiz` → `completed`)
- [x] `TICKET` 事件在验证码 AI 识别失败时发送（内嵌 `imageBase64`），并在 solved/skipped/timeout 时回发 `resolved:true` 作废工单
- [ ] `DONE` 事件在全部任务完成后发送（正常退出）
- [ ] `ERROR` 事件在捕获异常时发送，区分 `recoverable` 标志
- [x] stdin 支持 `PAUSE`, `RESUME`, `STOP` 控制信号 + `RESOLVE_TICKET` JSON 命令（逐行读取）
- [ ] 在安全点（导航后、批次间、每题后）调用暂停检查
- [ ] 2 小时内完成或优雅退出（遵守硬超时）
- [ ] 非 JSON 日志输出到 stderr 而非 stdout
- [ ] 遵守环境变量白名单，通过配置文件或安全存储读取 API Key 等凭据
- [x] 余额查询独立子命令 `python -m chaoxing.balance`（见 §4.7）：单行 `BALANCE` JSON / 失败 `ERROR` + exit 1；须用装有 `volcengine-python-sdk` 的解释器（`chaoxing-backend`）拉起；凭证读 `data/passwords/volc_billing.txt`（与 `ARK_API_KEY` 分离）

## 附录 C: 前端 Store 通信图

```
App.vue (onMounted)
  ├── accountStore.fetchAccounts()
  └── attentionStore.fetchTickets()

executionStore (唯一有跨 Store 依赖的 Store)
  ├── 调用: logStore.addLog()       [onLog 回调]
  └── 调用: attentionStore.addTicket()  [onTicket 回调]

DashboardView — 使用 5 个 Store: Account, Attention, Log, Course, Execution
ExecutionStudioView — 使用 3 个 Store: Execution, Account, Campaign
CourseAtlasView — 使用 4 个 Store: Account, Course, Execution, Settings
SettingsView — 使用 3 个 Store: Settings, Account, Course
AttentionQueueView — 使用 3 个 Store: Attention, Campaign, Log

所有其他 6 个 Store (Account, Course, Campaign, Settings, Attention, Log)
  — 无跨 Store 导入，仅被 executionStore 依赖
```

---

## 10. 2026-08-13：内存感知并发协议变更

### 10.1 新 CLI 参数（`python -m chaoxing.api`）

```text
--max-concurrent INT            动态信号量大小（Electron 按内存/CPU 计划计算）
--budget-gb FLOAT               项目内存预算（GB）
--system-limit-gb FLOAT         系统已用内存急停阈值（基线+预算+1GB 余量）
--per-account-estimate-gb FLOAT 初始单 Chrome 实例估算（默认 0.7GB）
```

`--chromium-flags` 已移除：省内存参数改由工作区 `backend/.playwright/cli.config.json`
的 `browser.launchOptions.args` 承载（打包时由 `ensureWorkspaceSeeded` 复制）。

### 10.2 协议事件

- `PROGRESS` 新增可选 `accountId`（整数）与 `laneStatus`（`queued` / `running` / `error`）。
- 新增 `MEMORY` 事件：

```json
{"type":"MEMORY","jobId":"...","budgetGB":12.9,"projectChromeGB":1.1,
 "perAccountAvgGB":0.55,"remainingCount":17,"level":"info","message":"..."}
```

### 10.3 账号与 AI 子命令

- `python -m chaoxing.accounts list|add|edit|remove`：单行 JSON；显式编号、
  删除不重排、新增复用最小空位、原子写入 + `.bak` 备份 + 读回校验。
- `python -m chaoxing.ai_config test`：读 `doubao.txt` 调方舟 `/models`，
  单行 JSON（key 不进命令行）。
- 环境变量 `CHAOXING_ACCOUNTS_FILE` 覆盖账号文件路径（Electron 全局设置下发）。

### 10.4 内存模型

- 启动前：`预算 = (总内存 − 基线) × 0.75`，`cpuCap = max(2, 线程数 − 2)`，
  `最大并发 = min(⌊预算/0.7⌋, cpuCap)`。
- 运行中：后端每 5 秒采样项目 Chrome 进程树，实测 EWMA 收紧开闸；
  系统总占用逼近上限且项目自身为主因且连续两次不回落时急停。
