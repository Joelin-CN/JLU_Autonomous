import type {
  Account,
  AIProvider,
  AppApi,
  Balance,
  CompletionEvent,
  Course,
  ErrorEvent,
  JobHandle,
  ModeType,
  PhaseChangeEvent,
  Platform,
  ProgressEvent,
  Settings,
  StartJobPayload,
  SystemResources,
  Ticket,
  TicketKind,
  MemoryEvent,
  MemoryPlan,
  AiStatus,
  AiTestResult,
} from './types'
import { MODES } from './constants'

function requireAPI() {
  if (!window.electronAPI) throw new Error('Electron API not available')
  return window.electronAPI
}

/**
 * ipcRenderer.invoke wraps any main-process rejection as
 * "Error invoking remote method '<channel>': <real message>" (optionally with a
 * nested "Error:" prefix). Strip both so UI surfaces show the real reason.
 */
export function stripInvokeErrorPrefix(message: string): string {
  return message
    .replace(/^Error invoking remote method '[^']+':\s*/i, '')
    .replace(/^Error:\s*/i, '')
    .trim()
}

function mapMode(mode: string): 'full' | 'scan_only' | 'solve_only' {
  if (mode === 'course-scan' || mode === 'section-scan' || mode === 'dry-run') return 'scan_only'
  if (mode === 'batch-exec') return 'solve_only'
  return 'full'
}

function mapBackMode(mode?: 'full' | 'scan_only' | 'solve_only'): ModeType {
  if (mode === 'scan_only') return 'course-scan'
  if (mode === 'solve_only') return 'batch-exec'
  return 'full-auto'
}

// Backend solvers ('deepseek' | 'doubao' | 'local') -> renderer AIProvider.
// Doubao API is the sole AI backend, so the renderer only models 'doubao';
// any backend value normalizes to it.
function mapQuizSolver(_solver?: string): AIProvider {
  return 'doubao'
}

// Maps the Electron-layer Ticket (type/imageBase64/options, ISO timestamps)
// to the renderer Ticket (severity, ms timestamps). Interactive tickets are
// surfaced as 'critical' and carry kind/imageBase64/options through so the
// interactive captcha modal can render and resolve them.
//
// Interactive FORM discrimination is inferred from the field combination the
// backends already emit (the NDJSON TICKET payload itself carries no form
// field — the backend can add an explicit one later to remove the heuristic):
//   - imageBase64 + timeoutSeconds → 'qrcode'  (zhihuishu QR login, auth.py)
//   - captcha type without image   → 'hint'    (zhihuishu slider: drag in the
//                                               visible browser window)
//   - otherwise                    → 'captcha' (chaoxing image + text input)
export function classifyTicketKind(ticket: any, isCaptchaType: boolean): TicketKind | undefined {
  if (!isCaptchaType) return undefined
  if (!ticket.imageBase64) return 'hint'
  if (typeof ticket.timeoutSeconds === 'number' && ticket.timeoutSeconds > 0) return 'qrcode'
  return 'captcha'
}

function mapElectronTicket(ticket: any): Ticket {
  const isCaptcha = ticket.type === 'captcha' || ticket.type === 'verification'
  const severity: Ticket['severity'] = isCaptcha
    ? 'critical'
    : ticket.type === 'error'
      ? 'critical'
      : ticket.type === 'warning'
        ? 'warning'
        : 'info'

  return {
    id: ticket.id,
    title: ticket.title,
    message: ticket.message,
    severity,
    accountId: ticket.accountId != null ? String(ticket.accountId) : undefined,
    resolved: ticket.resolved,
    resolvedAt: ticket.resolvedAt ? new Date(ticket.resolvedAt).getTime() : undefined,
    resolution: ticket.resolution,
    createdAt: new Date(ticket.createdAt).getTime(),
    kind: classifyTicketKind(ticket, isCaptcha),
    imageBase64: ticket.imageBase64,
    timeoutSeconds: typeof ticket.timeoutSeconds === 'number' ? ticket.timeoutSeconds : undefined,
    // Injected by the Electron main process from the running job's platform
    // (the backend TICKET event itself is platform-agnostic).
    platform: ticket.platform === 'zhihuishu' || ticket.platform === 'chaoxing' ? ticket.platform : undefined,
    options: Array.isArray(ticket.options) ? ticket.options : undefined,
  }
}

function mapElectronCourse(raw: any): Course {
  const sections = Array.isArray(raw.sections) ? raw.sections : undefined
  // Prefer explicit counts from discovery; fall back to deriving from sections.
  const totalSections = raw.totalSections ?? sections?.length ?? 0
  const completedSections =
    raw.completedSections ?? sections?.filter((s: any) => s.status === 'completed').length ?? 0
  return {
    id: String(raw.id),
    name: raw.name,
    teacher: raw.teacher ?? undefined,
    progress: raw.progress ?? 0,
    totalSections,
    completedSections,
    accountId: raw.accountId != null ? String(raw.accountId) : undefined,
    sections: sections?.map((s: any) => ({
      id: String(s.id),
      name: s.title ?? s.name ?? '',
      completed: s.status === 'completed',
    })),
  }
}

export class ElectronApiClient implements AppApi {
  private cleanupFns: Array<() => void> = []
  private currentHandle: JobHandle | null = null

  async startJob(payload: StartJobPayload): Promise<JobHandle> {
    this.dispose()
    const api = requireAPI()
    const platform: Platform = payload.platform ?? 'chaoxing'
    const result = await api.startJob({
      platform,
      accountIds: payload.accounts.map((id) => Number.parseInt(id, 10)),
      courseIds: payload.courses,
      mode: mapMode(payload.mode),
      objective: payload.objective,
      strategy: payload.strategy,
      options: payload.options,
    } as any)

    const modeConfig = MODES.find((item) => item.key === payload.mode)
    const phases = (modeConfig?.phases ?? []).map(([name, message], index) => ({
      name,
      status: index === 0 ? 'running' as const : 'pending' as const,
      progress: 0,
      message,
    }))

    this.currentHandle = {
      jobId: result.jobId,
      status: 'running',
      platform,
      createdAt: Date.now(),
      startedAt: Date.now(),
      objective: payload.objective,
      strategy: payload.strategy,
      mode: payload.mode,
      courseCount: payload.courses.length,
      accountCount: payload.accounts.length,
      progress: 0,
      phaseIndex: 0,
      phases,
      lanes: payload.accounts.map((accountId, index) => ({
        accountId,
        status: index === 0 ? 'running' : 'pending',
        progress: 0,
        currentTask: index === 0 ? 'Starting...' : 'Queued...',
        currentPhase: phases[0]?.name,
      })),
    }
    return this.currentHandle
  }

  async pauseJob(jobId: string, accountIds?: string[]): Promise<void> {
    if (accountIds?.length) await requireAPI().pauseSelected(jobId, accountIds.map((id) => Number.parseInt(id, 10)))
    else await requireAPI().pauseJob(jobId)
  }

  async resumeJob(jobId: string): Promise<void> {
    await requireAPI().resumeJob(jobId)
  }

  async stopJob(jobId: string, accountIds?: string[]): Promise<void> {
    if (accountIds?.length) await requireAPI().stopSelected(jobId, accountIds.map((id) => Number.parseInt(id, 10)))
    else await requireAPI().stopJob(jobId)
  }

  async pauseSelected(jobId: string, accountIds: string[]): Promise<void> {
    await requireAPI().pauseSelected(jobId, accountIds.map((id) => Number.parseInt(id, 10)))
  }

  async resumeSelected(jobId: string, accountIds: string[]): Promise<void> {
    await requireAPI().resumeSelected(jobId, accountIds.map((id) => Number.parseInt(id, 10)))
  }

  async stopSelected(jobId: string, accountIds: string[]): Promise<void> {
    await requireAPI().stopSelected(jobId, accountIds.map((id) => Number.parseInt(id, 10)))
  }

  async getJobStatus(jobId: string): Promise<JobHandle> {
    const raw = await requireAPI().getJobStatus(jobId) as any
    const mode = this.currentHandle?.mode ?? mapBackMode(raw.mode)
    const modeConfig = MODES.find((item) => item.key === mode)
    const phaseIndex = typeof raw.phaseIndex === 'number' ? raw.phaseIndex : this.currentHandle?.phaseIndex ?? 0
    // Always recompute the stepper from phaseIndex + global progress. The
    // old "prefer currentHandle.phases" shortcut replayed the snapshot taken
    // at startJob() forever, overwriting live event-driven updates.
    const phases = (modeConfig?.phases ?? []).map(([name, message], index) => ({
      name,
      status: index < phaseIndex ? 'completed' as const : index === phaseIndex ? 'running' as const : 'pending' as const,
      progress: index < phaseIndex ? 100 : index === phaseIndex ? (raw.progress ?? 0) : 0,
      message,
    }))

    const handle: JobHandle = {
      jobId: raw.jobId,
      status: raw.status,
      // Backend JobStatus carries no platform; keep the one recorded at start.
      platform: this.currentHandle?.platform,
      createdAt: this.currentHandle?.createdAt ?? Date.now(),
      startedAt: raw.startedAt ? new Date(raw.startedAt).getTime() : this.currentHandle?.startedAt,
      completedAt: raw.finishedAt ? new Date(raw.finishedAt).getTime() : this.currentHandle?.completedAt,
      objective: this.currentHandle?.objective ?? 'catchup',
      strategy: this.currentHandle?.strategy ?? 'balanced',
      mode,
      courseCount: raw.courseIds?.length ?? this.currentHandle?.courseCount ?? 0,
      accountCount: raw.accountIds?.length ?? this.currentHandle?.accountCount ?? 0,
      progress: raw.progress,
      phaseIndex,
      phases,
      lanes: (raw.lanes ?? []).map((lane: any) => ({
        accountId: String(lane.accountId),
        status: lane.status,
        progress: lane.progress,
        currentTask: lane.currentTask,
        currentPhase: lane.currentPhase,
        errorMessage: lane.errorMessage,
      })),
      memoryPlan: raw.memoryPlan,
    }

    this.currentHandle = handle
    return handle
  }

  async scanCourses(accountIds?: string[], platform?: Platform): Promise<Course[]> {
    const raw = await requireAPI().scanCourses({ accountIds: (accountIds ?? []).map((id) => Number.parseInt(id, 10)), platform })
    return (raw as any[]).map((c) => ({ ...mapElectronCourse(c), platform: platform ?? 'chaoxing' }))
  }

  async getCourses(accountId?: string, platform?: Platform): Promise<Course[]> {
    const raw = await requireAPI().getCourses(accountId ? Number.parseInt(accountId, 10) : 0, platform)
    return (raw as any[]).map((c) => ({ ...mapElectronCourse(c), platform: platform ?? 'chaoxing' }))
  }

  async getAccounts(platform?: Platform): Promise<Account[]> {
    const raw = await requireAPI().getAccounts(platform)
    return raw.map((account: any) => ({
      id: String(account.id),
      username: account.username,
      displayName: account.nickname ?? account.username,
      website: account.website ?? '',
      status: account.enabled ? 'online' : 'offline',
      avatar: account.avatar,
      platform: platform ?? 'chaoxing',
    }))
  }

  async getAccountStatus(accountId: string): Promise<Account> {
    const raw = await requireAPI().getAccountStatus(Number.parseInt(accountId, 10))
    return {
      id: String(raw.accountId),
      username: '',
      displayName: '',
      status: raw.loggedIn ? 'online' : 'offline',
    }
  }

  async getSettings(): Promise<Settings> {
    const raw = await requireAPI().getSettings()
    return {
      theme: 'light',
      language: 'zh-CN',
      maxConcurrency: raw.maxWorkers,
      quizSolver: mapQuizSolver(raw.quizSolver),
      quizRetryCount: raw.quizRetryCount ?? 10,
      logRetention: raw.logRetention ?? 7,
      notifications: raw.notifications ?? true,
      debugMode: raw.logLevel === 'debug',
      headless: raw.headless,
      targetAccuracy: raw.targetAccuracy ?? 100,
      // Backend settings carry a single chaoxing-semantics slot; the
      // zhihuishu path lives only in renderer localStorage.
      accountsFilePaths: { chaoxing: raw.accountsFilePath ?? '', zhihuishu: '' },
      concurrencyTarget: raw.concurrencyTarget ?? null,
      perAccountEstimateGB: raw.perAccountEstimateGB ?? 0.7,
      pythonPath: raw.pythonPath ?? '',
      pageLoadTimeout: raw.pageLoadTimeout ?? 30,
      snapshotTimeout: raw.snapshotTimeout ?? 15,
      clickTimeout: raw.clickTimeout ?? 10,
      videoWatchTimeout: raw.videoWatchTimeout ?? 60,
      quizAnswerTimeout: raw.quizAnswerTimeout ?? 120,
      sectionCompleteTimeout: raw.sectionCompleteTimeout ?? 15,
      dryRun: raw.dryRun ?? false,
    }
  }

  async setSettings(settings: Settings): Promise<void> {
    await requireAPI().setSettings({
      maxWorkers: settings.maxConcurrency,
      logLevel: settings.debugMode ? 'debug' : 'info',
      headless: settings.headless,
      // The backend slot is chaoxing-semantics only (CHAOXING_ACCOUNTS_FILE).
      accountsFilePath: settings.accountsFilePaths.chaoxing,
      concurrencyTarget: settings.concurrencyTarget,
      perAccountEstimateGB: settings.perAccountEstimateGB,
      pythonPath: settings.pythonPath,
      notifications: settings.notifications,
      logRetention: settings.logRetention,
      pageLoadTimeout: settings.pageLoadTimeout,
      snapshotTimeout: settings.snapshotTimeout,
      clickTimeout: settings.clickTimeout,
      videoWatchTimeout: settings.videoWatchTimeout,
      quizAnswerTimeout: settings.quizAnswerTimeout,
      sectionCompleteTimeout: settings.sectionCompleteTimeout,
      dryRun: settings.dryRun,
      quizRetryCount: settings.quizRetryCount,
      targetAccuracy: settings.targetAccuracy,
    } as any)
  }

  async getAiStatus(): Promise<AiStatus> {
    return requireAPI().getAiStatus()
  }

  async setAiConfig(payload: { provider?: string; apiKey?: string; model: string }): Promise<void> {
    await requireAPI().setAiConfig(payload)
  }

  async testAi(provider?: string): Promise<AiTestResult> {
    return requireAPI().testAi(provider)
  }

  async addAccount(payload: { account: string; password: string; website?: string; platform?: Platform; accountsFile?: string }): Promise<void> {
    await requireAPI().addAccount(payload)
  }

  async editAccount(payload: { index: number; password?: string; website?: string; platform?: Platform; accountsFile?: string }): Promise<void> {
    await requireAPI().editAccount(payload)
  }

  async removeAccount(index: number, platform?: Platform, accountsFile?: string): Promise<void> {
    await requireAPI().removeAccount({ index, platform, accountsFile })
  }

  async openFilePicker(): Promise<string | null> {
    return requireAPI().openFilePicker()
  }

  async getAccountsDefaultPath(platform?: Platform): Promise<string> {
    return requireAPI().getAccountsDefaultPath(platform)
  }

  async getTickets(): Promise<Ticket[]> {
    const raw = await requireAPI().getTickets()
    return raw.map((ticket: any) => mapElectronTicket(ticket))
  }

  async resolveTicket(ticketId: string, resolution: string): Promise<void> {
    await requireAPI().resolveTicket(ticketId, resolution)
  }

  async resolveCaptcha(payload: {
    ticketId: string
    accountId: number
    answer?: string
    action?: 'skip'
  }): Promise<void> {
    await requireAPI().resolveCaptcha(payload)
  }

  async getBalance(provider?: 'doubao' | 'deepseek'): Promise<Balance> {
    let raw
    try {
      raw = await requireAPI().getBalance(provider)
    } catch (e: any) {
      // ipcRenderer.invoke wraps handler rejections as
      // "Error invoking remote method 'balance:query': <real reason>".
      // Strip the wrapper so the UI shows the actionable reason (e.g. the
      // backend's volcengine-python-sdk guidance), not truncated boilerplate.
      throw new Error(stripInvokeErrorPrefix(e?.message ?? '') || '余额查询失败')
    }
    return {
      provider: raw.provider,
      accountId: raw.accountId,
      availableBalance: raw.availableBalance,
      cashBalance: raw.cashBalance,
      creditLimit: raw.creditLimit,
      arrearsBalance: raw.arrearsBalance,
      freezeAmount: raw.freezeAmount,
      currency: raw.currency,
      checkedAt: new Date(raw.checkedAt).getTime(),
    }
  }

  /** Validate a candidate pythonPath in the main process (inline UI feedback). */
  async validatePython(pythonPath: string): Promise<{ reason: string | null }> {
    return requireAPI().validatePython(pythonPath)
  }

  async getSystemResources(): Promise<SystemResources> {
    // Shape matches 1:1 across the IPC boundary; pass through.
    return requireAPI().getSystemResources()
  }

  async getMemoryPlan(): Promise<MemoryPlan> {
    return requireAPI().getMemoryPlan()
  }

  onProgress(cb: (e: ProgressEvent) => void): () => void {
    const cleanup = requireAPI().onProgress((event: any) => {
      cb({
        jobId: event.jobId,
        phase: event.phase ?? '',
        phaseIndex: event.phaseIndex ?? this.currentHandle?.phaseIndex ?? 0,
        percent: event.percent,
        message: event.message,
        timestamp: Date.now(),
      })
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onPhaseChange(cb: (e: PhaseChangeEvent) => void): () => void {
    const cleanup = requireAPI().onPhaseChange((event: any) => {
      cb({
        jobId: event.jobId,
        fromPhase: event.fromPhase ?? '',
        toPhase: event.phase,
        phaseIndex: event.phaseIndex ?? this.currentHandle?.phaseIndex ?? 0,
        timestamp: Date.now(),
      })
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onLog(cb: (line: { level: string; message: string; timestamp: number }) => void): () => void {
    const cleanup = requireAPI().onLog((event: any) => {
      cb({
        level: event.level,
        message: event.message,
        timestamp: new Date(event.timestamp).getTime(),
      })
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onTicket(cb: (ticket: Ticket) => void): () => void {
    const cleanup = requireAPI().onTicket((event: any) => {
      cb(mapElectronTicket(event.ticket))
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onCompleted(cb: (e: CompletionEvent) => void): () => void {
    const cleanup = requireAPI().onCompleted((event: any) => {
      cb({
        jobId: event.jobId,
        success: true,
        results: {
          totalSections: 0,
          completedSections: 0,
          failedSections: 0,
          totalQuizzes: 0,
          solvedQuizzes: 0,
          failedQuizzes: 0,
          durationMs: 0,
        },
        timestamp: Date.now(),
      })
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onError(cb: (e: ErrorEvent) => void): () => void {
    const cleanup = requireAPI().onError((event: any) => {
      cb({
        jobId: event.jobId,
        error: event.error,
        phase: event.phase ?? '',
        recoverable: Boolean(event.recoverable),
        timestamp: Date.now(),
      })
    })
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onResult(cb: (data: unknown) => void): () => void {
    const cleanup = requireAPI().onResult((event: any) => cb(event.data))
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  onMemory(cb: (e: MemoryEvent) => void): () => void {
    const cleanup = requireAPI().onMemory((event: any) => cb(event))
    this.cleanupFns.push(cleanup)
    return cleanup
  }

  dispose(): void {
    for (const cleanup of this.cleanupFns) {
      try { cleanup() } catch {}
    }
    this.cleanupFns = []
  }

  removeAllListeners(): void {
    this.dispose()
  }
}
