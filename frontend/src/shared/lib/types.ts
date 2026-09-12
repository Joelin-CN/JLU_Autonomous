// ── Shared TypeScript Interfaces ──

export type ObjectiveType = 'catchup' | 'exam-sprint' | 'maintenance' | 'custom'
export type StrategyType = 'balanced' | 'careful' | 'overnight' | 'surgical'
export type ModeType = 'course-scan' | 'section-scan' | 'single-exec' | 'batch-exec' | 'full-auto' | 'dry-run'
// Doubao API is the sole AI backend (chaoxing_config.json -> ai.provider:
// "doubao-api"). The renderer mirrors that — other providers were removed.
export type AIProvider = 'doubao'

export type AccountStatus = 'online' | 'offline' | 'error' | 'checking'

/** 课程平台标识。 */
export type Platform = 'chaoxing' | 'zhihuishu'

export interface Account {
  id: string
  username: string
  displayName: string
  website?: string
  status: AccountStatus
  avatar?: string
  lastChecked?: number
  errorMessage?: string
  platform?: Platform
}

export interface Course {
  id: string
  name: string
  teacher?: string
  coverUrl?: string
  progress: number // 0–100
  totalSections: number
  completedSections: number
  sections?: SectionDef[]
  accountId?: string
  url?: string
  platform?: Platform
}

export interface SectionDef {
  id: string
  name: string
  parentId?: string
  children?: SectionDef[]
  completed: boolean
  type?: 'chapter' | 'section' | 'quiz' | 'video' | 'doc'
  duration?: number // estimated seconds
}

export interface Objective {
  key: ObjectiveType
  label: string
  description: string
  icon?: string
}

export interface Strategy {
  key: StrategyType
  label: string
  description: string
}

export type ExecutionStatus = 'idle' | 'running' | 'paused' | 'completed' | 'error' | 'stopped'
export type JobStatus = ExecutionStatus

export interface RuntimePhase {
  name: string
  status: 'pending' | 'running' | 'completed' | 'error' | 'stopped'
  progress: number // 0–100
  message?: string
}

export interface AccountLane {
  accountId: string
  status: 'pending' | 'queued' | 'running' | 'completed' | 'error' | 'paused' | 'stopped'
  progress: number
  currentTask?: string
  currentPhase?: string
  startedAt?: number
  errorMessage?: string
}

export interface JobHandle {
  jobId: string
  status: JobStatus
  /** 本次任务所属平台（startJob 时由渲染层注入，用于执行页徽标回显）。 */
  platform?: Platform
  createdAt: number
  startedAt?: number
  completedAt?: number
  objective: ObjectiveType
  strategy: StrategyType
  mode: ModeType
  courseCount: number
  accountCount: number
  progress: number // 0–100
  phaseIndex: number
  phases: RuntimePhase[]
  lanes: AccountLane[]
  memoryPlan?: MemoryPlan
}

export interface MemoryPlan {
  totalGB: number
  baselineGB: number
  budgetGB: number
  cpuCap: number
  memMax: number
  maxConcurrent: number
  systemLimitGB: number
  perAccountEstimateGB: number
}

export interface MemoryEvent {
  type: 'MEMORY'
  jobId?: string
  budgetGB: number
  projectChromeGB: number
  perAccountAvgGB: number
  remainingCount: number
  level: 'info' | 'critical'
  message: string
}

export interface AiStatus {
  provider: string
  label: string
  configured: boolean
  model: string
  keyTail: string
}

export interface AiTestResult {
  ok: boolean
  reason?: string
  models?: number
}

export interface StartJobPayload {
  platform?: Platform
  objective: ObjectiveType
  strategy: StrategyType
  mode: ModeType
  courses: string[] // course IDs
  accounts: string[] // account IDs
  options?: Record<string, unknown>
}

export interface JobControlPayload {
  jobId: string
  accountIds?: string[]
}

export interface ProgressEvent {
  jobId: string
  phase: string
  phaseIndex: number
  percent: number
  message: string
  timestamp: number
  laneId?: string
}

export interface PhaseChangeEvent {
  jobId: string
  fromPhase: string
  toPhase: string
  phaseIndex: number
  timestamp: number
}

export interface CompletionEvent {
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

export interface ErrorEvent {
  jobId: string
  error: string
  phase: string
  recoverable: boolean
  timestamp: number
}

export type TicketSeverity = 'info' | 'warning' | 'critical'

/** 工单交互形态（渲染层判别值，由 ipcClient 按后端字段组合推断，
 *  见 mapElectronTicket；后端后续可发显式 kind 字段消除启发式）：
 *  - captcha：输入型 —— 验证码图片 + 文本输入（超星密码登录验证码）
 *  - qrcode：扫码型 —— 二维码图片 + 倒计时，扫码后后端自动 resolved
 *    （智慧树扫码登录，imageBase64 + timeoutSeconds）
 *  - hint：提示型 —— 纯文字指引（智慧树滑块：去浏览器窗口手动拖拽） */
export type TicketKind = 'captcha' | 'qrcode' | 'hint'

export interface Ticket {
  id: string
  title: string
  message: string
  severity: TicketSeverity
  courseId?: string
  accountId?: string
  resolved: boolean
  resolvedAt?: number
  resolution?: string
  createdAt: number
  /** 工单交互形态（判别见 TicketKind）；undefined = 被动工单（关注队列）。 */
  kind?: TicketKind
  /** 工单截图 / 二维码，data URI（e.g. "data:image/png;base64,..."）。 */
  imageBase64?: string
  /** 后端给出的等待上限（秒）。扫码型工单自带；渲染层倒计时优先读它，
   *  兜底 CAPTCHA_TIMEOUT_MS。 */
  timeoutSeconds?: number
  /** 工单来源平台（electron 层按当前任务平台注入，后端 TICKET 事件本身不携带）。 */
  platform?: Platform
  /** Action labels offered by the backend, e.g. ["输入验证码", "跳过此课程"]. */
  options?: string[]
  /** Frontend-only: set by captchaStore when this captcha is re-emitted after a
   *  wrong answer (same id, refreshed image). Not sent over the wire. */
  isRetry?: boolean
}

export interface Settings {
  theme: 'light' | 'dark'
  language: string
  maxConcurrency: number
  quizSolver: AIProvider
  quizRetryCount: number
  logRetention: number // days
  notifications: boolean
  debugMode: boolean
  headless: boolean // run browser in background (no visible window)
  targetAccuracy: number // 60-100, default 100
  /** 账号凭据文件路径，按平台各一份。后端 settings 只有单值槽位
   *  （chaoxing 语义）；zhihuishu 的路径仅保存在渲染层 localStorage，
   *  由渲染层调用账号 API 时通过 payload.accountsFile 生效。 */
  accountsFilePaths: Record<Platform, string>
  concurrencyTarget: number | null
  perAccountEstimateGB: number
  pythonPath: string
  pageLoadTimeout: number
  snapshotTimeout: number
  clickTimeout: number
  videoWatchTimeout: number
  quizAnswerTimeout: number
  sectionCompleteTimeout: number
  /** Persisted 模拟运行 guard: solve/fill/grade but never submit. */
  dryRun: boolean
}

export interface LogLine {
  id: number
  timestamp: number
  time: string
  level: 'info' | 'warn' | 'error' | 'debug'
  message: string
  source?: string
}

/** Volcengine (Doubao) cash-balance snapshot from `python -m chaoxing.balance`.
 *  Monetary fields are strings to preserve the billing API's decimal precision. */
export interface Balance {
  provider: string
  accountId: number
  availableBalance: string
  cashBalance: string
  creditLimit: string
  arrearsBalance: string
  freezeAmount: string
  currency: string
  checkedAt: number          // epoch ms (ISO `checkedAt` parsed on the way in)
}

/** Live system-resource snapshot for the dashboard panel. Sourced from Node's
 *  `os` module in the Electron main process (mocked in browser mode). */
export interface SystemResources {
  ram: { used: number; total: number; free: number; pct: number }
  cpu: { pct: number; cores: number }
  uptimeSeconds: number
}

/* ── API Interface ── */

/**
 * 渲染层 API 客户端接口（Electron / Mock 双实现）。
 * 平台差异通过 platform 参数表达；通道名与 NDJSON 协议见 electron/types.ts。
 */
export interface AppApi {
  startJob(payload: StartJobPayload): Promise<JobHandle>
  pauseJob(jobId: string, accountIds?: string[]): Promise<void>
  resumeJob(jobId: string): Promise<void>
  stopJob(jobId: string, accountIds?: string[]): Promise<void>
  pauseSelected(jobId: string, accountIds: string[]): Promise<void>
  resumeSelected(jobId: string, accountIds: string[]): Promise<void>
  stopSelected(jobId: string, accountIds: string[]): Promise<void>
  getJobStatus(jobId: string): Promise<JobHandle>
  scanCourses(accountIds?: string[], platform?: Platform): Promise<Course[]>
  getCourses(accountId?: string, platform?: Platform): Promise<Course[]>
  getAccounts(platform?: Platform): Promise<Account[]>
  getAccountStatus(accountId: string): Promise<Account>
  getSettings(): Promise<Settings>
  setSettings(settings: Settings): Promise<void>
  getTickets(): Promise<Ticket[]>
  resolveTicket(ticketId: string, resolution: string): Promise<void>
  /** Send a human's captcha answer (or skip) back to the running backend. */
  resolveCaptcha(payload: {
    ticketId: string
    accountId: number
    answer?: string
    action?: 'skip'
  }): Promise<void>
  /** Query the Volcengine (Doubao) cash balance. Decoupled from the job stream;
   *  spawns the chaoxing-backend interpreter on the Electron side. */
  getBalance(provider?: 'doubao' | 'deepseek'): Promise<Balance>
  /** Validate a candidate pythonPath (existence + >= 3.10); null reason = ok. */
  validatePython(pythonPath: string): Promise<{ reason: string | null }>
  /** Live system resources (RAM/CPU/uptime) for the dashboard panel. */
  getSystemResources(): Promise<SystemResources>
  getMemoryPlan(): Promise<MemoryPlan>
  onProgress(cb: (e: ProgressEvent) => void): () => void
  onPhaseChange(cb: (e: PhaseChangeEvent) => void): () => void
  onLog(cb: (line: { level: string; message: string; timestamp: number }) => void): () => void
  onTicket(cb: (ticket: Ticket) => void): () => void
  onCompleted(cb: (e: CompletionEvent) => void): () => void
  onError(cb: (e: ErrorEvent) => void): () => void
  onResult?(cb: (data: unknown) => void): () => void
  onMemory(cb: (e: MemoryEvent) => void): () => void
  getAiStatus(): Promise<AiStatus>
  setAiConfig(payload: { provider?: string; apiKey?: string; model: string }): Promise<void>
  testAi(provider?: string): Promise<AiTestResult>
  addAccount(payload: { account: string; password: string; website?: string; platform?: Platform; accountsFile?: string }): Promise<void>
  editAccount(payload: { index: number; password?: string; website?: string; platform?: Platform; accountsFile?: string }): Promise<void>
  removeAccount(index: number, platform?: Platform, accountsFile?: string): Promise<void>
  openFilePicker(): Promise<string | null>
  getAccountsDefaultPath(platform?: Platform): Promise<string>
  removeAllListeners(): void
  /** Release all event listeners registered by this API client instance. */
  dispose(): void
}
