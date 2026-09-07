<template>
  <div class="masked">
    <div class="masked__row">
      <input
        class="masked__input"
        :type="show ? 'text' : 'password'"
        :value="modelValue"
        :placeholder="placeholder"
        autocomplete="off"
        @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
      />
      <button type="button" class="masked__toggle" @click="show = !show">
        {{ show ? '隐藏' : '显示' }}
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  modelValue: string
  placeholder?: string
}>()

defineEmits<{
  'update:modelValue': [value: string]
}>()

const show = ref(false)
</script>

<style scoped>
.masked__row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.masked__input {
  flex: 1;
  max-width: 320px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 13px;
  outline: none;
}
.masked__input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.masked__toggle {
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--muted);
  font-family: var(--font-ui);
  font-size: 12px;
  cursor: pointer;
}
</style>
