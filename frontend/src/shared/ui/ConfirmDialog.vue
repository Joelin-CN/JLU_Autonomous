<template>
  <div v-if="open" class="dialog-mask" @click.self="$emit('cancel')">
    <div class="dialog" role="dialog" aria-modal="true">
      <h3 class="dialog__title">{{ title }}</h3>
      <p class="dialog__message">{{ message }}</p>
      <div class="dialog__actions">
        <button type="button" class="dialog__btn" @click="$emit('cancel')">取消</button>
        <button type="button" class="dialog__btn dialog__btn--danger" @click="$emit('confirm')">
          {{ confirmLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  open: boolean
  title: string
  message: string
  confirmLabel?: string
}>(), {
  confirmLabel: '删除',
})

defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
}
.dialog {
  width: 360px;
  padding: 22px;
  border-radius: var(--radius);
  background: var(--bg);
  border: 1px solid var(--line);
}
.dialog__title {
  font-family: var(--font-display);
  font-size: 16px;
  color: var(--text);
}
.dialog__message {
  margin: 10px 0 18px;
  font-size: 13px;
  color: var(--muted);
}
.dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.dialog__btn {
  padding: 6px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 13px;
  cursor: pointer;
}
.dialog__btn--danger {
  background: var(--warn-soft);
  border-color: var(--warn-soft);
  color: var(--warn);
}
</style>
