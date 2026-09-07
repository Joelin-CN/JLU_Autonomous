<template>
  <div
    class="glass-card"
    :class="{ 'glass-card--clickable': clickable }"
    :style="{ padding }"
    @click="handleClick"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  padding?: string
  clickable?: boolean
}>(), {
  padding: '16px',
  clickable: false,
})

const emit = defineEmits<{
  click: []
}>()

function handleClick() {
  if (props.clickable) {
    emit('click')
  }
}
</script>

<style scoped>
.glass-card {
  background: var(--panel);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-radius: var(--radius-md);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: var(--shadow);
}

.glass-card--clickable {
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.glass-card--clickable:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-lg);
}
</style>
