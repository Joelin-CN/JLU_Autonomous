import type {
  Account,
  AccountLane,
  Balance,
  ChaoxingApi,
  CompletionEvent,
  Course,
  ErrorEvent,
  JobHandle,
  PhaseChangeEvent,
  ProgressEvent,
  RuntimePhase,
  Settings,
  StartJobPayload,
  SystemResources,
  Ticket,
} from './types'
import {
  generateMockAccounts,
  generateMockCoursesForAccount,
  generateMockJobHandle,
  generateMockTickets,
  sleep,
} from './mockData'

type EventCallback = (...args: any[]) => void

// Placeholder captcha screenshot (inline SVG data URI) for mock/browser mode.
const MOCK_CAPTCHA_IMAGE =
  'data:image/svg+xml;utf8,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="60">' +
      '<rect width="160" height="60" fill="#f0f0f0"/>' +
      '<text x="80" y="40" font-family="monospace" font-size="32" font-weight="bold"' +
      ' fill="#333" text-anchor="middle" letter-spacing="6" transform="rotate(-4 80 30)">A7K9</text>' +
      '<line x1="10" y1="20" x2="150" y2="45" stroke="#999" stroke-width="1"/>' +
      '<line x1="20" y1="50" x2="140" y2="12" stroke="#bbb" stroke-width="1"/>' +
    '</svg>',
  )


interface JobSimulation {
  jobId: string
  payload: StartJobPayload
  handle: JobHandle
  timers: ReturnType<typeof setTimeout>[]
  running: boolean
}

const MAX_TICKETS = 200

export class MockApiClient implements ChaoxingApi {
  private accounts: Account[] = []
  private coursesByAccount: Record<string, Course[]> = {}
  private tickets: Ticket[] = []
  private currentSimulation: JobSimulation | null = null
  private listeners = new Map<string, Set<EventCallback>>()

  constructor() {
    this.accounts = generateMockAccounts()
    this.tickets = generateMockTickets()
    for (const account of this.accounts.slice(0, 5)) {
      this.coursesByAccount[account.id] = generateMockCoursesForAccount(account.id)
    }
  }

  private addListener(event: string, callback: EventCallback): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set())
    }
    this.listeners.get(event)?.add(callback)
  }

  private emit(event: string, data: unknown): void {
    const callbacks = this.listeners.get(event)
    if (!callbacks) return
    for (const callback of callbacks) {
      callback(data)
    }
  }

  private addLog(level: string, message: string): void {
    this.emit('log', { level, message, timestamp: Date.now() })
  }

  private clearTimers(simulation: JobSimulation): void {
    for (const timer of simulation.timers) {
      clearTimeout(timer)
    }
    simulation.timers = []
  }

  private stopSimulation(): void {
    if (!this.currentSimulation) return
    this.currentSimulation.running = false
    this.clearTimers(this.currentSimulation)
  }

  private cloneHandle(handle: JobHandle): JobHandle {
    return {
      ...handle,
      phases: handle.phases.map((phase) => ({ ...phase })),
      lanes: handle.lanes.map((lane) => ({ ...lane })),
    }
  }

  private getSimulation(jobId: string): JobSimulation {
    if (!this.currentSimulation || this.currentSimulation.jobId !== jobId) {
      throw new Error(`Job ${jobId} not found`)
    }
    return this.currentSimulation
  }

  private getMaxConcurrency(payload: StartJobPayload): number {
    return Math.max(1, Number(payload.options?.maxConcurrency ?? 2))
  }

  private syncHandleStatus(simulation: JobSimulation): void {
    const lanes = simulation.handle.lanes
    const running = lanes.some((lane) => lane.status === 'running' || lane.status === 'pending')
    const paused = lanes.some((lane) => lane.status === 'paused')
    const active = lanes.some((lane) => ['running', 'pending', 'paused'].includes(lane.status))

    if (!active) {
      simulation.handle.status = 'stopped'
      simulation.running = false
      this.clearTimers(simulation)
      return
    }

    if (!running && paused) {
      simulation.handle.status = 'paused'
      simulation.running = false
      this.clearTimers(simulation)
      return
    }

    simulation.handle.status = 'running'
    simulation.running = true
  }

  private activatePendingLanes(simulation: JobSimulation): void {
    const maxConcurrency = this.getMaxConcurrency(simulation.payload)
    let runningCount = simulation.handle.lanes.filter((lane) => lane.status === 'running').length
    for (const lane of simulation.handle.lanes) {
      if (runningCount >= maxConcurrency) break
      if (lane.status !== 'pending') continue
      lane.status = 'running'
      lane.currentPhase = simulation.handle.phases[simulation.handle.phaseIndex]?.name
      lane.currentTask = 'Running job'
      lane.startedAt = Date.now()
      runningCount += 1
    }
  }

  private emitStoppedCompletion(jobId: string, startedAt: number): void {
    this.emit('completed', {
      jobId,
      success: false,
      results: {
        totalSections: 0,
        completedSections: 0,
        failedSections: 0,
        totalQuizzes: 0,
        solvedQuizzes: 0,
        failedQuizzes: 0,
        durationMs: Date.now() - startedAt,
      },
      timestamp: Date.now(),
    } satisfies CompletionEvent)
  }

  async startJob(payload: StartJobPayload): Promise<JobHandle> {
    await sleep(300)
    this.stopSimulation()

    const handle = generateMockJobHandle(payload)
    this.currentSimulation = {
      jobId: handle.jobId,
      payload,
      handle,
      timers: [],
      running: true,
    }

    this.simulateJob(this.currentSimulation)

    // Demo: surface a captcha ticket a few seconds in so the CaptchaModal can
    // be exercised in browser/mock mode without a real backend.
    const captchaTimer = setTimeout(() => {
      if (!this.currentSimulation?.running) return
      const accountId = payload.accounts?.[0] ?? '0'
      const captcha: Ticket = {
        id: `captcha_${accountId}_${Math.floor(Date.now() / 1000)}`,
        title: '需要人工输入验证码',
        message: `账号 ${accountId} 在反爬验证码处受阻，AI 识别失败，请人工输入`,
        severity: 'critical',
        accountId: String(accountId),
        kind: 'captcha',
        imageBase64: MOCK_CAPTCHA_IMAGE,
        options: ['输入验证码', '跳过此课程'],
        resolved: false,
        createdAt: Date.now(),
      }
      this.addTicket(captcha)
    }, 4000)
    this.currentSimulation.timers.push(captchaTimer)

    return this.cloneHandle(handle)
  }

  async pauseJob(jobId: string, accountIds?: string[]): Promise<void> {
    await sleep(150)
    const simulation = this.getSimulation(jobId)

    if (accountIds?.length) {
      for (const lane of simulation.handle.lanes) {
        if (accountIds.includes(lane.accountId) && lane.status === 'running') {
          lane.status = 'paused'
          lane.currentTask = 'Paused'
        }
      }
    } else {
      // Global pause must also hold back pending lanes. syncHandleStatus()
      // treats `pending` as active, so leaving them pending would keep the job
      // status `running` and the UI would never show the paused state.
      for (const lane of simulation.handle.lanes) {
        if (lane.status === 'running' || lane.status === 'pending') {
          lane.status = 'paused'
          lane.currentTask = 'Paused'
        }
      }
    }

    this.syncHandleStatus(simulation)
    this.addLog('warn', accountIds?.length ? 'Paused selected accounts.' : 'Paused job.')
  }

  async resumeJob(jobId: string): Promise<void> {
    await sleep(150)
    const simulation = this.getSimulation(jobId)
    for (const lane of simulation.handle.lanes) {
      if (lane.status === 'paused') {
        lane.status = 'running'
        lane.currentTask = 'Resumed'
        lane.startedAt = Date.now()
      }
    }
    simulation.handle.status = 'running'
    simulation.running = true
    this.addLog('info', 'Resumed job.')
    this.simulateJob(simulation)
  }

  async stopJob(jobId: string, accountIds?: string[]): Promise<void> {
    await sleep(150)
    const simulation = this.getSimulation(jobId)

    if (accountIds?.length) {
      for (const lane of simulation.handle.lanes) {
        if (accountIds.includes(lane.accountId) && ['running', 'paused', 'pending'].includes(lane.status)) {
          lane.status = 'stopped'
          lane.currentTask = 'Stopped'
        }
      }
    } else {
      for (const lane of simulation.handle.lanes) {
        if (lane.status !== 'completed') {
          lane.status = 'stopped'
          lane.currentTask = 'Stopped'
        }
      }
    }

    this.syncHandleStatus(simulation)
    if (simulation.handle.status === 'stopped') {
      this.emitStoppedCompletion(jobId, simulation.handle.createdAt)
    }
    this.addLog('warn', accountIds?.length ? 'Stopped selected accounts.' : 'Stopped job.')
  }

  async pauseSelected(jobId: string, accountIds: string[]): Promise<void> {
    return this.pauseJob(jobId, accountIds)
  }

  async resumeSelected(jobId: string, accountIds: string[]): Promise<void> {
    await sleep(150)
    const simulation = this.getSimulation(jobId)
    for (const lane of simulation.handle.lanes) {
      if (accountIds.includes(lane.accountId) && lane.status === 'paused') {
        lane.status = 'running'
        lane.currentTask = 'Resumed'
        lane.startedAt = Date.now()
      }
    }
    this.activatePendingLanes(simulation)
    simulation.handle.status = 'running'
    simulation.running = true
    this.addLog('info', 'Resumed selected accounts.')
    this.simulateJob(simulation)
  }

  async stopSelected(jobId: string, accountIds: string[]): Promise<void> {
    return this.stopJob(jobId, accountIds)
  }

  async getJobStatus(jobId: string): Promise<JobHandle> {
    await sleep(100)
    return this.cloneHandle(this.getSimulation(jobId).handle)
  }

  async scanCourses(accountIds?: string[]): Promise<Course[]> {
    await sleep(500)
    const targetIds = accountIds?.length ? accountIds : this.accounts.slice(0, 5).map((account) => account.id)
    const results: Course[] = []

    for (const accountId of targetIds) {
      const courses = generateMockCoursesForAccount(accountId)
      this.coursesByAccount[accountId] = courses
      results.push(...courses)
    }

    this.addLog('info', `Scanned ${results.length} courses.`)
    return results
  }

  async getCourses(accountId?: string): Promise<Course[]> {
    await sleep(150)
    if (accountId) {
      if (!this.coursesByAccount[accountId]) {
        this.coursesByAccount[accountId] = generateMockCoursesForAccount(accountId)
      }
      return [...this.coursesByAccount[accountId]]
    }

    return Object.values(this.coursesByAccount).flatMap((courses) => courses)
  }

  async getAccounts(): Promise<Account[]> {
    await sleep(150)
    return this.accounts.map((account) => ({
      ...account,
      lastChecked: Date.now(),
      status: account.status === 'checking' ? 'online' : account.status,
    }))
  }

  async getAccountStatus(accountId: string): Promise<Account> {
    await sleep(100)
    const account = this.accounts.find((item) => item.id === accountId)
    if (!account) {
      throw new Error(`Account ${accountId} not found`)
    }
    return { ...account, lastChecked: Date.now() }
  }

  async getSettings(): Promise<Settings> {
    await sleep(100)
    const stored = localStorage.getItem('chaoxing-assistant-settings')
    if (stored) {
      try {
        return JSON.parse(stored)
      } catch {
        localStorage.removeItem('chaoxing-assistant-settings')
      }
    }

    return {
      theme: 'light',
      language: 'zh-CN',
      maxConcurrency: 2,
      quizSolver: 'doubao',
      quizRetryCount: 10,
      logRetention: 7,
      notifications: true,
      debugMode: false,
      headless: true,
      targetAccuracy: 100,
      accountsFilePath: '',
      concurrencyTarget: null,
      perAccountEstimateGB: 0.7,
      pythonPath: '',
      pageLoadTimeout: 30,
      snapshotTimeout: 15,
      clickTimeout: 10,
      videoWatchTimeout: 60,
      quizAnswerTimeout: 120,
      sectionCompleteTimeout: 15,
      dryRun: false,
    }
  }

  async setSettings(settings: Settings): Promise<void> {
    await sleep(100)
    localStorage.setItem('chaoxing-assistant-settings', JSON.stringify(settings))
  }

  async getAiStatus(): Promise<{ provider: string; label: string; configured: boolean; model: string; keyTail: string }> {
    await sleep(50)
    return { provider: 'doubao-api', label: '火山方舟（豆包）', configured: false, model: 'ep-demo', keyTail: '' }
  }

  async setAiConfig(_payload: { provider?: string; apiKey?: string; model: string }): Promise<void> {
    await sleep(100)
  }

  async testAi(_provider?: string): Promise<{ ok: boolean; reason?: string; models?: number }> {
    await sleep(300)
    return { ok: true, models: 3 }
  }

  async addAccount(_payload: { account: string; password: string; website?: string }): Promise<void> {
    await sleep(150)
  }

  async editAccount(_payload: { index: number; password?: string; website?: string }): Promise<void> {
    await sleep(150)
  }

  async removeAccount(_index: number): Promise<void> {
    await sleep(150)
  }

  async openFilePicker(): Promise<string | null> {
    await sleep(50)
    return null
  }

  async getAccountsDefaultPath(): Promise<string> {
    await sleep(20)
    return 'data/passwords/chaoxing.txt'
  }

  async getMemoryPlan(): Promise<import('./types').MemoryPlan> {
    await sleep(50)
    return {
      totalGB: 32, baselineGB: 14, budgetGB: 13.5, cpuCap: 8,
      memMax: 19, maxConcurrent: 8, systemLimitGB: 28.5, perAccountEstimateGB: 0.7,
    }
  }

  async getTickets(): Promise<Ticket[]> {
    await sleep(150)
    if (Math.random() > 0.7) {
      this.addTicket(generateMockTickets(1)[0])
    }
    return [...this.tickets]
  }

  async resolveTicket(ticketId: string, resolution: string): Promise<void> {
    await sleep(150)
    const ticket = this.tickets.find((item) => item.id === ticketId)
    if (!ticket) {
      throw new Error(`Ticket ${ticketId} not found`)
    }

    ticket.resolved = true
    ticket.resolvedAt = Date.now()
    ticket.resolution = resolution
    this.addLog('info', `Resolved ticket ${ticket.title}.`)
  }

  async resolveCaptcha(payload: {
    ticketId: string
    accountId: number
    answer?: string
    action?: 'skip'
  }): Promise<void> {
    await sleep(150)
    const verb = payload.action === 'skip' ? 'skipped' : `answered "${payload.answer}"`
    this.addLog('info', `Captcha ${payload.ticketId} ${verb} (account ${payload.accountId}).`)
  }

  async getBalance(_provider?: 'doubao' | 'deepseek'): Promise<Balance> {
    await sleep(200)
    return {
      provider: 'doubao',
      accountId: 2100123456,
      availableBalance: '326.50',
      cashBalance: '326.50',
      creditLimit: '0.00',
      arrearsBalance: '0.00',
      freezeAmount: '0.00',
      currency: 'CNY',
      checkedAt: Date.now(),
    }
  }

  async validatePython(_pythonPath: string): Promise<{ reason: string | null }> {
    await sleep(120)
    return { reason: null }
  }

  async getSystemResources(): Promise<SystemResources> {
    await sleep(80)
    // Jittered around a plausible baseline so the panel visibly updates in
    // browser/mock mode (real values come from Node `os` in Electron).
    const total = 16
    const usedPct = 35 + Math.round(Math.random() * 20) // 35–55%
    const used = Math.round(total * usedPct) / 100
    return {
      ram: { total, used, free: Math.round((total - used) * 10) / 10, pct: usedPct },
      cpu: { pct: 20 + Math.round(Math.random() * 40), cores: 8 }, // 20–60%
      uptimeSeconds: Math.round(Date.now() / 1000) % 86400,
    }
  }

  onProgress(callback: (event: ProgressEvent) => void): () => void {
    return this.onWithCleanup('progress', callback)
  }

  onPhaseChange(callback: (event: PhaseChangeEvent) => void): () => void {
    return this.onWithCleanup('phaseChange', callback)
  }

  onLog(callback: (line: { level: string; message: string; timestamp: number }) => void): () => void {
    return this.onWithCleanup('log', callback)
  }

  onTicket(callback: (ticket: Ticket) => void): () => void {
    return this.onWithCleanup('ticket', callback)
  }

  onCompleted(callback: (event: CompletionEvent) => void): () => void {
    return this.onWithCleanup('completed', callback)
  }

  onError(callback: (event: ErrorEvent) => void): () => void {
    return this.onWithCleanup('error', callback)
  }

  onResult(callback: (data: unknown) => void): () => void {
    return this.onWithCleanup('result', callback)
  }

  onMemory(_callback: (e: import('./types').MemoryEvent) => void): () => void {
    // Mock mode never emits MEMORY events.
    return () => {}
  }

  removeAllListeners(): void {
    this.dispose()
  }

  dispose(): void {
    this.listeners.clear()
    this.stopSimulation()
  }

  private onWithCleanup<T>(event: string, callback: (payload: T) => void): () => void {
    this.addListener(event, callback)
    return () => {
      this.listeners.get(event)?.delete(callback)
    }
  }

  private addTicket(ticket: Ticket): void {
    this.tickets.unshift(ticket)
    if (this.tickets.length > MAX_TICKETS) {
      this.tickets = this.tickets.slice(0, MAX_TICKETS)
    }
    this.emit('ticket', ticket)
  }

  private markCompletion(simulation: JobSimulation): void {
    simulation.handle.status = 'completed'
    simulation.handle.progress = 100
    simulation.handle.phases = simulation.handle.phases.map((phase) => ({
      ...phase,
      status: 'completed',
      progress: 100,
    }))
    simulation.handle.lanes = simulation.handle.lanes.map((lane) => ({
      ...lane,
      status: lane.status === 'stopped' ? 'stopped' : 'completed',
      progress: lane.status === 'stopped' ? lane.progress : 100,
      currentTask: lane.status === 'stopped' ? lane.currentTask : 'Completed',
      currentPhase: lane.status === 'stopped' ? lane.currentPhase : 'completed',
    }))
    simulation.running = false
    this.clearTimers(simulation)

    this.emit('completed', {
      jobId: simulation.handle.jobId,
      success: true,
      results: {
        totalSections: simulation.handle.courseCount * 10,
        completedSections: simulation.handle.courseCount * 10,
        failedSections: 0,
        totalQuizzes: simulation.handle.courseCount * 3,
        solvedQuizzes: simulation.handle.courseCount * 3,
        failedQuizzes: 0,
        durationMs: Date.now() - simulation.handle.createdAt,
      },
      timestamp: Date.now(),
    } satisfies CompletionEvent)

    this.addLog('info', 'Job completed.')
    this.addTicket(generateMockTickets(1)[0])
  }

  private updateRunningLaneProgress(lane: AccountLane, phase: RuntimePhase, step: number): AccountLane {
    return {
      ...lane,
      progress: Math.min(100, lane.progress + step * 1.1),
      currentPhase: phase.name,
      currentTask: `Running ${phase.name}`,
    }
  }

  private simulateJob(simulation: JobSimulation): void {
    if (!simulation.running) return
    if (simulation.timers.length > 0) return

    const tick = () => {
      simulation.timers = []
      if (!simulation.running) return

      this.activatePendingLanes(simulation)
      const phase = simulation.handle.phases[simulation.handle.phaseIndex]
      if (!phase) {
        this.markCompletion(simulation)
        return
      }

      const runningLanes = simulation.handle.lanes.filter((lane) => lane.status === 'running')
      if (runningLanes.length === 0) {
        this.syncHandleStatus(simulation)
        return
      }

      const step = 8 + Math.random() * 12
      phase.progress = Math.min(100, phase.progress + step)
      phase.status = 'running'

      const phaseWeight = 100 / Math.max(1, simulation.handle.phases.length)
      const completedPhaseProgress = simulation.handle.phaseIndex * phaseWeight
      const currentPhaseContribution = (phase.progress / 100) * phaseWeight
      simulation.handle.progress = Math.round(completedPhaseProgress + currentPhaseContribution)

      simulation.handle.lanes = simulation.handle.lanes.map((lane) =>
        lane.status === 'running' ? this.updateRunningLaneProgress(lane, phase, step) : lane,
      )

      this.emit('progress', {
        jobId: simulation.handle.jobId,
        phase: phase.name,
        phaseIndex: simulation.handle.phaseIndex,
        percent: simulation.handle.progress,
        message: `Running ${phase.name}: ${phase.message ?? ''}`.trim(),
        timestamp: Date.now(),
      } satisfies ProgressEvent)

      this.addLog('info', `[${phase.name}] ${Math.round(phase.progress)}%`)

      if (phase.progress >= 100) {
        const previousPhase = phase.name
        phase.status = 'completed'
        phase.progress = 100
        simulation.handle.phaseIndex += 1

        const nextPhase = simulation.handle.phases[simulation.handle.phaseIndex]
        if (nextPhase) {
          nextPhase.status = 'running'
          this.emit('phaseChange', {
            jobId: simulation.handle.jobId,
            fromPhase: previousPhase,
            toPhase: nextPhase.name,
            phaseIndex: simulation.handle.phaseIndex,
            timestamp: Date.now(),
          } satisfies PhaseChangeEvent)
        }
      }

      if (simulation.handle.phaseIndex >= simulation.handle.phases.length) {
        this.markCompletion(simulation)
        return
      }

      const timer = setTimeout(tick, 700 + Math.random() * 900)
      simulation.timers.push(timer)
    }

    const timer = setTimeout(tick, 400)
    simulation.timers.push(timer)
  }
}
