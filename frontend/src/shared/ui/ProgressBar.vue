<template>
  <div
    class="progress-bar-track"
    :style="{ height }"
    role="progressbar"
    :aria-valuenow="indeterminate ? undefined : Math.round(clampedPercent)"
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <div
      v-if="indeterminate"
      class="progress-bar-fill progress-bar-fill--indeterminate"
      :class="`progress-bar-fill--${variant}`"
    />
    <div
      v-else
      class="progress-bar-fill"
      :class="`progress-bar-fill--${variant}`"
      :style="{ width: clampedPercent + '%' }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  percent?: number
  variant?: 'accent' | 'ok' | 'warn' | 'gold'
  height?: string
  /** No measurable fraction yet (phase just started) — show a flowing
   *  animation instead of a misleading 0%/100% value. */
  indeterminate?: boolean
}>(), {
  percent: 0,
  variant: 'accent',
  height: '8px',
  indeterminate: false,
})

const clampedPercent = computed(() => Math.max(0, Math.min(100, props.percent)))
</script>

<style scoped>
.progress-bar-track {
  width: 100%;
  border-radius: 999px;
  background: var(--line);
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
  background: var(--accent);
}

.progress-bar-fill--accent { background: var(--accent); }
.progress-bar-fill--ok     { background: var(--ok); }
.progress-bar-fill--warn   { background: var(--warn); }
.progress-bar-fill--gold   { background: var(--gold); }

/* Indeterminate: a short segment flowing across the track. Pure CSS, so it
   costs nothing and needs no timer in the store. */
.progress-bar-fill--indeterminate {
  width: 30%;
  animation: progress-bar-flow 1.4s ease-in-out infinite;
}

@keyframes progress-bar-flow {
  0%   { margin-left: -30%; }
  100% { margin-left: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .progress-bar-fill--indeterminate {
    animation: none;
    width: 100%;
    opacity: 0.35;
  }
}
</style>
