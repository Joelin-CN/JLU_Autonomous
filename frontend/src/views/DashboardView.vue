<template>
  <div class="dash">
    <div class="stats-grid">
      <GlassmorphicCard class="stat-card" padding="16px 20px">
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--accent">👥</span>
          <div>
            <div class="stat-value stat-value--accent">{{ totalAccountCount }}</div>
            <div class="stat-label">账号总数</div>
            <div class="stat-sub">{{ accountBreakdown }}</div>
          </div>
        </div>
      </GlassmorphicCard>

      <GlassmorphicCard class="stat-card" padding="16px 20px">
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--gold">⏳</span>
          <div>
            <div class="stat-value stat-value--gold">{{ runningCount }}</div>
            <div class="stat-label">运行中账号</div>
            <div class="stat-sub">{{ runningPlatformLabel }}</div>
          </div>
        </div>
      </GlassmorphicCard>

      <GlassmorphicCard class="stat-card" padding="16px 20px">
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--ok">✓</span>
          <div>
            <div class="stat-value stat-value--ok">{{ doneCount }}</div>
            <div class="stat-label">完成课程</div>
            <div class="stat-sub">{{ doneBreakdown }}</div>
          </div>
        </div>
      </GlassmorphicCard>

      <GlassmorphicCard class="stat-card" padding="16px 20px">
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--warn">⚠</span>
          <div>
            <div class="stat-value stat-value--warn">{{ attentionStore.unresolvedCount }}</div>
            <div class="stat-label">待关注事项</div>
          </div>
        </div>
      </GlassmorphicCard>

      <GlassmorphicCard
        class="stat-card"
        :clickable="true"
        padding="16px 20px"
        @click="loadBalance"
      >
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--accent">💳</span>
          <div>
            <div class="stat-value stat-value--accent">{{ balanceValue }}</div>
            <div class="stat-label" :title="balanceError ?? undefined">{{ balanceLabel }}</div>
          </div>
        </div>
      </GlassmorphicCard>
      <GlassmorphicCard
        class="stat-card"
        :clickable="true"
        padding="16px 20px"
        @click="loadDeepseekBalance"
      >
        <div class="stat-card__inner">
          <span class="stat-icon stat-icon--accent">🧠</span>
          <div>
            <div class="stat-value stat-value--accent">{{ dsBalanceValue }}</div>
            <div class="stat-label" :title="dsBalanceError ?? undefined">{{ dsBalanceLabel }}</div>
          </div>
        </div>
      </GlassmorphicCard>
    </div>

    <div class="dash-grid">
      <GlassmorphicPanel class="panel" padding="20px">
        <div class="panel__header">
          <span class="panel__title">账号状态</span>
          <span class="panel__sub">{{ onlineCount }}/{{ totalAccountCount }} 在线</span>
        </div>
        <!-- 点阵按平台分块（数据已按平台分桶；运行状态只对运行中平台有意义） -->
        <div v-for="p in platformStore.platforms" :key="p" class="platform-dots">
          <div class="platform-dots__head">
            <span :style="{ color: platformStore.metaFor(p).color }">
              {{ platformStore.metaFor(p).icon }} {{ platformStore.metaFor(p).label }}
            </span>
            <span class="platform-dots__count">{{ platformStore.metaFor(p).shortLabel }} {{ accountStore.accountsFor(p).length }} 个</span>
          </div>
          <div v-if="accountStore.accountsFor(p).length" class="dot-matrix">
            <div
              v-for="account in accountStore.accountsFor(p)"
              :key="account.id"
              class="account-dot"
              :class="dotStatus(account.id, account.status, p)"
              @mouseenter="hoveredDot = `${p}:${account.id}`"
              @mouseleave="hoveredDot = null"
            >
              {{ account.id.slice(-2) }}
              <div v-if="hoveredDot === `${p}:${account.id}`" class="dot-tooltip">
                {{ maskLogin(account.username) }} · {{ statusLabel(account.id, account.status, p) }}
              </div>
            </div>
          </div>
          <div v-else class="platform-dots__empty">
            尚未配置{{ platformStore.metaFor(p).label }}账号
          </div>
        </div>
        <div class="dot-legend">
          <span><span class="swatch swatch--idle"></span> 空闲</span>
          <span><span class="swatch swatch--running"></span> 运行中</span>
          <span><span class="swatch swatch--done"></span> 已完成</span>
          <span><span class="swatch swatch--error"></span> 异常</span>
        </div>
      </GlassmorphicPanel>

      <GlassmorphicPanel class="panel" padding="20px">
        <div class="panel__header">
          <span class="panel__title">系统资源</span>
          <Chip v-if="mockMode" variant="warn" size="sm">模拟数据</Chip>
          <!-- os.uptime() — the machine's uptime, not the app's. -->
          <span class="panel__sub">系统运行 {{ uptime }}</span>
        </div>
        <div class="resource-item">
          <div class="resource-header">
            <span class="resource-label">RAM 内存</span>
            <span class="resource-val">{{ ram.used }} GB / {{ ram.total }} GB</span>
          </div>
          <div class="resource-bar">
            <div class="resource-fill" :class="ramClass" :style="{ width: `${ram.pct}%` }"></div>
          </div>
          <div class="resource-detail">
            <span>已用 {{ ram.pct }}%</span>
            <span>可用 {{ ram.free }} GB</span>
          </div>
        </div>
        <div class="resource-item">
          <div class="resource-header">
            <span class="resource-label">CPU 占用</span>
            <span class="resource-val">{{ cpu.pct }}%</span>
          </div>
          <div class="resource-bar">
            <div class="resource-fill resource-fill--cpu" :style="{ width: `${cpu.pct}%` }"></div>
          </div>
          <div class="resource-detail">
            <span>{{ cpu.cores }} 核心</span>
            <span>负载 {{ cpu.pct }}%</span>
          </div>
        </div>
        <div class="resource-item">
          <div class="resource-header">
            <span class="resource-label">项目 Chrome 占用</span>
            <span class="resource-val">{{ projectChromeText }}</span>
          </div>
        </div>
      </GlassmorphicPanel>
    </div>

    <GlassmorphicPanel class="panel" padding="20px">
      <div class="panel__header">
        <span class="panel__title">今日活动</span>
        <span class="panel__sub">{{ timelineEntries.length }} 条记录</span>
      </div>
      <div v-if="timelineEntries.length" class="timeline">
        <div v-for="(entry, index) in timelineEntries" :key="index" class="timeline-item" :class="entry.level">
          <span class="timeline-time">{{ entry.time }}</span>
          <div class="timeline-body">
            <div class="tl-title">{{ entry.title }}</div>
            <div v-if="entry.detail" class="tl-detail">{{ entry.detail }}</div>
          </div>
        </div>
      </div>
      <div v-else class="timeline-empty">暂无活动记录</div>
    </GlassmorphicPanel>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import GlassmorphicCard from '@/shared/ui/GlassmorphicCard.vue'
import GlassmorphicPanel from '@/shared/ui/GlassmorphicPanel.vue'
import Chip from '@/shared/ui/Chip.vue'
import { useAccountStore } from '@/app/stores/account.store'
import { useAttentionStore } from '@/app/stores/attention.store'
import { useCourseStore } from '@/app/stores/course.store'
import { useExecutionStore } from '@/app/stores/execution.store'
import { useMemoryStore } from '@/app/stores/memory.store'
import { useLogStore } from '@/app/stores/log.store'
import { usePlatformStore } from '@/app/stores/platform.store'
import { createApiClient, isMockMode } from '@/shared/lib/apiClient'
import { PLATFORM_META } from '@/shared/lib/platforms'
import { maskLogin } from '@/shared/lib/mask'
import type { AccountStatus, Balance, Platform, SystemResources } from '@/shared/lib/types'

const api = createApiClient()
const mockMode = isMockMode()

const accountStore = useAccountStore()
const attentionStore = useAttentionStore()
const courseStore = useCourseStore()
const executionStore = useExecutionStore()
const memoryStore = useMemoryStore()
const logStore = useLogStore()
const platformStore = usePlatformStore()

const hoveredDot = ref<string | null>(null)

// Volcengine (Doubao) cash balance — fetched on mount via `chaoxing.balance`.
const balance = ref<Balance | null>(null)
const balanceError = ref<string | null>(null)
const balanceLoading = ref(false)

const balanceValue = computed(() => {
  if (balanceLoading.value) return '查询中…'
  if (balanceError.value) return '—'
  if (!balance.value) return '—'
  return `¥ ${balance.value.availableBalance}`
})

const balanceLabel = computed(() => {
  if (balanceError.value) {
    // Keep the stat label short; the full reason is available as a hover
    // tooltip and in the DevTools console. Errors are real Chinese reasons
    // (the invoke wrapper is stripped in ipcClient), so allow more room.
    const short = balanceError.value.split('\n')[0]
    return `余额查询失败：${short.length > 60 ? `${short.slice(0, 60)}…` : short}`
  }
  if (!balance.value) return 'API 可用余额'
  return `${balance.value.provider} 可用余额（现金 ¥ ${balance.value.cashBalance}）`
})

// DeepSeek engine balance — separate card so both engines are visible
// regardless of which one is currently active.
const dsBalance = ref<Balance | null>(null)
const dsBalanceError = ref<string | null>(null)
const dsBalanceLoading = ref(false)

const dsBalanceValue = computed(() => {
  if (dsBalanceLoading.value) return '查询中…'
  if (dsBalanceError.value) return '—'
  if (!dsBalance.value) return '—'
  return `¥ ${dsBalance.value.availableBalance}`
})

const dsBalanceLabel = computed(() => {
  if (dsBalanceError.value) {
    const short = dsBalanceError.value.split('\n')[0]
    return `余额查询失败：${short.length > 60 ? `${short.slice(0, 60)}…` : short}`
  }
  if (!dsBalance.value) return 'DeepSeek 可用余额'
  return `DeepSeek 可用余额（充值 ¥ ${dsBalance.value.cashBalance}）`
})

async function loadDeepseekBalance(): Promise<void> {
  dsBalanceLoading.value = true
  dsBalanceError.value = null
  try {
    dsBalance.value = await api.getBalance('deepseek')
  } catch (e: any) {
    dsBalanceError.value = e?.message ?? '查询失败'
    console.error('[balance] deepseek query failed:', e)
  } finally {
    dsBalanceLoading.value = false
  }
}

async function loadBalance(): Promise<void> {
  balanceLoading.value = true
  balanceError.value = null
  try {
    balance.value = await api.getBalance()
  } catch (e: any) {
    balanceError.value = e?.message ?? '查询失败'
    console.error('[balance] balance query failed:', e)
  } finally {
    balanceLoading.value = false
  }
}

function laneStatus(accountId: string, platform: Platform): string | null {
  // Lanes belong to that platform's own execution slot — the other platform's
  // dots must not light up as running from stale lane ids.
  return executionStore.slotOf(platform).lanes.find((lane) => lane.accountId === accountId)?.status ?? null
}

function dotStatus(accountId: string, accountStatus: AccountStatus, platform: Platform): string {
  const currentLaneStatus = laneStatus(accountId, platform)
  if (currentLaneStatus === 'running' || currentLaneStatus === 'paused') return 'running'
  if (currentLaneStatus === 'completed') return 'done'
  if (currentLaneStatus === 'error' || currentLaneStatus === 'stopped') return 'error'
  if (accountStatus === 'checking') return 'running'
  if (accountStatus === 'error') return 'error'
  return 'idle'
}

function statusLabel(accountId: string, accountStatus: AccountStatus, platform: Platform): string {
  const currentLaneStatus = laneStatus(accountId, platform)
  if (currentLaneStatus === 'running') return '运行中'
  if (currentLaneStatus === 'paused') return '已暂停'
  if (currentLaneStatus === 'completed') return '已完成'
  if (currentLaneStatus === 'stopped') return '已停止'
  if (currentLaneStatus === 'error') return '任务异常'
  if (accountStatus === 'checking') return '检查中'
  if (accountStatus === 'error') return '账号异常'
  if (accountStatus === 'offline') return '离线'
  return '空闲'
}

const totalAccountCount = computed(() =>
  platformStore.platforms.reduce((sum, p) => sum + accountStore.accountsFor(p).length, 0),
)

/** 账号卡副行：按平台分解（超星 3 · 智慧树 2）。 */
const accountBreakdown = computed(() =>
  platformStore.platforms
    .map((p) => `${PLATFORM_META[p].shortLabel} ${accountStore.accountsFor(p).length}`)
    .join(' · '),
)

const runningPlatformLabel = computed(() => {
  const running = executionStore.runningPlatforms
  if (!running.length) return '空闲'
  if (running.length === 1) return `${PLATFORM_META[running[0]].label}任务`
  return '双平台并行'
})

const onlineCount = computed(() =>
  platformStore.platforms.reduce(
    (sum, p) => sum + accountStore.accountsFor(p).filter((a) => a.status === 'online').length,
    0,
  ),
)

const runningCount = computed(() =>
  executionStore.runningPlatforms.reduce(
    (sum, p) => sum + executionStore.slotOf(p).lanes.filter((lane) => lane.status === 'running').length,
    0,
  ),
)

/** 完成课程按平台分解（含全部平台分桶；键为 platform:accountId）。 */
function doneCountFor(platform: Platform): number {
  const prefix = `${platform}:`
  let count = 0
  for (const [key, courses] of Object.entries(courseStore.coursesByAccount)) {
    if (!key.startsWith(prefix)) continue
    count += courses.filter((course) => course.progress >= 100).length
  }
  return count
}

const doneCount = computed(() =>
  platformStore.platforms.reduce((sum, p) => sum + doneCountFor(p), 0),
)

const doneBreakdown = computed(() =>
  platformStore.platforms.map((p) => `${PLATFORM_META[p].shortLabel} ${doneCountFor(p)}`).join(' · '),
)

// Live system resources — polled every 2s from the Electron main process
// (Node `os`), or the mock client in browser mode. Replaces the previous
// hardcoded constants that never updated.
const resources = ref<SystemResources>({
  ram: { used: 0, total: 0, free: 0, pct: 0 },
  cpu: { pct: 0, cores: 0 },
  uptimeSeconds: 0,
})
const ram = computed(() => resources.value.ram)
const projectChromeText = computed(() => {
  if (memoryStore.latest) return `${memoryStore.latest.projectChromeGB.toFixed(2)} GB`
  return mockMode ? '—（模拟）' : '—'
})
const cpu = computed(() => resources.value.cpu)
const uptime = computed(() => {
  const s = resources.value.uptimeSeconds
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
})

const ramClass = computed(() => {
  if (ram.value.pct >= 80) return 'resource-fill--high'
  if (ram.value.pct >= 50) return 'resource-fill--mid'
  return 'resource-fill--low'
})

let resourcesTimer: ReturnType<typeof setInterval> | null = null
async function pollResources(): Promise<void> {
  try {
    resources.value = await api.getSystemResources()
  } catch {
    // Polling failures are non-fatal — keep the last good value on screen
    // rather than flashing zeros. The next tick will retry.
  }
}

const timelineEntries = computed(() => {
  const recent = logStore.recentLines.slice(0, 10)
  return recent.map((line) => {
    const level =
      line.level === 'error' || line.level === 'warn'
        ? 'warn'
        : line.message.includes('完成') || line.message.includes('success')
          ? 'ok'
          : 'info'

    return {
      time: line.time,
      title: line.message,
      detail: line.source ?? undefined,
      level,
    }
  })
})

onMounted(async () => {
  void loadBalance()
  void loadDeepseekBalance()
  void pollResources()
  resourcesTimer = setInterval(pollResources, 2000)
  // Dashboard aggregates BOTH platforms — load both buckets (fetchAccounts /
  // fetchCourses cache per platform, so this is a no-op when already loaded).
  await Promise.all([
    ...platformStore.platforms.map((p) => accountStore.fetchAccounts(p)),
    attentionStore.fetchTickets(),
  ])
  await Promise.all(
    platformStore.platforms.flatMap((p) =>
      accountStore.accountsFor(p).map((account) => courseStore.fetchCourses(account.id, p)),
    ),
  )
})

onUnmounted(() => {
  if (resourcesTimer) {
    clearInterval(resourcesTimer)
    resourcesTimer = null
  }
})
</script>

<style scoped>
.dash {
  max-width: 1100px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 40px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
}

.stat-card__inner {
  display: flex;
  align-items: center;
  gap: 14px;
}

.stat-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.stat-icon--accent { background: var(--accent-soft); }
.stat-icon--gold { background: var(--gold-soft); }
.stat-icon--ok { background: var(--ok-soft); }
.stat-icon--warn { background: var(--warn-soft); }

.stat-value {
  font-size: 22px;
  font-weight: 700;
  font-family: var(--font-display);
}
.stat-value--accent { color: var(--accent); }
.stat-value--gold { color: var(--gold); }
.stat-value--ok { color: var(--ok); }
.stat-value--warn { color: var(--warn); }

.stat-label {
  font-size: 11px;
  color: var(--muted);
  line-height: 1.3;
}

.dash-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.panel__title {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}

.panel__sub {
  font-size: 12px;
  color: var(--muted);
}

.dot-matrix {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.platform-dots {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius-sm);
}
.platform-dots + .platform-dots {
  margin-top: 10px;
}
.platform-dots__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 600;
}
.platform-dots__count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  font-weight: 400;
}
.platform-dots__empty {
  font-size: 12px;
  color: var(--muted);
  padding: 2px 0;
}

.stat-sub {
  font-size: 11px;
  color: var(--muted);
  margin-top: 2px;
  white-space: nowrap;
}

.account-dot {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  font-family: var(--font-mono);
  color: #fff;
  transition: transform 0.15s;
  position: relative;
}

.account-dot:hover {
  transform: scale(1.15);
  z-index: 2;
}

.account-dot.idle {
  background: var(--bg3, #252836);
  border: 1px solid var(--line);
  color: var(--muted);
}

.account-dot.running {
  background: var(--gold, #eab308);
  box-shadow: 0 0 8px rgba(234, 179, 8, 0.4);
}

.account-dot.done {
  background: var(--ok, #22c55e);
  box-shadow: 0 0 8px rgba(34, 197, 94, 0.4);
}

.account-dot.error {
  background: var(--warn, #ef4444);
  box-shadow: 0 0 8px rgba(239, 68, 68, 0.4);
}

.dot-legend {
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: var(--muted);
  flex-wrap: wrap;
}

.dot-legend span {
  display: flex;
  align-items: center;
  gap: 5px;
}

.swatch {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  flex-shrink: 0;
}

.swatch--idle { background: var(--bg3, #252836); border: 1px solid var(--line); }
.swatch--running { background: var(--gold, #eab308); }
.swatch--done { background: var(--ok, #22c55e); }
.swatch--error { background: var(--warn, #ef4444); }

.dot-tooltip {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  background: var(--bg3, #252836);
  border: 1px solid var(--line);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 11px;
  white-space: nowrap;
  pointer-events: none;
  z-index: 10;
  font-weight: 400;
  color: var(--text);
}

.resource-item {
  margin-bottom: 14px;
}

.resource-item:last-child {
  margin-bottom: 0;
}

.resource-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 12px;
}

.resource-label { color: var(--muted); }
.resource-val { font-weight: 600; font-family: var(--font-mono); }

.resource-bar {
  height: 10px;
  background: var(--bg);
  border-radius: 5px;
  overflow: hidden;
  position: relative;
}

.resource-fill {
  height: 100%;
  border-radius: 5px;
  transition: width 0.5s;
}

.resource-fill--low { background: var(--ok, #22c55e); }
.resource-fill--mid { background: var(--gold, #eab308); }
.resource-fill--high { background: var(--warn, #ef4444); }
.resource-fill--cpu { background: var(--accent); }

.resource-detail {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--muted);
  font-family: var(--font-mono);
  margin-top: 4px;
}

.timeline {
  position: relative;
  padding-left: 8px;
}

.timeline-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  position: relative;
  align-items: flex-start;
  border-left: 2px solid var(--line);
  padding-left: 16px;
  margin-left: 6px;
}

.timeline-item:last-child {
  border-left-color: transparent;
}

.timeline-item::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--line);
}

.timeline-item.ok::before { background: var(--ok, #22c55e); }
.timeline-item.warn::before { background: var(--warn, #ef4444); }
.timeline-item.info::before { background: var(--accent); }

.timeline-time {
  font-size: 11px;
  color: var(--muted);
  font-family: var(--font-mono);
  flex-shrink: 0;
  width: 48px;
}

.timeline-body {
  font-size: 12px;
  flex: 1;
}

.tl-title {
  font-weight: 600;
  color: var(--text);
}

.tl-detail {
  color: var(--muted);
  font-size: 11px;
  margin-top: 2px;
}

.timeline-empty {
  text-align: center;
  padding: 30px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 900px) {
  .stats-grid { grid-template-columns: repeat(3, 1fr); }
  .dash-grid { grid-template-columns: 1fr; }
}

@media (max-width: 600px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
