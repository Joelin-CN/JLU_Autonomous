<template>
  <div class="atlas">
    <aside class="atlas__left">
      <div class="left-header">
        <span class="left-header__title">
          账号列表
          <span class="left-header__platform" :style="{ color: platformStore.meta.color }">
            {{ platformStore.meta.icon }} {{ platformStore.meta.shortLabel }}
          </span>
        </span>
        <span class="left-header__count">{{ accountStore.selectedAccountIds.size }}/{{ accountStore.accounts.length }}</span>
      </div>

      <label class="select-all-row" @click.prevent="toggleAllAccounts">
        <span
          class="checkbox"
          :class="{
            'checkbox--on': allAccountsSelected,
            'checkbox--partial': !allAccountsSelected && accountStore.selectedAccountIds.size > 0,
          }"
        >
          <span v-if="allAccountsSelected">✓</span>
          <span v-else-if="accountStore.selectedAccountIds.size > 0">-</span>
        </span>
        <span>全选</span>
      </label>

      <div class="account-list">
        <div
          v-for="account in accountStore.accounts"
          :key="account.id"
          :class="['account-row', { 'account-row--active': activeAccountId === account.id }]"
          @click="setActiveAccount(account.id)"
        >
          <span
            class="checkbox"
            :class="{ 'checkbox--on': accountStore.selectedAccountIds.has(account.id) }"
            @click.stop="accountStore.toggleAccountSelection(account.id)"
          >
            <span v-if="accountStore.selectedAccountIds.has(account.id)">✓</span>
          </span>
          <StatusDot :status="accountStatusToDot(account.status)" size="sm" />
          <span class="account-row__phone">{{ maskLogin(account.username) }}</span>
          <span
            class="account-row__badge"
            :class="{ 'account-row__badge--sel': selectedCourseCountForAccount(account.id) > 0 }"
          >
            <template v-if="selectedCourseCountForAccount(account.id) > 0">
              {{ selectedCourseCountForAccount(account.id) }}/{{ courseCountForAccount(account.id) }}
            </template>
            <template v-else>
              {{ courseCountForAccount(account.id) }}
            </template>
          </span>
        </div>
      </div>

      <div v-if="extraAccountCount > 0" class="extra-hint">更多账号... (+{{ extraAccountCount }})</div>

      <div class="left-actions">
        <button class="btn btn--outline btn--block" :disabled="noAccountSelected || executionStore.isRunning" @click="scanClicked">
          {{ executionStore.isRunning ? '运行中...' : '一键扫描' }}
        </button>
        <button
          class="btn btn--primary btn--block"
          :disabled="noAccountSelected || executionStore.isRunning"
          :title="fullAutoHint"
          @click="startFullAuto"
        >
          {{ fullAutoLabel }}
        </button>
      </div>
    </aside>

    <section class="atlas__right">
      <div class="right-header">
        <span class="right-header__label">{{ activeAccountLabel }}</span>
        <div class="right-header__controls">
          <button class="btn btn--outline btn--sm" @click="toggleAllCourses">
            {{ allCoursesSelected ? '取消全选' : '全选' }}
          </button>
          <span class="right-header__sep"></span>
          <label class="dry-run-label" @click.prevent="dryRun = !dryRun">
            <span class="dry-run-label__text">模拟运行</span>
            <Toggle :model-value="dryRun" @update:model-value="dryRun = $event" @click.stop />
          </label>
        </div>
      </div>

      <div v-if="!activeAccountId" class="empty-state">
        <span class="empty-state__icon">📟</span>
        <p>请先从左侧选择一个账号。</p>
      </div>
      <div v-else-if="!activeCourses.length" class="empty-state">
        <span class="empty-state__icon">📚</span>
        <p>当前账号还没有课程数据，请先扫描。</p>
      </div>

      <div v-else class="course-grid">
        <GlassmorphicCard
          v-for="course in activeCourses"
          :key="course.id"
          :class="['course-card', { 'course-card--sel': courseStore.selectedCourseIds.has(course.id) }]"
          clickable
          padding="14px 16px"
          @click="courseStore.toggleCourseSelection(course.id)"
        >
          <div class="course-card__head">
            <span class="course-card__icon">{{ courseIcon(course) }}</span>
            <div class="course-card__info">
              <span class="course-card__name">{{ course.name }}</span>
              <span v-if="course.teacher" class="course-card__teacher">{{ course.teacher }}</span>
            </div>
            <!-- Progress on these cards is a discovery-file snapshot; while the
                 account is executing, mark it so a static bar isn't mistaken
                 for a live one. -->
            <Chip v-if="course.progress >= 100" variant="ok" size="sm">完成</Chip>
            <Chip v-else-if="activeAccountLaneRunning" variant="accent" size="sm">运行中</Chip>
          </div>
          <div class="course-card__tags">
            <Chip variant="accent" size="sm">{{ course.totalSections }} 章节</Chip>
            <Chip variant="ok" size="sm">{{ course.completedSections }} 已完成</Chip>
          </div>
          <div class="course-card__progress-row">
            <ProgressBar :percent="course.progress" :variant="course.progress >= 80 ? 'ok' : 'accent'" height="6px" />
            <span class="course-card__pct">{{ Math.round(course.progress) }}%</span>
          </div>
        </GlassmorphicCard>
      </div>

      <footer class="action-bar" v-if="courseStore.hasSelection">
        <GlassmorphicCard class="action-bar__inner" padding="12px 20px">
          <span class="action-bar__summary">
            已选 <strong>{{ courseStore.selectedCourseIds.size }}</strong> 门课程 ·
            <strong>{{ accountStore.selectedAccountIds.size }}</strong> 个账号
          </span>
          <div class="action-bar__buttons">
            <button
              v-if="unscannedSelectedAccounts.length > 0"
              class="btn btn--outline"
              :disabled="executionStore.isRunning"
              :title="`为 ${unscannedSelectedAccounts.length} 个尚未扫描的账号扫描课程`"
              @click="scanUnscannedOnly"
            >仅扫描</button>
            <button class="btn btn--primary" :disabled="executionStore.isRunning" @click="startJob('full-auto')">
              按队列启动 {{ accountStore.selectedAccountIds.size }} 个账号 · 最多 {{ planMax }} 并发
            </button>
            <!-- 任务模式按平台能力矩阵显隐/置灰（shared/lib/platforms.ts） -->
            <button
              class="btn btn--outline"
              :disabled="executionStore.isRunning || !caps.tasks.solveOnly"
              :title="caps.tasks.solveOnlyHint"
              @click="startJob('batch-exec', { focus: 'quiz' })"
            >仅刷题</button>
            <button
              class="btn btn--outline"
              :disabled="executionStore.isRunning || !caps.tasks.contentOnly"
              :title="caps.tasks.contentOnlyHint"
              @click="startJob('batch-exec', { focus: 'content' })"
            >仅内容</button>
          </div>
        </GlassmorphicCard>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import GlassmorphicCard from '@/shared/ui/GlassmorphicCard.vue'
import StatusDot from '@/shared/ui/StatusDot.vue'
import ProgressBar from '@/shared/ui/ProgressBar.vue'
import Chip from '@/shared/ui/Chip.vue'
import Toggle from '@/shared/ui/Toggle.vue'
import { maskLogin } from '@/shared/lib/mask'
import { useAccountStore } from '@/app/stores/account.store'
import { useCampaignStore } from '@/app/stores/campaign.store'
import { useCourseStore } from '@/app/stores/course.store'
import { useExecutionStore } from '@/app/stores/execution.store'
import { usePlatformStore } from '@/app/stores/platform.store'
import { useSettingsStore } from '@/app/stores/settings.store'
import { useMemoryStore } from '@/app/stores/memory.store'
import type { AccountStatus, Course, ModeType, StartJobPayload } from '@/shared/lib/types'

const router = useRouter()
const accountStore = useAccountStore()
const campaignStore = useCampaignStore()
const courseStore = useCourseStore()
const executionStore = useExecutionStore()

/** 全局平台上下文（侧栏切换器驱动；本页不再持有局部平台状态）。 */
const platformStore = usePlatformStore()
const caps = computed(() => platformStore.capabilities)

const settingsStore = useSettingsStore()
const memoryStore = useMemoryStore()

const activeAccountId = ref<string | null>(null)
// Persisted in settings so the never-submit guard survives view switches —
// a view-local toggle silently reset and could enable real submissions.
const dryRun = computed({
  get: () => settingsStore.settings.dryRun,
  set: (value: boolean) => settingsStore.updateSetting('dryRun', value),
})
const planMax = computed(() => memoryStore.plan?.maxConcurrent ?? settingsStore.settings.concurrencyTarget ?? 8)

/** 「全自动」按钮按平台能力矩阵取文案/说明（智慧树 full = 视频任务）。 */
const fullAutoLabel = computed(
  () => caps.value.tasks.fullAutoLabel ?? '一键全自动',
)
const fullAutoHint = computed(() =>
  platformStore.currentPlatform === 'zhihuishu'
    ? '智慧树当前以 1.0 倍速真实播放视频任务（D6 决策）'
    : '全自动完成课程学习与答题',
)

function accountStatusToDot(status: AccountStatus): 'online' | 'offline' | 'running' | 'idle' | 'error' | 'done' {
  if (status === 'online') return 'online'
  if (status === 'error') return 'error'
  if (status === 'checking') return 'running'
  return 'offline'
}

function courseIcon(course: Course): string {
  if (course.name.includes('English') || course.name.includes('英语')) return '📘'
  if (course.name.includes('Math') || course.name.includes('数学')) return '📐'
  if (course.name.includes('计算机') || course.name.includes('编程')) return '💻'
  if (course.name.includes('政治') || course.name.includes('思政')) return '🗳'
  return '📙'
}

const allAccountsSelected = computed(() =>
  accountStore.accounts.length > 0 &&
  accountStore.selectedAccountIds.size === accountStore.accounts.length,
)

/** Buttons operate on the selected subset — any non-empty selection works. */
const noAccountSelected = computed(() => accountStore.selectedAccountIds.size === 0)

const extraAccountCount = computed(() => {
  const total = accountStore.accounts.length
  return total > 8 ? total - 8 : 0
})

const activeAccountLabel = computed(() => {
  if (!activeAccountId.value) return '请选择一个账号'
  const account = accountStore.accounts.find((item) => item.id === activeAccountId.value)
  return account ? maskLogin(account.username) : '请选择一个账号'
})

const activeCourses = computed(() => {
  if (!activeAccountId.value) return []
  return courseStore.coursesForAccount(activeAccountId.value)
})

/** True while the displayed account has an executing lane — course-card
 *  progress bars are snapshots until that run finishes and reloads. */
const activeAccountLaneRunning = computed(() => {
  if (!activeAccountId.value) return false
  return executionStore.lanes.some(
    (lane) => lane.accountId === activeAccountId.value && lane.status === 'running',
  )
})

const allCoursesSelected = computed(() => {
  if (!activeCourses.value.length) return false
  return activeCourses.value.every((course) => courseStore.selectedCourseIds.has(course.id))
})

/** 所选账号中尚未被扫描（还没有课程数据）的账号。底部「仅扫描」只对它们有意义。 */
const unscannedSelectedAccounts = computed(() =>
  [...accountStore.selectedAccountIds].filter((id) => !courseStore.isAccountScanned(id)),
)

function courseCountForAccount(accountId: string): number {
  return courseStore.coursesForAccount(accountId).length
}

function selectedCourseCountForAccount(accountId: string): number {
  return courseStore
    .coursesForAccount(accountId)
    .filter((course) => courseStore.selectedCourseIds.has(course.id)).length
}

function syncCampaignSelection(): void {
  campaignStore.syncSelection({
    courseIds: [...courseStore.selectedCourseIds],
    operatorIds: [...accountStore.selectedAccountIds],
  })
}

function toggleAllAccounts(): void {
  if (allAccountsSelected.value) {
    accountStore.deselectAll()
  } else {
    accountStore.selectAll()
  }
  syncCampaignSelection()
}

function setActiveAccount(accountId: string): void {
  activeAccountId.value = accountId
  courseStore.setActiveAccount(accountId)
  void courseStore.fetchCourses(accountId)
}

function toggleAllCourses(): void {
  const activeIds = activeCourses.value.map((course) => course.id)
  if (allCoursesSelected.value) {
    courseStore.removeSelectedCourses(activeIds)
  } else {
    courseStore.addSelectedCourses(activeIds)
  }
}

async function scanClicked(): Promise<void> {
  // Real platform scan: spawn a scan_only job over the selected accounts. This
  // opens a logged-in browser and discovers courses (mode 'course-scan' →
  // backend --mode scan_only). No course selection is needed; an empty course
  // filter means "scan everything". The discovery file it writes is reflected
  // back into this atlas on completion (execution.store → course.store reload).
  //
  // NOTE: distinct from courseStore.scanCourses, which only re-reads the
  // already-persisted discovery cache (a sub-second file read, no browser).
  await startJob('course-scan')
}

async function startFullAuto(): Promise<void> {
  await startJob('full-auto')
}

async function startJob(
  mode: ModeType,
  extraOptions?: Record<string, unknown>,
  accountOverride?: string[],
): Promise<void> {
  const payload: StartJobPayload = {
    platform: platformStore.currentPlatform,
    objective: 'catchup',
    strategy: 'balanced',
    mode,
    courses: [...courseStore.selectedCourseIds],
    accounts: accountOverride ?? [...accountStore.selectedAccountIds],
    options: {
      dryRun: dryRun.value,
      maxConcurrency: settingsStore.settings.maxConcurrency,
      ...extraOptions,
    },
  }
  await executionStore.startJob(payload)
  router.push('/execution-studio')
}

/** 仅对尚未扫描的账号发起扫描；已扫描账号的课程已在列表中，无需重复扫描。 */
async function scanUnscannedOnly(): Promise<void> {
  await startJob('course-scan', undefined, unscannedSelectedAccounts.value)
}

watch(
  () => courseStore.selectedCourseIds,
  (selectedIds) => {
    // Auto-select any account (current platform's buckets only) that owns one
    // of the selected courses so the job payload stays consistent.
    for (const account of accountStore.accounts) {
      const hasSelectedCourse = courseStore
        .coursesForAccount(account.id)
        .some((course) => selectedIds.has(course.id))
      if (hasSelectedCourse && !accountStore.selectedAccountIds.has(account.id)) {
        accountStore.selectAccount(account.id)
      }
    }
    syncCampaignSelection()
  },
)

watch(
  () => accountStore.selectedAccountIds,
  () => {
    syncCampaignSelection()
  },
)

/** 平台切换后：激活新平台的第一个账号并预取课程（数据已按平台分桶）。 */
watch(
  () => platformStore.currentPlatform,
  async () => {
    activeAccountId.value = null
    if (accountStore.accounts.length > 0) {
      setActiveAccount(accountStore.accounts[0].id)
    }
    for (const account of accountStore.accounts) {
      void courseStore.fetchCourses(account.id)
    }
    syncCampaignSelection()
  },
)

onMounted(async () => {
  await accountStore.fetchAccounts()

  if (!activeAccountId.value && accountStore.accounts.length > 0) {
    setActiveAccount(accountStore.accounts[0].id)
  }

  for (const account of accountStore.accounts) {
    void courseStore.fetchCourses(account.id)
  }

  syncCampaignSelection()
})
</script>

<style scoped>
.atlas {
  display: flex;
  gap: 0;
  height: 100%;
}

.atlas__left {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 16px;
  border-right: 1px solid var(--line);
}
.left-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.left-header__title {
  font-family: var(--font-display);
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
}
.left-header__count {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
}
.left-header__platform {
  font-size: 12px;
  font-weight: 600;
  margin-left: 6px;
}

.checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 1.5px solid var(--line);
  font-size: 11px;
  color: transparent;
  flex-shrink: 0;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.checkbox--on {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.checkbox--partial {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent);
}

.select-all-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  padding: 4px 0;
}

.account-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow-y: auto;
}
.account-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  border-left: 3px solid transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.account-row:hover {
  background: var(--accent-soft);
}
.account-row--active {
  background: var(--accent-soft);
  border-left-color: var(--accent);
}
.account-row__phone {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--text);
}
.account-row__badge {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
  background: var(--line);
  padding: 1px 7px;
  border-radius: 999px;
}
.account-row__badge--sel {
  background: var(--accent-soft);
  color: var(--accent);
}

.extra-hint {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
}

.left-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.atlas__right {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding-left: 20px;
  overflow: hidden;
}
.right-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.right-header__label {
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
}
.right-header__controls {
  display: flex;
  align-items: center;
  gap: 12px;
}
.right-header__sep {
  width: 1px;
  height: 20px;
  background: var(--line);
  flex-shrink: 0;
}
.dry-run-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.dry-run-label__text {
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
}

.empty-state {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--muted);
  font-size: 14px;
}
.empty-state__icon {
  font-size: 48px;
  opacity: 0.6;
}

.course-grid {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  align-content: start;
  padding-bottom: 8px;
}
.course-card {
  transition: border-color 0.2s, background 0.2s;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.course-card--sel {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.course-card__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.course-card__icon {
  font-size: 24px;
  flex-shrink: 0;
}
.course-card__info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.course-card__name {
  font-weight: 600;
  font-size: 14px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.course-card__teacher {
  font-size: 12px;
  color: var(--muted);
}
.course-card__tags {
  display: flex;
  gap: 6px;
}
.course-card__progress-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.course-card__pct {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
  flex-shrink: 0;
}

.action-bar {
  flex-shrink: 0;
}
.action-bar__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--bg3) !important;
}
.action-bar__summary {
  font-size: 13px;
  color: var(--muted);
}
.action-bar__summary strong {
  color: var(--text);
  font-weight: 700;
}
.action-bar__buttons {
  display: flex;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 0.2s, opacity 0.2s;
}
.btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.btn--block {
  width: 100%;
}
.btn--sm {
  padding: 4px 12px;
  font-size: 12px;
}
.btn--outline {
  background: transparent;
  border-color: var(--line);
  color: var(--text);
}
.btn--outline:hover:not(:disabled) {
  background: var(--accent-soft);
}
.btn--primary {
  background: var(--accent);
  color: #fff;
}
.btn--primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

@media (max-width: 900px) {
  .course-grid {
    grid-template-columns: 1fr;
  }
}
</style>
