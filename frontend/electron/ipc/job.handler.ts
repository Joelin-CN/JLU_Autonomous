import { ipcMain, BrowserWindow, Notification } from 'electron'
import { execSync, execFile } from 'child_process'
import os from 'os'
import path from 'path'
import { PythonBridge } from '../python/pythonBridge'
import { DATA_DIR } from '../backendPath'
import { getCurrentSettings } from './status.handler'
import { setJobActive } from './jobState'
import {
  computeMemoryPlan,
  measureProjectChromeGB,
  measureSystemUsedGB,
} from '../memory/planner'
import type {
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

let activeJobId: string | null = null
let bridge: PythonBridge | null = null

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
 * Clear the global bridge/job state only when the event belongs to the
 * currently active bridge. A previous job's Python process can still emit
 * exit/error events after a new job has been started; without this guard the
 * stale event would null out the new job's bridge and active flag.
 */
function clearActiveJobIfCurrent(current: PythonBridge | null): void {
  if (!current || bridge !== current) return
  bridge = null
  activeJobId = null
  setJobActive(false)
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
function closeBrowserSessions(accountIds: number[]): void {
  const cli = process.platform === 'win32' ? 'playwright-cli.cmd' : 'playwright-cli'
  for (const id of accountIds) {
    try {
      // .cmd wrappers need shell:true on Windows; without it the close was
      // silently failing and Chrome lingered in Task Manager after every stop.
      execFile(cli, [`-s=chaoxing-chrome-${id}`, 'close'], { shell: true, timeout: 20000 }, () => {
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
  if (bridge?.isRunning()) {
    bridge.pause()
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
  if (!bridge) {
    throw new Error('No active Python process. The job cannot be resumed.')
  }

  bridge.resume()
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
  const stoppedBridge = bridge
  if (stoppedBridge?.isRunning()) {
    stoppedBridge.stop()
  }

  // The visible Chrome is a child of the playwright-cli *daemon*, not of the
  // Python process — so killing Python (even tree-kill) never reaps it. The
  // only thing that closes it is `playwright-cli -s=<session> close`. Python's
  // own finally-block close is best-effort and often skipped when STOP escalates
  // to SIGTERM before a check_signals() checkpoint is reached, so close the
  // sessions here too. Idempotent: closing an already-gone session is a no-op.
  closeBrowserSessions(job.accountIds)

  job.status = 'stopped'
  job.phase = 'stopped'
  job.message = 'Job stopped.'
  job.finishedAt = new Date().toISOString()
  if (job.lanes?.length) {
    job.lanes = job.lanes.map((lane) =>
      lane.status === 'completed' ? lane : { ...lane, status: 'stopped', currentTask: 'Stopped' },
    )
  }

  clearActiveJobIfCurrent(stoppedBridge)
}

function createBridgeAndBind(win: BrowserWindow, jobId: string): PythonBridge {
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

    sendToRenderer(win, IPC_CHANNELS.ON_PROGRESS, event)
  })

  currentBridge.on('memory', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_MEMORY, event)
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

    sendToRenderer(win, IPC_CHANNELS.ON_PHASE_CHANGE, event)
  })

  currentBridge.on('log', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_LOG, event)
  })

  currentBridge.on('ticket', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_TICKET, event)
  })

  currentBridge.on('error', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    job.status = 'error'
    job.message = event.error
    job.phase = (event.phase as JobStatus['phase']) ?? 'error'
    markTerminalLanes(job, 'error', job.progress)
    if (bridge === currentBridge) setJobActive(false)
    if (getCurrentSettings().notifications) {
      new Notification({ title: '超星助手', body: `任务异常：${event.error}` }).show()
    }
    sendToRenderer(win, IPC_CHANNELS.ON_ERROR, event)
  })

  currentBridge.on('done', (event) => {
    const job = jobs.get(jobId)
    if (!job) return

    // The backend emits ERROR followed by DONE on failure. Once the job is in
    // the error state, DONE must not flip it back to "completed".
    if (job.status === 'error' || job.status === 'stopped') {
      clearActiveJobIfCurrent(currentBridge)
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
      new Notification({ title: '超星助手', body: '任务已全部完成。' }).show()
    }

    sendToRenderer(win, IPC_CHANNELS.ON_COMPLETED, event)
    clearActiveJobIfCurrent(currentBridge)
  })

  currentBridge.on('result', (event) => {
    sendToRenderer(win, IPC_CHANNELS.ON_RESULT, event)
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
        error: job.message,
        phase: 'error',
        recoverable: false,
      })
    }
    clearActiveJobIfCurrent(currentBridge)
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
    const plan = computeMemoryPlan(totalGB, baselineGB, os.cpus().length,
      getCurrentSettings().perAccountEstimateGB)
    if (plan.budgetGB < plan.perAccountEstimateGB) {
      throw new Error(`内存预算不足以运行一个浏览器实例（预算 ${plan.budgetGB.toFixed(1)}GB）。`)
    }

    if (activeJobId) {
      throw new Error(`任务 ${activeJobId} 正在运行，请先停止再启动新任务。`)
    }

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
    activeJobId = jobId
    bridge = createBridgeAndBind(win, jobId)

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
      bridge.start(args, jobId)
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error)
      jobStatus.status = 'error'
      jobStatus.phase = 'error'
      jobStatus.message = message
      markTerminalLanes(jobStatus, 'error', 0)
      activeJobId = null
      bridge = null
      throw new Error(`启动 Python 后端进程失败：${message}`)
    }

    setJobActive(true)

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
    // No id → the active job (the common renderer query). A caller asking for
    // an unknown id gets a Chinese message instead of "Job undefined not found".
    const target = jobId ?? activeJobId ?? undefined
    if (!target) {
      throw new Error('当前没有可查询的任务。')
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

    if (!bridge?.isRunning()) {
      throw new Error('No active Python process. The ticket cannot be resolved.')
    }

    bridge.resolveTicket({
      ticketId: payload.ticketId,
      accountId: payload.accountId,
      answer: payload.answer,
      action: payload.action,
    })
  })
}

export function stopActiveJob(): void {
  if (!bridge || !bridge.isRunning()) {
    activeJobId = null
    bridge = null
    return
  }

  bridge.stop()

  // Close the playwright-cli browser sessions for whatever job is active, for
  // the same reason as stopWholeJob: Chrome is the daemon's child, not Python's.
  if (activeJobId) {
    const activeJob = jobs.get(activeJobId)
    if (activeJob) closeBrowserSessions(activeJob.accountIds)
  }

  let elapsedSeconds = 0
  const interval = setInterval(() => {
    elapsedSeconds += 1
    if (!bridge || !bridge.isRunning() || elapsedSeconds >= 10) {
      clearInterval(interval)
      if (bridge && bridge.isRunning()) {
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
      bridge = null
    }
  }, 1000)

  if (activeJobId) {
    const job = jobs.get(activeJobId)
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
    activeJobId = null
  }
  setJobActive(false)
}
