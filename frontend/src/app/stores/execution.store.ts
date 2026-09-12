import { computed, reactive } from 'vue'
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
import { PLATFORMS, isInteractiveTicket } from '@/shared/lib/platforms'
import { createApiClient } from '@/shared/lib/apiClient'
import { formatDuration } from '@/shared/lib/formatDuration'
import { useAttentionStore } from '@/app/stores/attention.store'
import { useLogStore } from '@/app/stores/log.store'
import { useCaptchaStore } from '@/app/stores/captcha.store'
import { useCourseStore } from '@/app/stores/course.store'
import { useMemoryStore } from '@/app/stores/memory.store'

const api = createApiClient()

/** 平台执行槽位 —— 双平台并行时每个平台一份独立的任务状态/泳道/计时。 */
export interface ExecutionSlot {
  platform: Platform
  jobId: string | null
  status: ExecutionStatus
  phaseIndex: number
  lanes: AccountLane[]
  phases: RuntimePhase[]
  progress: number
  error: string | null
  startTime: number | null
  endTime: number | null
  elapsedMs: number
  selectedLaneIds: Set<string>
  /** 泳道计时（键 = accountId；分槽持有，跨平台同号账号天然不撞）。 */
  laneElapsedMs: Record<string, number>
  laneStartedAt: Record<string, number | null>
}

function createSlot(platform: Platform): ExecutionSlot {
  return {
    platform,
    jobId: null,
    status: 'idle',
    phaseIndex: 0,
    lanes: [],
    phases: [],
    progress: 0,
    error: null,
    startTime: null,
    endTime: null,
    elapsedMs: 0,
    selectedLaneIds: new Set(),
    laneElapsedMs: {},
    laneStartedAt: {},
  }
}

export const useExecutionStore = defineStore('execution', () => {
  const slots = reactive({
    chaoxing: createSlot('chaoxing'),
    zhihuishu: createSlot('zhihuishu'),
  } as Record<Platform, ExecutionSlot>)

  // 非响应式计时基线（每平台一组；tick 里折叠进 slot.elapsedMs）
  const timerBase: Record<Platform, { activeStartedAt: number | null; activeElapsedBase: number }> = {
    chaoxing: { activeStartedAt: null, activeElapsedBase: 0 },
    zhihuishu: { activeStartedAt: null, activeElapsedBase: 0 },
  }
  let globalTick: ReturnType<typeof setInterval> | null = null
  let listenersRegistered = false
  const eventCleanupFns: Array<() => void> = []
  const refreshInFlight = new Set<Platform>()

  // ── 查询 ──
  const isRunning = computed(() => PLATFORMS.some((p) => slots[p].status === 'running'))
  const isIdle = computed(() => PLATFORMS.every((p) => slots[p].status === 'idle'))
  const runningPlatforms = computed(() => PLATFORMS.filter((p) => slots[p].status === 'running'))

  function slotOf(platform: Platform): ExecutionSlot {
    return slots[platform]
  }

  /** 该平台是否有活跃任务（同平台互斥的 UI 侧判定）。 */
  function isRunningOn(platform: Platform): boolean {
    return slots[platform].status === 'running'
  }

  /** 有数据可展示的槽（运行/暂停/终态未清）。 */
  const visibleSlots = computed(() =>
    PLATFORMS.map((p) => slots[p]).filter((slot) => slot.status !== 'idle'),
  )

  function anySlotRunning(exclude?: Platform): boolean {
    return PLATFORMS.some((p) => p !== exclude && slots[p].status === 'running')
  }

  function slotByJobId(jobId: string | null | undefined): ExecutionSlot | null {
    if (!jobId) return null
    for (const p of PLATFORMS) {
      if (slots[p].jobId === jobId) return slots[p]
    }
    return null
  }

  function laneElapsed(platform: Platform, accountId: string): number {
    return slots[platform].laneElapsedMs[accountId] ?? 0
  }

  function laneElapsedFormatted(platform: Platform, accountId: string): string {
    return formatDuration(laneElapsed(platform, accountId))
  }

  function elapsedFormattedOf(platform: Platform): string {
    return formatDuration(slots[platform].elapsedMs)
  }

  // ── 计时 ──
  function syncSlotElapsed(platform: Platform): void {
    const base = timerBase[platform]
    slots[platform].elapsedMs = base.activeStartedAt
      ? base.activeElapsedBase + (Date.now() - base.activeStartedAt)
      : base.activeElapsedBase
  }

  function ensureGlobalTick(): void {
    if (globalTick) return
    globalTick = setInterval(() => {
      for (const p of PLATFORMS) {
        if (timerBase[p].activeStartedAt) syncSlotElapsed(p)
      }
      if (!PLATFORMS.some((p) => timerBase[p].activeStartedAt) && globalTick) {
        clearInterval(globalTick)
        globalTick = null
      }
    }, 1000)
  }

  function startSlotTimer(slot: ExecutionSlot): void {
    if (!slot.startTime) slot.startTime = Date.now()
    const base = timerBase[slot.platform]
    if (base.activeStartedAt) return
    base.activeStartedAt = Date.now()
    syncSlotElapsed(slot.platform)
    ensureGlobalTick()
  }

  function stopSlotTimer(slot: ExecutionSlot): void {
    const base = timerBase[slot.platform]
    if (base.activeStartedAt) {
      base.activeElapsedBase += Date.now() - base.activeStartedAt
      base.activeStartedAt = null
    }
    syncSlotElapsed(slot.platform)
  }

  function startLaneTimer(slot: ExecutionSlot, accountId: string): void {
    if (slot.laneStartedAt[accountId]) return
    slot.laneStartedAt = { ...slot.laneStartedAt, [accountId]: Date.now() }
  }

  function stopLaneTimer(slot: ExecutionSlot, accountId: string): void {
    const startedAt = slot.laneStartedAt[accountId]
    if (!startedAt) return
    slot.laneElapsedMs = {
      ...slot.laneElapsedMs,
      [accountId]: (slot.laneElapsedMs[accountId] ?? 0) + (Date.now() - startedAt),
    }
    slot.laneStartedAt = { ...slot.laneStartedAt, [accountId]: null }
  }

  function recomputeLaneElapsed(slot: ExecutionSlot, accountId: string): void {
    const startedAt = slot.laneStartedAt[accountId]
    if (!startedAt) return
    slot.laneElapsedMs = {
      ...slot.laneElapsedMs,
      [accountId]: (slot.laneElapsedMs[accountId] ?? 0) + (Date.now() - startedAt),
    }
    slot.laneStartedAt = { ...slot.laneStartedAt, [accountId]: Date.now() }
  }

  function startAllLaneTimers(slot: ExecutionSlot): void {
    for (const lane of slot.lanes) {
      if (lane.status === 'running') startLaneTimer(slot, lane.accountId)
    }
  }

  function stopAllLaneTimers(slot: ExecutionSlot): void {
    for (const lane of slot.lanes) stopLaneTimer(slot, lane.accountId)
  }

  // ── 事件监听（一次注册、按 jobId 路由到对应槽）──
  function registerEventListeners(): void {
    if (listenersRegistered) return
    listenersRegistered = true

    const logStore = useLogStore()
    const attentionStore = useAttentionStore()
    const captchaStore = useCaptchaStore()

    eventCleanupFns.push(
      api.onProgress((event) => {
        const slot = slotByJobId(event.jobId)
        if (!slot) return
        // A per-course "Completed" event can carry 100% while the account still
        // has phases left (quiz done, content pending). Cap non-terminal events
        // at 99% until the account-level "DONE" arrives, so the banner does not
        // claim 100% prematurely. The final 100% comes from onCompleted.
        slot.progress =
          event.percent >= 100 && !/^DONE/.test(event.message) ? 99 : event.percent
        if (typeof event.phaseIndex === 'number') slot.phaseIndex = event.phaseIndex
        // The progress event carries no lane data, so the lane cards would never
        // move during a run. Pull the latest handle (which includes per-lane
        // progress/status) and merge it. Guarded so overlapping events don't
        // stack concurrent getJobStatus calls.
        if (!refreshInFlight.has(slot.platform)) {
          refreshInFlight.add(slot.platform)
          void refreshStatus(slot.platform)
            .catch(() => { /* 同平台新任务已替换旧仿真：迟到的刷新忽略 */ })
            .finally(() => {
              refreshInFlight.delete(slot.platform)
            })
        }
      }),
    )

    eventCleanupFns.push(
      api.onPhaseChange((event) => {
        const slot = slotByJobId(event.jobId)
        if (!slot) return
        if (typeof event.phaseIndex === 'number') slot.phaseIndex = event.phaseIndex
        if (typeof event.toPhase === 'string') applyPhaseToSteps(slot, event.toPhase)
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
        const slot = slotByJobId(event.jobId)
        if (!slot) return
        if (event.success) {
          slot.progress = 100
          // Reflect newly discovered courses back into the atlas (the job's own
          // platform bucket — NOT the UI's current platform). A scan_only (or
          // full) run rewrites output/discovered_courses_*.json; reload it for
          // every account this job touched. Best-effort: a failed reload must
          // not break terminal handling.
          void reloadCoursesForJob(slot)
        }
        handleTerminalStatus(slot, event.success ? 'completed' : 'stopped')
      }),
    )

    eventCleanupFns.push(
      api.onError((event) => {
        const slot = slotByJobId(event.jobId)
        if (!slot) return
        slot.error = event.error
        if (!event.recoverable) handleTerminalStatus(slot, 'error')
      }),
    )
  }

  function unregisterEventListeners(): void {
    while (eventCleanupFns.length) {
      const cleanup = eventCleanupFns.pop()
      try { cleanup?.() } catch {}
    }
    listenersRegistered = false
  }

  function handleTerminalStatus(slot: ExecutionSlot, nextStatus: ExecutionStatus): void {
    // 内存订阅只在「没有任何平台任务在跑」时停 —— 双平台并行时另一路的
    // MEMORY 事件仍需送达。
    if (!anySlotRunning()) useMemoryStore().stop()
    slot.status = nextStatus
    slot.endTime = Date.now()
    stopSlotTimer(slot)
    stopAllLaneTimers(slot)
    // Close out the phase stepper so a finished/stopped run never leaves a
    // step claiming "running" under a terminal banner.
    if (nextStatus === 'completed') {
      slot.phases = slot.phases.map((p) => ({ ...p, status: 'completed', progress: 100 }))
    } else if (nextStatus === 'error' || nextStatus === 'stopped') {
      slot.phases = slot.phases.map((p) =>
        p.status === 'running'
          ? { ...p, status: nextStatus === 'error' ? 'error' : 'stopped' }
          : p,
      )
    }
    // On failure/stop, lanes that never saw a backend event (e.g. the Python
    // process died at spawn) would otherwise keep claiming 运行中 under a
    // failed banner. Mark them terminal and surface the reason.
    if (nextStatus === 'error' || nextStatus === 'stopped') {
      slot.lanes = slot.lanes.map((lane) => {
        const active = lane.status === 'running' || lane.status === 'queued' || lane.status === 'paused'
        if (!active) return lane
        return {
          ...lane,
          status: nextStatus,
          errorMessage: nextStatus === 'error' ? (slot.error ?? lane.errorMessage) : lane.errorMessage,
        }
      })
    }
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
  function applyPhaseToSteps(slot: ExecutionSlot, phase: string): void {
    const PHASE_RANK: Record<string, number> = {
      login: 0,
      scan_courses: 0,
      process_sections: 3,
      solve_quiz: 3,
      completed: 4,
    }
    const rank = PHASE_RANK[phase]
    if (rank === undefined) return
    const count = slot.phases.length
    if (!count) return
    const idx = Math.max(0, Math.min(count - 1, Math.round((rank / 4) * (count - 1))))
    slot.phases = slot.phases.map((p, i) => ({
      ...p,
      status: i < idx ? 'completed' : i === idx ? 'running' : p.status,
      progress: i < idx ? 100 : p.progress,
    }))
    slot.phaseIndex = idx
  }

  function mergeHandle(slot: ExecutionSlot, handle: JobHandle): void {
    slot.status = handle.status
    slot.phaseIndex = handle.phaseIndex
    slot.phases = handle.phases
    slot.progress = handle.progress

    const previousById = new Map(slot.lanes.map((lane) => [lane.accountId, lane]))
    slot.lanes = handle.lanes

    for (const lane of slot.lanes) {
      const previous = previousById.get(lane.accountId)
      if (lane.status === 'running' && previous?.status !== 'running') startLaneTimer(slot, lane.accountId)
      if (previous?.status === 'running' && lane.status !== 'running') stopLaneTimer(slot, lane.accountId)
    }

    for (const previous of previousById.values()) {
      if (!slot.lanes.find((lane) => lane.accountId === previous.accountId)) stopLaneTimer(slot, previous.accountId)
    }
  }

  // ── 选择（按槽）──
  function toggleLaneSelection(platform: Platform, accountId: string): void {
    const slot = slots[platform]
    const next = new Set(slot.selectedLaneIds)
    if (next.has(accountId)) next.delete(accountId)
    else next.add(accountId)
    slot.selectedLaneIds = next
  }

  function selectAllLanes(platform: Platform): void {
    slots[platform].selectedLaneIds = new Set(slots[platform].lanes.map((lane) => lane.accountId))
  }

  function deselectAllLanes(platform: Platform): void {
    slots[platform].selectedLaneIds = new Set()
  }

  // ── 任务生命周期 ──
  async function startJob(payload: StartJobPayload): Promise<void> {
    const platform: Platform = payload.platform ?? 'chaoxing'
    const slot = slots[platform]
    slot.status = 'running'
    slot.error = null
    slot.selectedLaneIds = new Set()
    timerBase[platform] = { activeStartedAt: null, activeElapsedBase: 0 }
    slot.elapsedMs = 0
    slot.startTime = Date.now()
    slot.endTime = null
    slot.laneElapsedMs = {}
    slot.laneStartedAt = {}

    try {
      const handle = await api.startJob(payload)
      slot.jobId = handle.jobId
      mergeHandle(slot, handle)
      useMemoryStore().start()
      registerEventListeners()
      startSlotTimer(slot)
      startAllLaneTimers(slot)
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to start job'
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
            `任务启动失败：${stripInvokeErrorPrefix(String(slot.error))}`,
            '执行',
          )
        })
        .catch(() => { /* log store unavailable in early boot */ })
      handleTerminalStatus(slot, 'error')
    }
  }

  async function pauseJob(platform: Platform, accountIds?: string[]): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    try {
      await api.pauseJob(slot.jobId, accountIds)
      if (accountIds?.length) {
        for (const accountId of accountIds) stopLaneTimer(slot, accountId)
      } else {
        stopSlotTimer(slot)
        stopAllLaneTimers(slot)
        slot.status = 'paused'
      }
      await refreshStatus(platform)
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to pause job'
    }
  }

  async function resumeJob(platform: Platform): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    try {
      await api.resumeJob(slot.jobId)
      startSlotTimer(slot)
      await refreshStatus(platform)
      startAllLaneTimers(slot)
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to resume job'
    }
  }

  async function resumeSelectedLanes(platform: Platform): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    const accountIds = slot.lanes
      .filter((lane) => slot.selectedLaneIds.has(lane.accountId) && lane.status === 'paused')
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.resumeSelected(slot.jobId, accountIds)
      await refreshStatus(platform)
      for (const accountId of accountIds) startLaneTimer(slot, accountId)
      if (slot.lanes.some((lane) => lane.status === 'running')) startSlotTimer(slot)
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to resume selected lanes'
    }
  }

  async function pauseSelectedLanes(platform: Platform): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    const accountIds = slot.lanes
      .filter((lane) => slot.selectedLaneIds.has(lane.accountId) && lane.status === 'running')
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.pauseSelected(slot.jobId, accountIds)
      for (const accountId of accountIds) stopLaneTimer(slot, accountId)
      await refreshStatus(platform)
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to pause selected lanes'
    }
  }

  async function stopJob(platform: Platform, accountIds?: string[]): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    try {
      await api.stopJob(slot.jobId, accountIds)
      await refreshStatus(platform)
      if (!accountIds?.length) {
        slot.selectedLaneIds = new Set()
        handleTerminalStatus(slot, 'stopped')
      }
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to stop job'
    }
  }

  async function stopSelectedLanes(platform: Platform): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    const accountIds = slot.lanes
      .filter((lane) => slot.selectedLaneIds.has(lane.accountId) && ['running', 'paused', 'pending'].includes(lane.status))
      .map((lane) => lane.accountId)

    if (!accountIds.length) return

    try {
      await api.stopSelected(slot.jobId, accountIds)
      for (const accountId of accountIds) stopLaneTimer(slot, accountId)
      await refreshStatus(platform)
      const activeLaneExists = slot.lanes.some((lane) => ['running', 'paused', 'pending'].includes(lane.status))
      if (!activeLaneExists) handleTerminalStatus(slot, 'stopped')
    } catch (cause: any) {
      slot.error = cause?.message ?? 'Failed to stop selected lanes'
    }
  }

  async function refreshStatus(platform: Platform): Promise<void> {
    const slot = slots[platform]
    if (!slot.jobId) return
    const handle = await api.getJobStatus(slot.jobId)
    mergeHandle(slot, handle)
    useMemoryStore().setPlan(platform, handle.memoryPlan ?? null)
    if (handle.status === 'completed') handleTerminalStatus(slot, 'completed')
    if (handle.status === 'stopped') handleTerminalStatus(slot, 'stopped')
    if (handle.status === 'error') handleTerminalStatus(slot, 'error')
    if (handle.status === 'running') startSlotTimer(slot)
    if (handle.status === 'paused') stopSlotTimer(slot)
    for (const lane of slot.lanes) {
      if (lane.status === 'running') recomputeLaneElapsed(slot, lane.accountId)
    }
  }

  // After a job completes, pull the freshly-persisted discovery state into the
  // course atlas — into the JOB's platform bucket (scanCourses re-reads
  // discovered_courses_*.json per platform; no browser involved).
  async function reloadCoursesForJob(slot: ExecutionSlot): Promise<void> {
    const accountIds = [...new Set(slot.lanes.map((lane) => lane.accountId))]
    if (!accountIds.length) return
    const courseStore = useCourseStore()
    await Promise.all(accountIds.map((id) => courseStore.scanCourses(id, slot.platform)))
  }

  /** 清空指定平台的执行槽（终态后的「关闭」）；无参 = 全部清空。 */
  function reset(platform?: Platform): void {
    const targets = platform ? [platform] : PLATFORMS
    for (const p of targets) {
      const slot = slots[p]
      stopSlotTimer(slot)
      stopAllLaneTimers(slot)
      timerBase[p] = { activeStartedAt: null, activeElapsedBase: 0 }
      const fresh = createSlot(p)
      Object.assign(slot, fresh)
    }
    if (!PLATFORMS.some((p) => slots[p].status !== 'idle')) {
      useMemoryStore().stop()
      useMemoryStore().setPlan(null)
    }
  }

  return {
    slots,
    slotOf,
    visibleSlots,
    runningPlatforms,
    isRunning,
    isIdle,
    isRunningOn,
    slotByJobId,
    laneElapsed,
    laneElapsedFormatted,
    elapsedFormattedOf,
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
    registerEventListeners,
    unregisterEventListeners,
  }
})
