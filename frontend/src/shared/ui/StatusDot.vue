<template>
  <span
    class="status-dot"
    :class="[`status-dot--${status}`, `status-dot--${size}`]"
    :title="status"
  />
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  status: 'online' | 'offline' | 'running' | 'idle' | 'error' | 'done'
  size?: 'sm' | 'md'
}>(), {
  size: 'md',
})
</script>

<style scoped>
.status-dot {
  display: inline-block;
  border-radius: 50%;
  flex-shrink: 0;
  transition: background-color 0.3s ease;
}

.status-dot--sm { width: 8px; height: 8px; }
.status-dot--md { width: 10px; height: 10px; }

.status-dot--online,
.status-dot--done {
  background: var(--ok);
  box-shadow: 0 0 6px var(--ok);
}

.status-dot--running {
  background: var(--accent);
  animation: pulse-dot 1.2s ease-in-out infinite;
}

.status-dot--error {
  background: var(--warn);
}

.status-dot--offline,
.status-dot--idle {
  background: var(--muted);
}

@keyframes pulse-dot {
  0%, 100% { box-shadow: 0 0 4px var(--accent); }
  50%      { box-shadow: 0 0 12px var(--accent); }
}
</style>
