import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import type {
  AccountLane,
  ExecutionStatus,
  JobHandle,
  LogLine,
  Platform,
  RuntimePhase,
  StartJobPayload,
} from '@/shared/lib/types'
import { isInteractiveTicket } from '@/shared/lib/platforms'
import { createApiClient } from '@/shared/lib/apiClient'
import { formatDuration } from '@/shared/lib/formatDuration'
import { useAttentionStore } from '@/app/stores/attention.store'
import { useLogStore } from '@/app/stores/log.store'
import { useCaptchaStore } from '@/app/stores/captcha.store'
import { useCourseStore } from '@/app/stores/course.store'
import { useMemoryStore } from '@/app/stores/memory.store'

const api = createApiClient()

export const useExecutionStore = defineStore('execution', () => {
  const status = ref<ExecutionStatus>('idle')
  const jobId = ref<string | null>(null)
  /** 当前任务所属平台（startJob 时记录；执行页徽标用）。 */
  const platform = ref<Platform | null>(null)
  const phaseIndex = ref(0)
  const lanes = ref<AccountLane[]>([])
  const phases = ref<RuntimePhase[]>([])
  const progress = ref(0)
  const error = ref<string | null>(null)
  const startTime = ref<number | null>(null)
  const endTime = ref<number | null>(null)
  const elapsedMs = ref(0)
  const selectedLaneIds = ref<Set<string>>(new Set())

  const laneElapsedMs = ref<Record<string, number>>({})
  const laneStartedAt = ref<Record<string, number | null>>({})

  let globalTick: ReturnType<typeof setInterval> | null = null
  let activeStartedAt: number | null = null
  let activeElapsedBase = 0
  const eventCleanupFns: Array<() => void> = []
  let refreshInFlight = false

  const isRunning = computed(() => status.value === 'running')
  const isPaused = computed(() => status.value === 'paused')
  const isIdle = computed(() => status.value === 'idle')
  const currentPhase = computed(() => phases.value[phaseIndex.value] ?? null)
  const elapsedFormatted = computed(() => formatDuration(elapsedMs.value))
  const selectedLaneCount = computed(() => selectedLaneIds.value.size)
  const allLanesSelected = computed(() => lanes.value.length > 0 && selectedLaneIds.value.size === lanes.value.length)

  function laneElapsed(accountId: string): number {
    return laneElapsedMs.value[accountId] ?? 0
  }

  function laneElapsedFormatted(accountId: string): string {
    return formatDuration(laneElapsed(accountId))
  }

  function syncGlobalElapsed(): void {
    elapsedMs.value = activeStartedAt ? activeElapsedBase + (Date.now() - activeStartedAt) : activeElapsedBase
  }

  function startTimer(): void {
    if (!startTime.value) startTime.value = Date.now()
    if (activeStartedAt) return
    activeStartedAt = Date.now()
    syncGlobalElapsed()
    if (globalTick) clearInterval(globalTick)
    globalTick = setInterval(syncGlobalElapsed, 1000)
  }

  function stopTimer(): void {
    if (activeStartedAt) {
      activeElapsedBase += Date.now() - activeStartedAt
      activeStartedAt = null
    }
    if (globalTick) {
      clearInterval(globalTick)
      globalTick = null
    }
    elapsedMs.value = activeElapsedBase
  }

  function startLaneTimer(accountId: string): void {
    if (laneStartedAt.value[accountId]) return
    laneStartedAt.value = { ...laneStartedAt.value, [accountId]: Date.now() }
  }

  function stopLaneTimer(accountId: string): void {
    const startedAt = laneStartedAt.value[accountId]
    if (!startedAt) return
    laneElapsedMs.value = {
      ...laneElapsedMs.value,
      [accountId]: (laneElapsedMs.value[accountId] ?? 0) + (Date.now() - startedAt),
    }
    laneStartedAt.value = { ...laneStartedAt.value, [accountId]: null }
  }

  function recomputeLaneElapsed(accountId: string): void {
    const startedAt = laneStartedAt.value[accountId]
    if (!startedAt) return
    laneElapsedMs.value = {
      ...laneElapsedMs.value,
      [accountId]: (laneElapsedMs.value[accountId] ?? 0) + (Date.now() - startedAt),
    }
    laneStartedAt.value = { ...laneStartedAt.value, [accountId]: Date.now() }
  }

  function startAllLaneTimers(): void {
    for (const lane of lanes.value) {
      if (lane.status === 'running') startLaneTimer(lane.accountId)
    }
  }

  function stopAllLaneTimers(): void {
    for (const lane of lanes.value) stopLaneTimer(lane.accountId)
  }

  function unregisterEventListeners(): void {
    // Each listener was registered with a precise removal fn in eventCleanupFns,
    // so pop them off one by one. We deliberately do NOT call api.dispose() here:
    // `api` is a singleton shared by all 5 stores, and (in mock mode) dispose()
    // stops the in-flight job simulation — which would kill the job we just
    // started, since startJob() → registerEventListeners() → unregisterEventListeners()
    // runs in the same frame as api.startJob().
    while (eventCleanupFns.length) {
      const cleanup = eventCleanupFns.pop()
      try { cleanup?.() } catch {}
    }
  }

  function handleTerminalStatus(nextStatus: ExecutionStatus): void {
    useMemoryStore().stop()
    status.value = nextStatus
    endTime.value = Date.now()
    stopTimer()
    stopAllLaneTimers()
    // Close out the phase stepper so a finished/stopped run never leaves a
    // step claiming "running" under a terminal banner.
    if (nextStatus === 'completed') {
      phases.value = phases.value.map((p) => ({ ...p, status: 'completed', progress: 100 }))
    } else if (nextStatus === 'error' || nextStatus === 'stopped') {
      phases.value = phases.value.map((p) =>
        p.status === 'running'
          ? { ...p, status: nextStatus === 'error' ? 'error' : 'stopped' }
          : p,
      )
    }
    // On failure/stop, lanes that never saw a backend event (e.g. the Python
    // process died at spawn) would otherwise keep claiming 运行中 under a
    // failed banner. Mark them terminal and surface the reason.
    if (nextStatus === 'error' || nextStatus === 'stopped') {
      lanes.value = lanes.value.map((lane) => {
        const active = lane.status === 'running' || lane.status === 'queued' || lane.status === 'paused'
        if (!active) return lane
        return {
          ...lane,
          status: nextStatus,
          errorMessage: nextStatus === 'error' ? (error.value ?? lane.errorMessage) : lane.errorMessage,
        }
      })
    }
    unregisterEventListeners()
  }

  /**
   * Backend PHASE events carry a phase NAME — never an index, and never in
   * the MODES vocabulary the stepper is built from. Map the name onto a
   * normalized 0..4 rank, scale it to this mode's step count, and advance the
   * stepper. Without this the stepper stays on step 0 forever.
   *
   * Phase vocabulary is shared across platforms: zhihuishu emits the subset
   * idle/login/scan_courses/completed (see platforms/zhihuishu/api.py
   * VALID_PHASES), chaoxing adds process_sections/solve_quiz mid-run.
   */
  function applyPhaseToSteps(phase: string): void {
    const PHASE_RANK: Record<string, number> = {
      login: 0,
      scan_courses: 0,
      process_sections: 3,
      solve_quiz: 3,
      completed: 4,
    }
    const rank = PHASE_RANK[phase]
    if (rank === undefined) return
    const count = phases.value.length
    if (!count) return
    const idx = Math.max(0, Math.min(count - 1, Math.round((rank / 4) * (count - 1))))
    phases.value = phases.value.map((p, i) => ({
      ...p,
      status: i < idx ? 'completed' : i === idx ? 'running' : p.status,
      progress: i < idx ? 100 : p.progress,
    }))
    phaseIndex.value = idx
  }

  function mergeHandle(handle: JobHandle): void {
    status.value = handle.status
    if (handle.platform) platform.value = handle.platform
    phaseIndex.value = handle.phaseIndex
    phases.value = handle.phases
    progress.value = handle.progress

    const previousById = new Map(lanes.value.map((lane) => [lane.accountId, lane]))
    lanes.value = handle.lanes

    for (const lane of lanes.value) {
      const previous = previousById.get(lane.accountId)
      if (lane.status === 'running' && previous?.status !== 'running') startLaneTimer(lane.accountId)
      if (previous?.status === 'running' && lane.status !== 'running') stopLaneTimer(lane.accountId)
    }

    for (const previous of previousById.values()) {
      if (!lanes.value.find((lane) => lane.accountId === previous.accountId)) stopLaneTimer(previous.accountId)
    }
  }

  function registerEventListeners(): void {
    unregisterEventListeners()

    const logStore = useLogStore()
    const attentionStore = useAttentionStore()
    const captchaStore = useCaptchaStore()

    eventCleanupFns.push(
      api.onProgress((event) => {
        if (event.jobId !== jobId.value) return
        // A per-course "Completed" event can carry 100% while the account still
        // has phases left (quiz done, content pending). Cap non-terminal events
        // at 99% until the account-level "DONE" arrives, so the banner does not
        // claim 100% prematurely. The final 100% comes from onCompleted.
        progress.value =
          event.percent >= 100 && !/^DONE/.test(event.message) ? 99 : event.percent
        if (typeof event.phaseIndex === 'number') phaseIndex.value = event.phaseIndex
        // The progress event carries no lane data, so the lane cards would never
        // move during a run. Pull the latest handle (which includes per-lane
        // progress/status) and merge it. Guarded so overlapping events don't
        // stack concurrent getJobStatus calls.
        if (!refreshInFlight) {
          refreshInFlight = true
          void refreshStatus().finally(() => {
            refreshInFlight = false
          })
        }
      }),
    )

    eventCleanupFns.push(
      api.onPhaseChange((event) => {
        if (event.jobId !== jobId.value) return
        if (typeof event.phaseIndex === 'number') phaseIndex.value = event.phaseIndex
        if (typeof event.toPhase === 'string') applyPhaseToSteps(event.toPhase)
      }),
    )

    eventCleanupFns.push(
      api.onLog((line) => {
        logStore.addLog((line.level as LogLine['level']) ?? 'info', line.message)
      }),
    )

    eventCleanupFns.push(
      api.onTicket((ticket) => {
        // Interactive tickets (captcha input / QR scan / slider hint) need the
        // modal; everything (including their resolved/timeout follow-ups) is
        // also archived in the attention queue for later review.
        if (isInteractiveTicket(ticket)) {
          captchaStore.ingest(ticket)
        }
        attentionStore.upsertTicket(ticket)
      }),
    )

    eventCleanupFns.push(
      api.onCompleted((event) => {
        if (event.jobId !== jobId.value) return
        if (event.success) {
          progress.value = 100
          // Reflect newly discovered courses back into the atlas. A scan_only
          // (or full) run rewrites output/discovered_courses_*.json; reload it
          // for every account this job touched so CourseAtlasView shows the
          // fresh list without the user re-triggering anything. Re-reading is
          // harmless for solve_only (file unchanged). Best-effort: a failed
          // reload must not break terminal handling.
          void reloadCoursesForJob()
        }
        handleTerminalStatus(event.success ? 'completed' : 'stopped')
      }),
    )

    eventCleanupFns.push(
      api.onError((event) => {
        if (event.jobId !== jobId.value) return
        error.value = event.error
        if (!event.recoverable) handleTerminalStatus('error')
      }),
    )
  }

  function toggleLaneSelection(accountId: string): void {
    const next = new Set(selectedLaneIds.value)
    if (next.has(accountId)) next.delete(accountId)
    else next.add(accountId)
    selectedLaneIds.value = next
  }

  function selectAllLanes(): void {
    selectedLaneIds.value = new Set(lanes.value.map((lane) => lane.accountId))
  }

  function deselectAllLanes(): void {
    selectedLaneIds.value = new Set()
  }

  async function startJob(payload: StartJobPayload): Promise<void> {
    status.value = 'running'
    error.value = null
    platform.value = payload.platform ?? 'chaoxing'
    selectedLaneIds.value = new Set()
    activeElapsedBase = 0
    elapsedMs.value = 0
    startTime.value = Date.now()
    endTime.value = null
    laneElapsedMs.value = {}
    laneStartedAt.value = {}
    stopTimer()
    stopAllLaneTimers()

    try {
      const handle = await api.startJob(payload)
      jobId.value = handle.jobId
      mergeHandle(handle)
      useMemoryStore().start()
      registerEventListeners()
      startTimer()
      startAllLaneTimers()
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to start job'
      // A synchronous job:start failure (bad interpreter, memory budget,
      // duplicate job) only flips the banner — if the user is on another
      // view it's invisible. Write the reason to the log console too.
      void Promise.all([
        import('@/shared/lib/apiClient'),
        import('@/app/stores/log.store'),
      ])
        .then(([{ stripInvokeErrorPrefix }, { useLogStore }]) => {
          useLogStore().addLog(
            'error',
            `任务启动失败：${stripInvokeErrorPrefix(String(error.value))}`,
            '执行',
          )
        })
        .catch(() => { /* log store unavailable in early boot */ })
      handleTerminalStatus('error')
    }
  }

  async function pauseJob(accountIds?: string[]): Promise<void> {
    if (!jobId.value) return
    try {
      await api.pauseJob(jobId.value, accountIds)
      if (accountIds?.length) {
        for (const accountId of accountIds) stopLaneTimer(accountId)
      } else {
        stopTimer()
        stopAllLaneTimers()
        status.value = 'paused'
      }
      await refreshStatus()
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to pause job'
    }
  }

  async function resumeJob(): Promise<void> {
    if (!jobId.value) return
    try {
      await api.resumeJob(jobId.value)
      startTimer()
      await refreshStatus()
      startAllLaneTimers()
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to resume job'
    }
  }

  async function resumeSelectedLanes(): Promise<void> {
    if (!jobId.value) return
    const accountIds = lanes.value
      .filter((lane) => selectedLaneIds.value.has(lane.accountId) && lane.status === 'paused')
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.resumeSelected(jobId.value, accountIds)
      await refreshStatus()
      for (const accountId of accountIds) startLaneTimer(accountId)
      if (lanes.value.some((lane) => lane.status === 'running')) startTimer()
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to resume selected lanes'
    }
  }

  async function pauseSelectedLanes(): Promise<void> {
    if (!jobId.value) return
    const accountIds = lanes.value
      .filter((lane) => selectedLaneIds.value.has(lane.accountId) && lane.status === 'running')
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.pauseSelected(jobId.value, accountIds)
      for (const accountId of accountIds) stopLaneTimer(accountId)
      await refreshStatus()
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to pause selected lanes'
    }
  }

  async function stopJob(accountIds?: string[]): Promise<void> {
    if (!jobId.value) return
    try {
      await api.stopJob(jobId.value, accountIds)
      await refreshStatus()
      if (!accountIds?.length) {
        selectedLaneIds.value = new Set()
        handleTerminalStatus('stopped')
      }
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to stop job'
    }
  }

  async function stopSelectedLanes(): Promise<void> {
    if (!jobId.value) return
    const accountIds = lanes.value
      .filter((lane) => selectedLaneIds.value.has(lane.accountId) && ['running', 'paused', 'pending'].includes(lane.status))
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.stopSelected(jobId.value, accountIds)
      for (const accountId of accountIds) stopLaneTimer(accountId)
      await refreshStatus()
      const activeLaneExists = lanes.value.some((lane) => ['running', 'paused', 'pending'].includes(lane.status))
      if (!activeLaneExists) handleTerminalStatus('stopped')
    } catch (cause: any) {
      error.value = cause?.message ?? 'Failed to stop selected lanes'
    }
  }

  async function refreshStatus(): Promise<void> {
    if (!jobId.value) return
    const handle = await api.getJobStatus(jobId.value)
    mergeHandle(handle)
    useMemoryStore().setPlan(handle.memoryPlan ?? null)
    if (handle.status === 'completed') handleTerminalStatus('completed')
    if (handle.status === 'stopped') handleTerminalStatus('stopped')
    if (handle.status === 'error') handleTerminalStatus('error')
    if (handle.status === 'running') startTimer()
    if (handle.status === 'paused') stopTimer()
    for (const lane of lanes.value) {
      if (lane.status === 'running') recomputeLaneElapsed(lane.accountId)
    }
  }

  // After a job completes, pull the freshly-persisted discovery state into the
  // course atlas. scanCourses() just re-reads discovered_courses_*.json (no
  // browser), so this is a cheap per-account file read. Each call is independent
  // and best-effort — a single account's failure is swallowed by the store.
  async function reloadCoursesForJob(): Promise<void> {
    const accountIds = [...new Set(lanes.value.map((lane) => lane.accountId))]
    if (!accountIds.length) return
    const courseStore = useCourseStore()
    await Promise.all(accountIds.map((id) => courseStore.scanCourses(id)))
  }

  function reset(): void {
    useMemoryStore().stop()
    useMemoryStore().setPlan(null)
    unregisterEventListeners()
    stopTimer()
    stopAllLaneTimers()
    status.value = 'idle'
    jobId.value = null
    platform.value = null
    phaseIndex.value = 0
    lanes.value = []
    phases.value = []
    progress.value = 0
    error.value = null
    startTime.value = null
    endTime.value = null
    elapsedMs.value = 0
    selectedLaneIds.value = new Set()
    laneElapsedMs.value = {}
    laneStartedAt.value = {}
    activeElapsedBase = 0
    activeStartedAt = null
  }

  return {
    status,
    jobId,
    platform,
    phaseIndex,
    lanes,
    phases,
    progress,
    error,
    startTime,
    endTime,
    elapsedMs,
    selectedLaneIds,
    laneElapsedMs,
    isRunning,
    isPaused,
    isIdle,
    currentPhase,
    elapsedFormatted,
    selectedLaneCount,
    allLanesSelected,
    laneElapsed,
    laneElapsedFormatted,
    toggleLaneSelection,
    selectAllLanes,
    deselectAllLanes,
    startJob,
    pauseJob,
    resumeJob,
    stopJob,
    pauseSelectedLanes,
    resumeSelectedLanes,
    stopSelectedLanes,
    refreshStatus,
    reset,
    startLaneTimer,
    stopLaneTimer,
    startAllLaneTimers,
    stopAllLaneTimers,
  }
})
