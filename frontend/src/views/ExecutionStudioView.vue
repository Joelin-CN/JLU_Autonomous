<template>
  <div class="studio">
    <!-- ── Empty State ── -->
    <div v-if="!executionStore.isRunning && !executionStore.isPaused && !hasRunData" class="empty-state">
      <span class="empty-state__icon">▶️</span>
      <p class="empty-state__text">从「课程总览」页面选择账号与课程并启动任务后，这里会显示实时执行进度</p>
    </div>

    <template v-else>
      <!-- ── Runtime Banner ── -->
      <GlassmorphicPanel :class="['banner', `banner--${statusColorKey}`]" padding="16px 22px">
        <div class="banner__left">
          <span class="banner__icon">{{ statusIcon }}</span>
          <span class="banner__label">{{ statusText }}</span>
          <span v-if="executionStore.isRunning" class="banner__elapsed">{{ executionStore.elapsedFormatted }}</span>
          <span v-if="executionStore.progress > 0" class="banner__pct">{{ executionStore.progress }}%</span>
        </div>
        <div class="banner__actions">
          <button
            v-if="executionStore.isRunning"
            class="btn btn--gold"
            @click="executionStore.pauseJob()"
          >全部暂停</button>
          <button
            v-if="executionStore.isPaused"
            class="btn btn--accent"
            @click="executionStore.resumeJob()"
          >全部继续</button>
          <button
            v-if="executionStore.isRunning || executionStore.isPaused"
            class="btn btn--warn"
            @click="executionStore.stopJob()"
          >全部停止</button>
          <button
            v-if="isTerminal"
            class="btn btn--outline"
            @click="executionStore.reset()"
          >关闭</button>
        </div>
      </GlassmorphicPanel>

      <!-- ── Phase Stepper ── -->
      <GlassmorphicPanel class="phases" padding="20px">
        <h3 class="section-title">执行阶段</h3>
        <div class="timeline">
          <div
            v-for="(phase, i) in executionStore.phases"
            :key="i"
            :class="['timeline-item', `timeline-item--${phase.status}`]"
          >
            <div class="timeline__dot">
              <span v-if="phase.status === 'completed'" class="timeline__check">✓</span>
              <span v-else-if="phase.status === 'error'" class="timeline__cross">✕</span>
              <span v-else-if="phase.status === 'stopped'" class="timeline__cross">⏹</span>
            </div>
            <div class="timeline__body">
              <span class="timeline__name">{{ phase.name }}</span>
              <span v-if="phase.message" class="timeline__msg">{{ phase.message }}</span>
              <!-- The backend reports no per-phase fraction; a flowing bar is
                   honest where a stuck 0%/100% bar would be misleading. -->
              <ProgressBar
                v-if="phase.status === 'running'"
                indeterminate
                variant="accent"
                height="4px"
              />
            </div>
          </div>
        </div>
      </GlassmorphicPanel>

      <!-- ── Account Swimlanes ── -->
      <GlassmorphicPanel class="lanes" padding="20px">
        <div class="lanes__header">
          <h3 class="section-title">执行席位</h3>
        </div>
        <div class="lane-grid">
          <GlassmorphicCard
            v-for="(lane, i) in executionStore.lanes"
            :key="lane.accountId"
            padding="16px"
            :class="['lane-card', `lane-card--${lane.status}`]"
          >
            <div class="lane-card__head">
              <span class="lane-card__name">{{ accountName(lane.accountId) }}</span>
              <span class="lane-card__session">S{{ i + 1 }}-{{ lane.accountId.slice(0, 6) }}</span>
            </div>
            <div v-if="lane.currentPhase" class="lane-card__phase">
              <span class="lane-card__phase-label">当前阶段</span>
              <span class="lane-card__phase-value">{{ lane.currentPhase }}</span>
            </div>
            <div v-if="lane.status === 'running'" class="lane-card__time">
              ⏱ {{ executionStore.laneElapsedFormatted(lane.accountId) }}
            </div>
            <div v-else-if="lane.status === 'paused'" class="lane-card__time lane-card__time--paused">
              ⏸ {{ executionStore.laneElapsedFormatted(lane.accountId) }}
            </div>
            <p class="lane-card__task">{{ lane.currentTask ?? '就绪中...' }}</p>
            <div class="lane-card__progress">
              <ProgressBar
                :percent="lane.progress"
                :variant="laneVariant(lane.status)"
                height="6px"
              />
              <span class="lane-card__pct">{{ Math.round(lane.progress) }}%</span>
            </div>
            <Chip :variant="laneChipVariant(lane.status)" size="sm">{{ laneStatusLabel(lane.status) }}</Chip>
            <p v-if="lane.errorMessage" class="lane-card__error">{{ lane.errorMessage }}</p>
          </GlassmorphicCard>
        </div>
      </GlassmorphicPanel>

      <!-- ── Last Run Stats ── -->
      <GlassmorphicPanel v-if="executionStore.status === 'completed' || executionStore.status === 'stopped' || executionStore.status === 'error'" class="stats" padding="20px">
        <h3 class="section-title">执行统计</h3>
        <div class="stats-grid">
          <GlassmorphicCard padding="16px" class="stat-card">
            <span class="stat-card__value">{{ totalCourses }}</span>
            <span class="stat-card__label">课程</span>
          </GlassmorphicCard>
          <GlassmorphicCard padding="16px" class="stat-card">
            <span class="stat-card__value">{{ totalSections }}</span>
            <span class="stat-card__label">章节</span>
          </GlassmorphicCard>
          <GlassmorphicCard padding="16px" class="stat-card">
            <span class="stat-card__value">{{ executionStore.progress }}%</span>
            <span class="stat-card__label">完成率</span>
          </GlassmorphicCard>
          <GlassmorphicCard padding="16px" class="stat-card">
            <span class="stat-card__value">{{ executionStore.elapsedFormatted }}</span>
            <span class="stat-card__label">耗时</span>
          </GlassmorphicCard>
        </div>
      </GlassmorphicPanel>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import GlassmorphicPanel from '@/shared/ui/GlassmorphicPanel.vue'
import GlassmorphicCard from '@/shared/ui/GlassmorphicCard.vue'
import ProgressBar from '@/shared/ui/ProgressBar.vue'
import Chip from '@/shared/ui/Chip.vue'
import { useExecutionStore } from '@/app/stores/execution.store'
import { useAccountStore } from '@/app/stores/account.store'
import { useCampaignStore } from '@/app/stores/campaign.store'
import { maskLogin } from '@/shared/lib/mask'

const executionStore = useExecutionStore()
const accountStore = useAccountStore()
const campaignStore = useCampaignStore()

// Reconcile with main-process truth on mount: if a terminal event was missed
// (e.g. the Python process failed to spawn while this view was not mounted),
// the banner would otherwise stay "running" forever.
onMounted(() => {
  if (executionStore.isRunning) {
    void executionStore.refreshStatus()
  }
})

/* ── computed ── */
const hasRunData = computed(() =>
  executionStore.phases.length > 0 || executionStore.status !== 'idle',
)

// A finished run (completed / stopped / error) keeps the studio populated so
// the user can read the final lanes + stats, but offers a 「关闭」 button to
// reset back to idle. Without this, a terminal job is un-dismissable and the
// pause/stop buttons (running-only) are gone — leaving the view stuck.
const isTerminal = computed(() =>
  executionStore.status === 'completed' ||
  executionStore.status === 'stopped' ||
  executionStore.status === 'error',
)

/* ── status mapping ── */
const statusColorKey = computed((): string => {
  switch (executionStore.status) {
    case 'running': return 'running'
    case 'paused': return 'paused'
    case 'completed': return 'completed'
    case 'error': return 'error'
    case 'stopped': return 'stopped'
    default: return 'idle'
  }
})

const statusIcon = computed((): string => {
  switch (executionStore.status) {
    case 'running': return '🟢'
    case 'paused': return '⏸️'
    case 'completed': return '✅'
    case 'error': return '❌'
    case 'stopped': return '⏹️'
    default: return '⏳'
  }
})

const statusText = computed((): string => {
  switch (executionStore.status) {
    case 'idle': return '就绪'
    case 'running': return '运行中'
    case 'paused': return '已暂停'
    case 'completed': return '执行完成'
    case 'error': return '执行失败'
    case 'stopped': return '已停止'
    default: return '未知'
  }
})

/* ── helpers ── */
function accountName(accountId: string): string {
  const acc = accountStore.accounts.find(a => a.id === accountId)
  const name = acc?.displayName ?? acc?.username ?? accountId.slice(0, 8)
  // Logins are phone numbers — mask them like every other view does.
  return maskLogin(name)
}

function laneVariant(status: string): 'accent' | 'ok' | 'warn' | 'gold' {
  if (status === 'completed') return 'ok'
  if (status === 'error') return 'warn'
  if (status === 'running') return 'accent'
  if (status === 'paused') return 'gold'
  if (status === 'queued') return 'gold'
  return 'gold'
}

function laneChipVariant(status: string): 'accent' | 'ok' | 'warn' | 'gold' | 'muted' {
  if (status === 'completed') return 'ok'
  if (status === 'error') return 'warn'
  if (status === 'running') return 'accent'
  if (status === 'paused') return 'gold'
  if (status === 'queued') return 'muted'
  return 'muted'
}

function laneStatusLabel(status: string): string {
  switch (status) {
    case 'pending': return '待命'
    case 'running': return '运行中'
    case 'completed': return '完成'
    case 'error': return '异常'
    case 'paused': return '已暂停'
    case 'queued': return '排队中'
    case 'stopped': return '已停止'
    default: return status
  }
}

const totalCourses = computed(() => campaignStore.selectedCourseIds.length || executionStore.lanes.length)
const totalSections = computed(() => executionStore.lanes.reduce((sum, l) => sum + (l.progress > 0 ? Math.floor(l.progress / 10) : 0), 0))
</script>

<style scoped>
.studio {
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Empty ── */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 60vh;
  gap: 16px;
}
.empty-state__icon { font-size: 56px; opacity: 0.5; }
.empty-state__text { font-size: 15px; color: var(--muted); }

/* ── Banner ── */
.banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.banner--running { border-color: var(--accent); }
.banner--paused { border-color: var(--gold); }
.banner--completed { border-color: var(--ok); }
.banner--error { border-color: var(--warn); }
.banner--stopped { border-color: var(--muted); }

.banner__left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.banner__icon { font-size: 18px; }
.banner__label {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
}
.banner__elapsed {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--muted);
}
.banner__pct {
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}
.banner__actions {
  display: flex;
  gap: 8px;
}

/* ── Buttons ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: background 0.2s;
}
.btn--accent { background: var(--accent); color: #fff; }
.btn--accent:hover { filter: brightness(1.1); }
.btn--gold { background: var(--gold); color: #fff; }
.btn--gold:hover { filter: brightness(1.1); }
.btn--warn { background: var(--warn); color: #fff; }
.btn--warn:hover { filter: brightness(1.1); }

/* ── Section title ── */
.section-title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 0;
  margin-block-end: 0;
}

/* ── Timeline ── */
.timeline {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 8px 0;
}
.timeline__dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 2px solid var(--line);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  background: var(--bg);
  font-size: 12px;
}
.timeline-item--running .timeline__dot {
  border-color: var(--accent);
  background: var(--accent-soft);
  animation: pulse-ring 1.5s ease-in-out infinite;
}
.timeline-item--completed .timeline__dot {
  border-color: var(--ok);
  background: var(--ok-soft);
}
.timeline-item--error .timeline__dot {
  border-color: var(--warn);
  background: var(--warn-soft);
}
.timeline-item--stopped .timeline__dot {
  border-color: var(--muted);
  background: var(--line);
}
.timeline-item--stopped .timeline__name { color: var(--muted); }
.timeline__check { color: var(--ok); font-weight: 700; }
.timeline__cross { color: var(--warn); font-weight: 700; }

.timeline__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.timeline__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.timeline-item--pending .timeline__name { color: var(--muted); }
.timeline-item--running .timeline__name { color: var(--accent); font-weight: 700; }
.timeline__msg {
  font-size: 12px;
  color: var(--muted);
}

@keyframes pulse-ring {
  0%, 100% { box-shadow: 0 0 0 0 var(--accent-soft); }
  50% { box-shadow: 0 0 0 6px transparent; }
}

/* ── Lanes header ── */
.lanes__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.lanes__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
}
.select-all__text {
  font-size: 12px;
  color: var(--muted);
}

/* ── Small outline button ── */
.btn--sm {
  padding: 4px 14px;
  font-size: 12px;
}
.btn--outline {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--muted);
}
.btn--outline:hover {
  border-color: var(--accent);
  color: var(--accent);
}

/* ── Lane grid ── */
.lane-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.lane-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.lane-card--running { border-color: var(--accent); }
.lane-card--completed { border-color: var(--ok); }
.lane-card--error { border-color: var(--warn); }
.lane-card--paused { border-color: var(--gold); opacity: 0.85; }
.lane-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.lane-card__check {
  display: flex;
  align-items: center;
  cursor: pointer;
}
.lane-card__check input[type="checkbox"] {
  width: 15px;
  height: 15px;
  accent-color: var(--accent);
  cursor: pointer;
}
.lane-card__name {
  font-weight: 700;
  font-size: 14px;
  color: var(--text);
  flex: 1;
}
.lane-card__session {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}
.lane-card__phase {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.lane-card__phase-label {
  color: var(--muted);
}
.lane-card__phase-value {
  color: var(--accent);
  font-weight: 600;
}
.lane-card__time {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--accent);
}
.lane-card__time--paused {
  color: var(--gold);
}
.lane-card__task {
  font-size: 12px;
  color: var(--muted);
  margin: 0;
}
.lane-card__progress {
  display: flex;
  align-items: center;
  gap: 10px;
}
.lane-card__pct {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
  flex-shrink: 0;
}
.lane-card__error {
  font-size: 11px;
  color: var(--warn);
  padding: 6px 8px;
  background: var(--warn-soft);
  border-radius: var(--radius-sm);
  margin: 0;
}

/* ── Stats ── */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.stat-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.stat-card__value {
  font-family: var(--font-display);
  font-size: 24px;
  font-weight: 700;
  color: var(--text);
}
.stat-card__label {
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 600px) {
  .stats-grid { grid-template-columns: repeat(2, 1fr); }
  .lane-grid { grid-template-columns: 1fr; }
}
</style>
