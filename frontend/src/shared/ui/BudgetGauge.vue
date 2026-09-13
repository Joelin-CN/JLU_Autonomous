<template>
  <div :class="['gauge', `gauge--${band}`, { 'gauge--compact': compact }]">
    <div class="gauge__number">{{ remainingCount ?? '—' }}</div>
    <div class="gauge__label">剩余可开实例</div>
    <div class="gauge__bar">
      <div class="gauge__fill" :style="{ width: pct + '%' }"></div>
    </div>
    <div class="gauge__meta">
      预算 {{ plan?.budgetGB.toFixed(1) ?? '—' }} GB · 上限 = min(内存, CPU)
      <span v-if="mock"> · 模拟数据</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MemoryPlan } from '@/shared/lib/types'

const props = withDefaults(defineProps<{
  plan: MemoryPlan | null
  projectChromeGB?: number
  remainingCount?: number | null
  mock?: boolean
  /** 紧凑横排变体：执行页分平台内存面板用（设置页保持大数字卡片）。 */
  compact?: boolean
}>(), {
  projectChromeGB: 0,
  remainingCount: null,
  mock: false,
  compact: false,
})

const pct = computed(() => {
  if (!props.plan || props.plan.budgetGB <= 0) return 0
  return Math.min(100, Math.max(0, (props.projectChromeGB ?? 0) / props.plan.budgetGB * 100))
})

const band = computed(() => (pct.value < 60 ? 'ok' : pct.value < 85 ? 'warn' : 'danger'))
</script>

<style scoped>
.gauge {
  padding: 18px;
  border-radius: var(--radius);
  border: 1px solid var(--line);
  background: var(--bg);
}
.gauge__number {
  font-family: var(--font-display);
  font-size: 34px;
  font-weight: 700;
  color: var(--text);
  line-height: 1;
}
.gauge__label {
  font-size: 12px;
  color: var(--muted);
  margin: 4px 0 12px;
}
.gauge__bar {
  height: 8px;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}
.gauge__fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.3s ease;
}
.gauge--ok .gauge__fill { background: var(--ok); }
.gauge--warn .gauge__fill { background: var(--warn); }
.gauge--danger .gauge__fill { background: var(--danger, #e5484d); }
.gauge__meta {
  margin-top: 10px;
  font-size: 11px;
  color: var(--muted);
}

/* ── Compact 横排变体（执行页）── */
.gauge--compact {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 0;
  border: none;
  background: transparent;
}
.gauge--compact .gauge__number {
  font-size: 22px;
  min-width: 36px;
  text-align: center;
}
.gauge--compact .gauge__label {
  margin: 0;
  font-size: 11px;
  white-space: nowrap;
}
.gauge--compact .gauge__bar {
  flex: 1;
  height: 6px;
}
.gauge--compact .gauge__meta {
  margin: 0;
  white-space: nowrap;
}
</style>
