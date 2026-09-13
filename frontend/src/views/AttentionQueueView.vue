<template>
  <div class="attention">
    <!-- ── Main: Tickets ── -->
    <section class="attention__main">
      <div class="section-header">
        <div class="section-header__left">
          <h2 class="section-header__title">关注队列</h2>
          <span class="section-header__count">{{ attentionStore.unresolvedCount }}</span>
        </div>
        <div class="section-header__filters">
          <PillButton
            :active="attentionStore.severityFilter === 'all'"
            variant="default"
            @click="attentionStore.setSeverityFilter('all')"
          >全部</PillButton>
          <PillButton
            :active="attentionStore.severityFilter === 'critical'"
            variant="warn"
            @click="attentionStore.setSeverityFilter('critical')"
          >紧急</PillButton>
          <PillButton
            :active="attentionStore.severityFilter === 'warning'"
            variant="warn"
            @click="attentionStore.setSeverityFilter('warning')"
          >警告</PillButton>
          <PillButton
            :active="attentionStore.severityFilter === 'info'"
            variant="default"
            @click="attentionStore.setSeverityFilter('info')"
          >信息</PillButton>
          <span class="section-header__filter-sep"></span>
          <PillButton
            :active="attentionStore.platformFilter === 'all'"
            variant="default"
            @click="attentionStore.setPlatformFilter('all')"
          >全平台</PillButton>
          <PillButton
            v-for="p in platformStore.platforms"
            :key="p"
            :active="attentionStore.platformFilter === p"
            variant="default"
            @click="attentionStore.setPlatformFilter(p)"
          >{{ platformStore.metaFor(p).shortLabel }}</PillButton>
        </div>
      </div>

      <!-- tickets list -->
      <div v-if="filteredTickets.length" class="ticket-list">
        <div
          v-for="ticket in filteredTickets"
          :key="ticket.id"
          :class="['ticket', `ticket--${ticket.severity}`, { 'ticket--resolved': ticket.resolved }]"
        >
          <GlassmorphicCard class="ticket__card" padding="16px 20px">
            <div class="ticket__head">
              <h3 class="ticket__title">{{ ticket.title }}</h3>
              <span
                v-if="ticketPlatformMeta(ticket)"
                class="ticket__platform"
                :style="{ color: ticketPlatformMeta(ticket)!.color, borderColor: ticketPlatformMeta(ticket)!.color }"
              >{{ ticketPlatformMeta(ticket)!.shortLabel }}</span>
              <Chip :variant="severityChipVariant(ticket.severity)" size="sm">{{ severityLabel(ticket.severity) }}</Chip>
            </div>
            <p class="ticket__msg">
              <template v-for="(part, i) in messageParts(ticket.message)" :key="i">
                <a v-if="part.url" :href="part.text" target="_blank" rel="noopener noreferrer">{{ part.text }}</a>
                <template v-else>{{ part.text }}</template>
              </template>
            </p>
            <p v-if="ticket.resolution" class="ticket__resolution">{{ ticket.resolution }}</p>
            <div class="ticket__footer">
              <span class="ticket__time">{{ formatTime(ticket.createdAt) }}</span>
              <!-- Interactive tickets (captcha input / QR / slider hint) need the
                   popup modal, which delivers the response to the waiting Python
                   process. The generic 处理完成 button only dismisses the card
                   locally and would NOT unblock the backend — so for interactive
                   kinds we show guidance instead of a misleading button. -->
              <span v-if="ticket.kind === 'captcha' && !ticket.resolved" class="ticket__hint">
                ⚠ 请在弹窗中输入验证码处理
              </span>
              <span v-else-if="ticket.kind === 'qrcode' && !ticket.resolved" class="ticket__hint">
                ⚠ 请在弹窗中扫码登录，扫码成功后自动继续
              </span>
              <span v-else-if="ticket.kind === 'hint' && !ticket.resolved" class="ticket__hint">
                ⚠ 请按提示在浏览器窗口人工处理
              </span>
              <button
                v-else-if="!ticket.resolved"
                class="btn-ghost"
                @click="resolveTicket(ticket.id)"
              >处理完成</button>
              <span v-else class="ticket__done">已处理</span>
            </div>
          </GlassmorphicCard>
        </div>
      </div>

      <!-- empty -->
      <div v-else class="empty-state">
        <span class="empty-state__icon">✅</span>
        <p>暂无关注项 — 一切正常</p>
      </div>
    </section>

    <!-- ── Right Sidebar ── -->
    <aside class="attention__side">
      <!-- Live execution overview. Replaces the old "结果预测" card, which
           showed constants from DEFAULT_FORECAST and never moved no matter
           how far a task had actually progressed. -->
      <GlassmorphicPanel class="forecast" padding="18px">
        <h3 class="panel-title">执行概况</h3>
        <template v-if="hasRunData">
          <div class="forecast__progress">
            <div class="forecast__progress-head">
              <span class="forecast-item__label">整体进度</span>
              <span class="forecast-item__value">{{ Math.round(executionStore.progress) }}%</span>
            </div>
            <ProgressBar
              :percent="executionStore.progress"
              :variant="executionStore.status === 'error' ? 'warn' : executionStore.status === 'completed' ? 'ok' : 'accent'"
              height="8px"
            />
          </div>
          <div class="forecast-grid">
            <div class="forecast-item">
              <span class="forecast-item__value">{{ runningLanes }}/{{ executionStore.lanes.length }}</span>
              <span class="forecast-item__label">运行席位</span>
            </div>
            <div class="forecast-item">
              <span class="forecast-item__value">{{ attentionStore.unresolvedCount }}</span>
              <span class="forecast-item__label">人工介入</span>
            </div>
            <div :class="['forecast-item', `forecast-item--${statusColorKey}`]">
              <span class="forecast-item__value">{{ statusBadge }}</span>
              <span class="forecast-item__label">{{ statusLabel }}</span>
            </div>
            <div class="forecast-item">
              <span class="forecast-item__value">{{ executionStore.elapsedFormatted }}</span>
              <span class="forecast-item__label">耗时</span>
            </div>
          </div>
        </template>
        <div v-else class="forecast__empty">暂无执行数据 — 启动任务后此处显示实时进度</div>
      </GlassmorphicPanel>

      <!-- Operator Feed -->
      <GlassmorphicPanel class="feed" padding="18px">
        <h3 class="panel-title">执行日志</h3>
        <div class="feed__entries">
          <div
            v-for="line in logStore.recentLines"
            :key="line.id"
            :class="['feed__entry', `feed__entry--${line.level}`]"
          >
            <span class="feed__time">{{ line.time }}</span>
            <span class="feed__msg">{{ line.message }}</span>
          </div>
          <div v-if="!logStore.recentLines.length" class="feed__empty">暂无日志条目</div>
        </div>
      </GlassmorphicPanel>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import GlassmorphicPanel from '@/shared/ui/GlassmorphicPanel.vue'
import GlassmorphicCard from '@/shared/ui/GlassmorphicCard.vue'
import Chip from '@/shared/ui/Chip.vue'
import PillButton from '@/shared/ui/PillButton.vue'
import ProgressBar from '@/shared/ui/ProgressBar.vue'
import { useAttentionStore } from '@/app/stores/attention.store'
import { useExecutionStore } from '@/app/stores/execution.store'
import { useLogStore } from '@/app/stores/log.store'
import { usePlatformStore } from '@/app/stores/platform.store'
import { PLATFORM_META } from '@/shared/lib/platforms'
import type { Ticket, TicketSeverity } from '@/shared/lib/types'

const attentionStore = useAttentionStore()
const executionStore = useExecutionStore()
const logStore = useLogStore()
const platformStore = usePlatformStore()

/* ── computed ── */

const hasRunData = computed(() =>
  executionStore.phases.length > 0 || executionStore.status !== 'idle',
)

const runningLanes = computed(() =>
  executionStore.lanes.filter((lane) => lane.status === 'running').length,
)

const statusColorKey = computed(() => {
  switch (executionStore.status) {
    case 'running': return 'low'
    case 'paused': return 'medium'
    case 'completed': return 'low'
    case 'error': return 'high'
    default: return 'medium'
  }
})

const statusBadge = computed(() => {
  switch (executionStore.status) {
    case 'running': return '▶'
    case 'paused': return '⏸'
    case 'completed': return '✓'
    case 'error': return '✕'
    case 'stopped': return '⏹'
    default: return '·'
  }
})

const statusLabel = computed(() => {
  switch (executionStore.status) {
    case 'running': return '运行中'
    case 'paused': return '已暂停'
    case 'completed': return '已完成'
    case 'error': return '执行失败'
    case 'stopped': return '已停止'
    default: return '空闲'
  }
})

const filteredTickets = computed(() => attentionStore.filteredTickets)

/* ── helpers ── */

function ticketPlatformMeta(ticket: Ticket) {
  return ticket.platform ? PLATFORM_META[ticket.platform] : null
}

/** Split message text / URL segments so appeal links (e.g. zhihuishu course
 *  lock warnings) render as clickable anchors without v-html. */
const URL_PATTERN = /https?:\/\/[^\s）)】\]，,。]+/g
function messageParts(message: string): Array<{ text: string; url?: boolean }> {
  const parts: Array<{ text: string; url?: boolean }> = []
  let last = 0
  for (const match of message.matchAll(URL_PATTERN)) {
    const index = match.index ?? 0
    if (index > last) parts.push({ text: message.slice(last, index) })
    parts.push({ text: match[0], url: true })
    last = index + match[0].length
  }
  if (last < message.length) parts.push({ text: message.slice(last) })
  return parts
}

function severityLabel(s: TicketSeverity): string {
  if (s === 'critical') return '需处理'
  if (s === 'warning') return '需复核'
  return '观察'
}

function severityChipVariant(s: TicketSeverity): 'warn' | 'gold' | 'muted' | 'accent' | 'ok' {
  if (s === 'critical') return 'warn'
  if (s === 'warning') return 'gold'
  return 'muted'
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

async function resolveTicket(id: string): Promise<void> {
  await attentionStore.resolveTicket(id, '手动处理完成')
}
</script>

<style scoped>
.attention {
  display: flex;
  gap: 24px;
  height: 100%;
}

/* ── Main ── */
.attention__main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: hidden;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
}
.section-header__left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-header__title {
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
}
.section-header__count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--accent);
  color: #fff;
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 700;
}
.section-header__filters {
  display: flex;
  align-items: center;
  gap: 6px;
}
.section-header__filter-sep {
  width: 1px;
  height: 18px;
  background: var(--line);
  margin: 0 4px;
}

/* ── Tickets ── */
.ticket-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}
.ticket {
  border-left: 4px solid transparent;
  border-radius: var(--radius-md);
  transition: border-color 0.2s;
}
.ticket--critical { border-left-color: var(--warn); }
.ticket--warning { border-left-color: var(--gold); }
.ticket--info { border-left-color: var(--muted); }
.ticket--resolved { opacity: 0.55; }

.ticket__card {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ticket__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.ticket__title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text);
  flex: 1;
  min-width: 0;
}
.ticket__platform {
  flex-shrink: 0;
  padding: 1px 8px;
  border: 1px solid var(--line);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
.ticket__msg {
  font-size: 13px;
  color: var(--muted);
  line-height: 1.4;
  word-break: break-word;
}
.ticket__msg a {
  color: var(--accent);
}
.ticket__resolution {
  font-size: 12px;
  color: var(--ok);
  background: var(--ok-soft);
  padding: 6px 10px;
  border-radius: var(--radius-sm);
}
.ticket__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ticket__time {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--muted);
}
.ticket__done {
  font-size: 12px;
  color: var(--ok);
  font-weight: 600;
}
.ticket__hint {
  font-size: 12px;
  color: var(--warn, #d9803a);
  font-weight: 600;
}
.btn-ghost {
  background: none;
  border: 1px solid var(--line);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 12px;
  padding: 4px 14px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s;
}
.btn-ghost:hover {
  background: var(--accent-soft);
}

/* ── Empty ── */
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
.empty-state__icon { font-size: 40px; opacity: 0.6; }

/* ── Side ── */
.attention__side {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.panel-title {
  font-family: var(--font-display);
  font-size: 14px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 12px;
}

/* ── Forecast ── */
.forecast-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.forecast-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.forecast-item__value {
  font-family: var(--font-display);
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
}
.forecast-item--low .forecast-item__value { color: var(--ok); }
.forecast-item--medium .forecast-item__value { color: var(--gold); }
.forecast__progress {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}
.forecast__progress-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.forecast__empty {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.6;
  padding: 8px 0;
}
.forecast-item--high .forecast-item__value { color: var(--warn); }
.forecast-item__label {
  font-size: 11px;
  color: var(--muted);
}

/* ── Feed ── */
.feed {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.feed__entries {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-family: var(--font-mono);
}
.feed__entry {
  display: flex;
  gap: 8px;
  font-size: 11px;
  line-height: 1.5;
  padding: 4px 0;
  border-bottom: 1px solid var(--line);
}
.feed__entry--warn .feed__msg { color: var(--gold); }
.feed__entry--error .feed__msg { color: var(--warn); }
.feed__time {
  color: var(--muted);
  flex-shrink: 0;
}
.feed__msg {
  color: var(--text);
  word-break: break-all;
}
.feed__empty {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  padding: 16px 0;
}

@media (max-width: 800px) {
  .attention {
    flex-direction: column;
  }
  .attention__side {
    width: 100%;
  }
}
</style>
