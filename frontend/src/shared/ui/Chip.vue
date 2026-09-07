<template>
  <span class="chip" :class="[`chip--${variant}`, `chip--${size}`]">
    <slot />
  </span>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  variant?: 'accent' | 'ok' | 'warn' | 'gold' | 'muted'
  size?: 'sm' | 'md'
}>(), {
  variant: 'muted',
  size: 'sm',
})
</script>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  font-family: var(--font-ui);
  white-space: nowrap;
  line-height: 1;
}

.chip--sm {
  padding: 2px 10px;
  font-size: 11px;
}

.chip--md {
  padding: 4px 14px;
  font-size: 13px;
}

.chip--accent {
  background: var(--accent-soft);
  color: var(--accent);
}

.chip--ok {
  background: var(--ok-soft);
  color: var(--ok);
}

.chip--warn {
  background: var(--warn-soft);
  color: var(--warn);
}

.chip--gold {
  background: var(--gold-soft);
  color: var(--gold);
}

.chip--muted {
  background: var(--line);
  color: var(--muted);
}
</style>
