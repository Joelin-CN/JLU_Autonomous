<template>
  <div class="glass-panel" :class="{ 'glass-panel--no-border': noBorder }" :style="{ padding }">
    <slot />
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  padding?: string
  noBorder?: boolean
}>(), {
  padding: '20px',
  noBorder: false,
})
</script>

<style scoped>
.glass-panel {
  background: var(--panel);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  border-radius: var(--radius-lg);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: var(--shadow);
}

.glass-panel--no-border {
  border: none;
}
</style>
