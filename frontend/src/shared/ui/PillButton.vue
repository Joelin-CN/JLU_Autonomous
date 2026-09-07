<template>
  <button
    type="button"
    class="pill-btn"
    :class="[
      `pill-btn--${variant}`,
      { 'pill-btn--active': active },
    ]"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  active?: boolean
  variant?: 'accent' | 'ok' | 'warn' | 'default'
}>(), {
  active: false,
  variant: 'default',
})

defineEmits<{
  click: []
}>()
</script>

<style scoped>
.pill-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 18px;
  border-radius: 999px;
  border: 1px solid var(--line);
  background: var(--panel);
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 13px;
  cursor: pointer;
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.15s ease;
  outline: none;
}

.pill-btn:hover {
  transform: translateY(-1px);
}

.pill-btn:focus-visible {
  box-shadow: 0 0 0 2px var(--accent-soft);
}

.pill-btn--active.pill-btn--accent {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.pill-btn--active.pill-btn--ok {
  background: var(--ok);
  color: #fff;
  border-color: var(--ok);
}

.pill-btn--active.pill-btn--warn {
  background: var(--warn);
  color: #fff;
  border-color: var(--warn);
}

.pill-btn--active.pill-btn--default {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
</style>
