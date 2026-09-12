import { ipcMain, BrowserWindow, Notification } from 'electron'
import { execSync, execFile } from 'child_process'
import os from 'os'
import path from 'path'
import { PythonBridge } from '../python/pythonBridge'
import { DATA_DIR } from '../backendPath'
import { getCurrentSettings } from './status.handler'
import { jobSlots, type JobSlot } from './jobSlots'
import {
  allocateBudget,
  computeMemoryPlan,
  measureProjectChromeGB,
  measureSystemUsedGB,
} from '../memory/planner'
import type { Platform,
  JobControlPayload,
  JobLaneStatus,
  JobStatus,
  ResolveTicketPayload,
  StartJobPayload,
} from '../types'
import { IPC_CHANNELS } from '../types'

const MAX_ACCOUNTS = 50
const RATE_LIMIT_COOLDOWN_MS = 500
/** Keep at most this many finished jobs in memory; older entries are dropped
 *  so the jobs map cannot grow without bound over a long-running session. */
const MAX_RETAINED_JOBS = 20

const jobs = new Map<string, JobStatus>()

// 活跃任务改由 jobSlots 按平台键控（同平台互斥、跨平台并行）；
// 这里不再持有全局单例 bridge / activeJobId。

const rateLimitMap = new Map<string, number>()

function checkRateLimit(key: string): void {
  const now = Date.now()
  const last = rateLimitMap.get(key) ?? 0
  if (now - last < RATE_LIMIT_COOLDOWN_MS) {
    throw new Error(`Rate limited: ${key}. Please wait before retrying.`)
  }
  rateLimitMap.set(key, now)
}

function generateJobId(): string {
  return `job_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
}

function retainJob(jobId: string, job: JobStatus): void {
  jobs.set(jobId, job)
  // Map preserves insertion order — drop the oldest entries first.
  while (jobs.size > MAX_RETAINED_JOBS) {
    const oldest = jobs.keys().next().value
    if (oldest === undefined) break
    jobs.delete(oldest)
  }
}

function cloneJob(job: JobStatus): JobStatus {
  return {
    ...job,
    accountIds: [...job.accountIds],
    courseIds: job.courseIds ? [...job.courseIds] : undefined,
    lanes: job.lanes?.map((lane) => ({ ...lane })),
  }
}

function validateAccountIds(raw: unknown): number[] {
  if (!Array.isArray(raw) || raw.length === 0) {
    throw new Error('At least one accountId is required.')
  }
  if (raw.length > MAX_ACCOUNTS) {
    throw new Error(`Too many accounts: ${raw.length}. Maximum is ${MAX_ACCOUNTS}.`)
  }

  const ids: number[] = []
  for (const value of raw) {
    const parsed = typeof value === 'string' ? Number.parseInt(value, 10) : value
    // accountId is the 0-based index from the id=index contract — 0 is the
    // FIRST account and is valid. Reject only negatives / non-integers; do not
    // use `<= 0` (that wrongly drops account 0, the falsy-index trap).
    if (typeof parsed !== 'number' || !Number.isInteger(parsed) || parsed < 0) {
      throw new Error(`Invalid accountId: ${String(value)}.`)
    }
    ids.push(parsed)
  }
  return ids
}

function sendToRenderer(win: BrowserWindow, channel: string, ...args: unknown[]): void {
  if (!win.isDestroyed()) {
    win.webContents.send(channel, ...args)
  }
}

function createInitialLanes(accountIds: number[]): JobLaneStatus[] {
  return accountIds.map((accountId) => ({
    accountId,
    status: 'running',
    progress: 0,
    currentTask: 'Starting job',
    currentPhase: 'idle',
  }))
}

function updateRunningLanes(
  job: JobStatus,
  updater: (lane: JobLaneStatus) => JobLaneStatus,
): void {
  if (!job.lanes?.length) return
  job.lanes = job.lanes.map((lane) => {
    if (lane.status === 'running') {
      return updater(lane)
    }
    return lane
  })
}

function markTerminalLanes(
  job: JobStatus,
  status: JobLaneStatus['status'],
  progress: number | null = null,
): void {
  if (!job.lanes?.length) return
  job.lanes = job.lanes.map((lane) => {
    if (lane.status === 'stopped' || lane.status === 'error') {
      return lane
    }
    return {
      ...lane,
      status,
      ...(status === 'completed'
        ? { progress: 100 }
        : progress !== null
          ? { progress }
          : {}),
      currentTask: status === 'completed' ? 'Completed' : lane.currentTask,
      currentPhase: status === 'completed' ? 'completed' : lane.currentPhase,
    }
  })
}

function getJobOrThrow(jobId: string): JobStatus {
  const job = jobs.get(jobId)
  if (!job) {
    throw new Error(`未找到任务 ${jobId}（可能已重启应用）。`)
  }
  return job
}

function validateControlPayload(payload: JobControlPayload): { job: JobStatus; accountIds: number[] } {
  const job = getJobOrThrow(payload.jobId)
  const accountIds = validateAccountIds(payload.accountIds)
  for (const accountId of accountIds) {
    if (!job.accountIds.includes(accountId)) {
      throw new Error(`Account ${accountId} is not part of job ${payload.jobId}.`)
    }
  }
  return { job, accountIds }
}

function selectedControlUnsupported(): never {
  throw new Error(
    'Per-account runtime control is not supported by the current Python backend. Use the global pause/resume/stop controls in Electron mode.',
  )
}

/**
 * Release the platform slot only when the event belongs to the slot's current
 * bridge. A previous job's Python process can still emit exit/error events
 * after a new job has started on the same platform; without this guard the
 * stale event would release the new job's slot.
 */
function releaseSlotIfCurrent(current: PythonBridge | null): void {
  if (!current) return
  jobSlots.releaseIfCurrent(current)
}

/**
 * Close the persistent playwright-cli browser sessions for the given accounts.
 *
 * The visible Chrome windows are children of the long-lived `playwright-cli`
 * daemon, NOT of the spawned Python process, so terminating Python (even with a
 * process-tree kill) leaves them running. Each account uses a session named
 * `chaoxing-chrome-<index>` (see backend auth.ensure_chaoxing_browser). Closing
 * an absent session is a harmless no-op, and login is preserved because cookies
 * live in the on-disk --user-data-dir profile.
 *
 * Fire-and-forget per session: we don't block the stop response on it.
 */
function closeBrowserSessions(accountIds: number[], platform: Platform = 'chaoxing'): void {
  const cli = process.platform === 'win32' ? 'playwright-cli.cmd' : 'playwright-cli'
  for (const id of accountIds) {
    try {
      // .cmd wrappers need shell:true on Windows; without it the close was
      // silently failing and Chrome lingered in Task Manager after every stop.
      execFile(cli, [`-s=${platform}-chrome-${id}`, 'close'], { shell: true, timeout: 20000 }, () => {
        // Ignore: session may already be gone, or the daemon may be down.
      })
    } catch {
      // execFile itself only throws synchronously on bad arguments; ignore.
    }
  }

  // After the daemon close attempts, sweep any chrome.exe still bound to a
  // project profile (e.g. the daemon is wedged or Python was force-killed).
  // Scoped to the profile root so the user's own Chrome is untouched.
  setTimeout(() => {
    const root = path.join(DATA_DIR, 'chrome-profiles')
    const escaped = root.replace(/'/g, "''")
    const script =
      "$ps = Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\";" +
      `$hits = $ps | Where-Object { $_.CommandLine -like '*${escaped}*' };` +
      "$hits | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    try {
      execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { timeout: 30000 }, () => {})
    } catch {
      // Cleanup is best-effort; never block the stop response on it.
    }
  }, 3000)
}

function pauseWholeJob(job: JobStatus): void {
  const slot = jobSlots.getByJobId(job.jobId)
  if (slot?.bridge.isRunning()) {
    slot.bridge.pause()
  }

  job.status = 'paused'
  job.phase = 'paused'
  job.message = 'Job paused.'
  if (job.lanes?.length) {
    job.lanes = job.lanes.map((lane) =>
      lane.status === 'running' ? { ...lane, status: 'paused', currentTask: 'Paused' } : lane,
    )
  }
}

function resumeWholeJob(job: JobStatus): void {
  const slot = jobSlots.getByJobId(job.jobId)
  if (!slot) {
    throw new Error('No active Python process. The job cannot be resumed.')
  }

  slot.bridge.resume()
  job.status = 'running'
  job.phase = 'idle'
  job.message = 'Job resumed.'
  if (job.lanes?.length) {
    job.lanes = job.lanes.map((lane) =>
      lane.status === 'paused' ? { ...lane, status: 'running', currentTask: 'Resuming' } : lane,
    )
  }
}

function stopWholeJob(job: JobStatus): void {
  const slot = jobSlots.getByJobId(job.jobId)
  if (slot?.bridge.isRunning()) {
    slot.bridge.stop()
  }

  // The visible Chrome is a child of the playwright-cli *daemon*, not of the
  // Python process — so killing Python (even tree-kill) never reaps it. The
  // only thing that closes it is `playwright-cli -s=<session> close`. Python's
  // own finally-block close is best-effort and often skipped when STOP escalates
  // to SIGTERM before a check_signals() checkpoint is reached, so close the
  // sessions here too. Idempotent: closing an already-gone session is a no-op.
  closeBrowserSessions(job.accountIds, job.platform ?? 'chaoxing')

  job.status = 'stopped'
  job.phase = 'stopped'
  job.message = 'Job stopped.'
  job.finishedAt = new Date().toISOString()
  if (job.lanes?.length) {
    job.lanes = job.lanes.map((lane) =>
      lane.status === 'completed' ? lane : { ...lane, status: 'stopped', currentTask: 'Stopped' },
    )
  }

  if (slot) jobSlots.release(slot.platform)
}

function createBridgeAndBind(win: BrowserWindow, jobId: string, platform: Platform): PythonBridge {
  const currentBridge = new PythonBridge()

  currentBridge.on('progress', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    job.message = event.message
    if (typeof event.phaseIndex === 'number') {
      job.phaseIndex = event.phaseIndex
    }
    if (event.phase) {
      job.phase = event.phase as JobStatus['phase']
    }

    if (typeof event.accountId === 'number' && job.lanes?.length) {
      // A per-course "Completed" event can carry 100% when a single-course job
      // still has more phases to run (e.g. quiz done, content pending). Cap
      // the lane at 99% until the account-level "DONE" terminal event.
      const laneProgress =
        event.percent >= 100 && !/^DONE/.test(event.message) ? 99 : event.percent
      job.lanes = job.lanes.map((lane) => {
        if (lane.accountId !== event.accountId) return lane
        const status = event.laneStatus === 'queued'
          ? 'queued'
          : event.laneStatus === 'error'
            ? 'error'
            : 'running'
        return {
          ...lane,
          status,
          progress: laneProgress,
          currentTask: event.message,
          currentPhase: event.phase ?? lane.currentPhase,
        }
      })
      // Overall job progress = average of active lane progress, so one
      // finished lane no longer forces the whole job to show 100%.
      job.progress = Math.round(
        job.lanes.reduce((sum, lane) => sum + lane.progress, 0) / job.lanes.length,
      )
    } else {
      job.progress = event.percent
      updateRunningLanes(job, (lane) => ({
        ...lane,
        progress: event.percent,
        currentTask: event.message,
        currentPhase: event.phase ?? lane.currentPhase,
      }))
    }

    sendToRenderer(win, IPC_CHANNELS.ON_PROGRESS, { ...event, platform })
  })

  currentBridge.on('memory', (event) => {
    // MEMORY 是进程级快照（不带平台）——渲染层按平台分桶显示，转发时统一盖章。
    sendToRenderer(win, IPC_CHANNELS.ON_MEMORY, { ...event, platform })
  })

  currentBridge.on('phase', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    job.phase = event.phase
    // The backend emits phase NAMES (login / scan_courses / process_sections /
    // solve_quiz / completed) — never an index. Map the name onto a normalized
    // 0..4 rank so job:status consumers see a phaseIndex that actually moves.
    const PHASE_RANK: Record<string, number> = {
      login: 0,
      scan_courses: 0,
      process_sections: 3,
      solve_quiz: 3,
      completed: 4,
    }
    const rank = PHASE_RANK[event.phase as string]
    if (rank !== undefined) {
      job.phaseIndex = Math.max(0, Math.min(4, rank))
    }

    updateRunningLanes(job, (lane) => ({
      ...lane,
      currentPhase: event.phase,
      currentTask: `Running ${event.phase}`,
    }))

    sendToRenderer(win, IPC_CHANNELS.ON_PHASE_CHANGE, { ...event, platform })
  })

  currentBridge.on('log', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_LOG, { ...event, platform })
  })

  currentBridge.on('ticket', (event) => {
    // The NDJSON TICKET event is platform-agnostic; the renderer needs the
    // platform for badges/filtering, so stamp the running job's platform onto
    // the forwarded ticket (protocol shape unchanged — additive field).
    const stamped = {
      ...event,
      platform,
      ticket: { ...event.ticket, platform },
    }
    sendToRenderer(win, IPC_CHANNELS.ON_TICKET, stamped)
  })

  currentBridge.on('error', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    job.status = 'error'
    job.message = event.error
    job.phase = (event.phase as JobStatus['phase']) ?? 'error'
    markTerminalLanes(job, 'error', job.progress)
    if (getCurrentSettings().notifications) {
      new Notification({ title: 'JLU 学习助手', body: `任务异常：${event.error}` }).show()
    }
    sendToRenderer(win, IPC_CHANNELS.ON_ERROR, { ...event, platform })
  })

  currentBridge.on('done', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    // The backend emits ERROR followed by DONE on failure. Once the job is in
    // the error state, DONE must not flip it back to "completed".
    if (job.status === 'error' || job.status === 'stopped') {
      releaseSlotIfCurrent(currentBridge)
      return
    }

    job.status = 'completed'
    job.phase = 'completed'
    job.progress = job.lanes?.length
      ? Math.round(job.lanes.reduce((sum, lane) => sum + lane.progress, 0) / job.lanes.length)
      : 100
    job.message = 'Job completed.'
    job.finishedAt = new Date().toISOString()
    markTerminalLanes(job, 'completed')
    if (getCurrentSettings().notifications) {
      new Notification({ title: 'JLU 学习助手', body: '任务已全部完成。' }).show()
    }

    sendToRenderer(win, IPC_CHANNELS.ON_COMPLETED, { ...event, platform })
    releaseSlotIfCurrent(currentBridge)
  })

  currentBridge.on('result', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_RESULT, { ...event, platform })
  })

  currentBridge.on('exit', (code) => {
    const job = jobs.get(jobId)
    // If the bridge already reported a specific error (e.g. spawn ENOENT),
    // keep that message — don't overwrite it with a generic exit line.
    if (job && job.status !== 'completed' && job.status !== 'stopped' && job.status !== 'error') {
      job.status = 'error'
      job.phase = 'error'
      job.message = `Python 进程异常退出（exit ${code}）。请检查「系统设置 → Python 路径」与后端依赖。`
      markTerminalLanes(job, 'error', job.progress)
      // The backend died before emitting DONE, so the renderer would wait
      // forever — push the terminal state explicitly.
      sendToRenderer(win, IPC_CHANNELS.ON_ERROR, {
        type: 'ERROR',
        jobId,
        platform,
        error: job.message,
        phase: 'error',
        recoverable: false,
      })
    }
    releaseSlotIfCurrent(currentBridge)
  })

  return currentBridge
}

export function registerJobHandlers(getMainWindow: () => BrowserWindow | null): void {
  ipcMain.handle(IPC_CHANNELS.JOB_START, async (_event, payload: StartJobPayload) => {
    checkRateLimit('job:start')

    const win = getMainWindow()
    if (!win) {
      throw new Error('No main window available.')
    }

    const rawAccountIds = payload.accountIds?.length ? payload.accountIds : []
    const accountIds = validateAccountIds(rawAccountIds)

    const totalGB = os.totalmem() / 1024 ** 3
    let baselineGB = 0
    try {
      const leftover = await measureProjectChromeGB(path.join(DATA_DIR, 'chrome-profiles'))
      baselineGB = Math.max(0, (await measureSystemUsedGB()) - leftover)
    } catch {
      baselineGB = (os.totalmem() - os.freemem()) / 1024 ** 3
    }
    const platform: Platform = payload.platform === 'zhihuishu' ? 'zhihuishu' : 'chaoxing'
    const basePlan = computeMemoryPlan(totalGB, baselineGB, os.cpus().length,
      getCurrentSettings().perAccountEstimateGB)
    if (basePlan.budgetGB < basePlan.perAccountEstimateGB) {
      throw new Error(`内存预算不足以运行一个浏览器实例（预算 ${basePlan.budgetGB.toFixed(1)}GB）。`)
    }

    // 同平台互斥、跨平台并行：另一平台的活跃任务不阻塞本平台启动。
    const occupant = jobSlots.occupant(platform)
    if (occupant) {
      throw new Error(`平台 ${platform} 的任务 ${occupant.jobId} 正在运行，请先停止该任务再启动同平台新任务。`)
    }

    // 双平台并行时的动态剩余分账：本任务预算 = 全局预算 − 其他平台已授予之和
    // （下限 1 账号；允许受控超卖，实际占用由两进程的全局测量闸门收敛）。
    const plan = allocateBudget(basePlan, jobSlots.grantedBudgetsExcluding(platform))

    const jobId = generateJobId()
    const now = new Date().toISOString()
    const courseIds = payload.courseIds ?? []
    // 仅内容 arrives as mode='solve_only' (the renderer maps batch-exec →
    // solve_only) + focus='content'. solve_only means quiz-only on the backend,
    // which combined with --content-only would skip BOTH phases. Override to
    // 'full' so the content phase actually runs and --content-only trims the quiz.
    const mode = payload.options?.focus === 'content' ? 'full' : (payload.mode ?? 'full')

    const jobStatus: JobStatus = {
      jobId,
      status: 'running',
      platform,
      phase: 'idle',
      phaseIndex: 0,
      progress: 0,
      message: 'Starting job.',
      startedAt: now,
      accountIds,
      courseIds,
      lanes: createInitialLanes(accountIds),
      memoryPlan: plan,
    }

    retainJob(jobId, jobStatus)
    const jobBridge = createBridgeAndBind(win, jobId, platform)
    jobSlots.acquire(platform, jobId, jobBridge, plan.budgetGB)

    const args: string[] = ['--job-id', jobId, '--accounts', accountIds.join(',')]
    if (mode) {
      args.push('--mode', mode)
    }
    if (courseIds.length > 0) {
      args.push('--courses', courseIds.join(','))
    }
    // "模拟运行" — solve/fill/AI-grade but never submit (backend grade_only).
    if (payload.options?.dryRun) {
      args.push('--grade-only')
    }
    // 仅内容: a full-mode run restricted to the content phase. (仅刷题 is
    // already expressed as mode='solve_only' by the renderer's mapMode.)
    if (payload.options?.focus === 'content') {
      args.push('--content-only')
    }
    args.push('--max-concurrent', String(plan.maxConcurrent),
              '--budget-gb', plan.budgetGB.toFixed(2),
              '--system-limit-gb', plan.systemLimitGB.toFixed(2),
              '--per-account-estimate-gb', String(plan.perAccountEstimateGB))

    try {
      jobBridge.start(args, jobId, platform)
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error)
      jobStatus.status = 'error'
      jobStatus.phase = 'error'
      jobStatus.message = message
      markTerminalLanes(jobStatus, 'error', 0)
      jobSlots.release(platform)
      throw new Error(`启动 Python 后端进程失败：${message}`)
    }

    return { jobId }
  })

  ipcMain.handle(IPC_CHANNELS.JOB_PAUSE, async (_event, jobId: string) => {
    checkRateLimit('job:pause')
    const job = getJobOrThrow(jobId)
    pauseWholeJob(job)
  })

  ipcMain.handle(IPC_CHANNELS.JOB_RESUME, async (_event, jobId: string) => {
    checkRateLimit('job:resume')
    const job = getJobOrThrow(jobId)
    resumeWholeJob(job)
  })

  ipcMain.handle(IPC_CHANNELS.JOB_STOP, async (_event, jobId: string) => {
    checkRateLimit('job:stop')
    const job = getJobOrThrow(jobId)
    stopWholeJob(job)
  })

  ipcMain.handle(IPC_CHANNELS.JOB_PAUSE_SELECTED, async (_event, payload: JobControlPayload) => {
    checkRateLimit('job:pause-selected')
    const { job, accountIds } = validateControlPayload(payload)
    if (accountIds.length === job.accountIds.length) {
      pauseWholeJob(job)
      return
    }
    return selectedControlUnsupported()
  })

  ipcMain.handle(IPC_CHANNELS.JOB_RESUME_SELECTED, async (_event, payload: JobControlPayload) => {
    checkRateLimit('job:resume-selected')
    const { job, accountIds } = validateControlPayload(payload)
    if (accountIds.length === job.accountIds.length) {
      resumeWholeJob(job)
      return
    }
    return selectedControlUnsupported()
  })

  ipcMain.handle(IPC_CHANNELS.JOB_STOP_SELECTED, async (_event, payload: JobControlPayload) => {
    checkRateLimit('job:stop-selected')
    const { job, accountIds } = validateControlPayload(payload)
    if (accountIds.length === job.accountIds.length) {
      stopWholeJob(job)
      return
    }
    return selectedControlUnsupported()
  })

  ipcMain.handle(IPC_CHANNELS.JOB_STATUS, async (_event, jobId?: string) => {
    // No id → the sole active job (legacy renderer query; with two platforms
    // running in parallel a jobId is required). A caller asking for an unknown
    // id gets a Chinese message instead of "Job undefined not found".
    const target = jobId ?? jobSlots.soleActiveSlot()?.jobId ?? undefined
    if (!target) {
      throw new Error(jobSlots.size > 1
        ? '当前有多个并行任务，查询时需指定 jobId。'
        : '当前没有可查询的任务。')
    }
    const job = jobs.get(target)
    if (!job) {
      throw new Error(`未找到任务 ${target}（可能已重启应用）。`)
    }
    return cloneJob(job)
  })

  ipcMain.handle(IPC_CHANNELS.JOB_RESOLVE_TICKET, async (_event, payload: ResolveTicketPayload) => {
    checkRateLimit('job:resolve-ticket')

    if (!payload || typeof payload.ticketId !== 'string' || !payload.ticketId) {
      throw new Error('A ticketId is required to resolve a ticket.')
    }
    if (typeof payload.accountId !== 'number' || !Number.isInteger(payload.accountId)) {
      throw new Error('A numeric accountId is required to resolve a ticket.')
    }
    if (payload.action !== 'skip' && typeof payload.answer !== 'string') {
      throw new Error('Either an answer or action: "skip" is required.')
    }

    // 双平台并行时按 jobId 路由到对应平台的 bridge；未携带 jobId 的旧载荷
    // 在恰好只有一个活跃任务时仍可送达（向后兼容）。
    const slot = (typeof payload.jobId === 'string' && payload.jobId
      ? jobSlots.getByJobId(payload.jobId)
      : jobSlots.soleActiveSlot())
    if (!slot || !slot.bridge.isRunning()) {
      throw new Error('No active Python process. The ticket cannot be resolved.')
    }

    slot.bridge.resolveTicket({
      ticketId: payload.ticketId,
      accountId: payload.accountId,
      answer: payload.answer,
      action: payload.action,
    })
  })
}

/**
 * Stop every active platform job during app shutdown (before-quit / quit).
 * 双平台并行时逐一停止所有槽位；每个槽位沿用原有的 STOP → 定时升级强杀链路。
 */
export function stopAllJobs(): void {
  for (const slot of jobSlots.activeSlots()) {
    stopSlotDuringQuit(slot)
  }
}

function stopSlotDuringQuit(slot: JobSlot): void {
  const { platform, jobId, bridge } = slot
  if (!bridge.isRunning()) {
    jobSlots.release(platform)
    return
  }

  bridge.stop()

  // Close the playwright-cli browser sessions for this job, for the same
  // reason as stopWholeJob: Chrome is the daemon's child, not Python's.
  const job = jobs.get(jobId)
  if (job) closeBrowserSessions(job.accountIds, job.platform ?? platform)

  let elapsedSeconds = 0
  const interval = setInterval(() => {
    elapsedSeconds += 1
    if (!bridge.isRunning() || elapsedSeconds >= 10) {
      clearInterval(interval)
      if (bridge.isRunning()) {
        const pid = (bridge as unknown as { process?: { pid?: number } }).process?.pid
        // taskkill is Windows-only; on other platforms the SIGKILL path in
        // PythonBridge.stop() already covers forced termination.
        if (pid && process.platform === 'win32') {
          try {
            execSync(`taskkill /f /pid ${pid} /t 2>nul`, { timeout: 5000 })
          } catch {
            // Ignore cleanup failures during shutdown.
          }
        }
      }
    }
  }, 1000)

  if (job) {
    job.status = 'stopped'
    job.phase = 'stopped'
    job.message = 'Job stopped during app shutdown.'
    job.finishedAt = new Date().toISOString()
    if (job.lanes?.length) {
      job.lanes = job.lanes.map((lane) =>
        lane.status === 'completed' ? lane : { ...lane, status: 'stopped', currentTask: 'Stopped' },
      )
    }
  }
  jobSlots.release(platform)
}
