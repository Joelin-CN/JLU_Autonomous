<template>
  <div class="filepicker">
    <span class="filepicker__label">{{ label }}</span>
    <div class="filepicker__row">
      <span class="filepicker__value" :title="modelValue || defaultPath">
        {{ modelValue || defaultPath || '未指定（使用默认路径）' }}
        <span v-if="!modelValue && defaultPath" class="filepicker__badge">默认</span>
      </span>
      <button type="button" class="filepicker__btn" @click="pick">选择文件</button>
      <button v-if="modelValue" type="button" class="filepicker__btn" @click="$emit('update:modelValue', '')">
        恢复默认
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { createApiClient } from '@/shared/lib/apiClient'

defineProps<{
  modelValue: string
  label: string
  defaultPath?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const api = createApiClient()

async function pick(): Promise<void> {
  const path = await api.openFilePicker()
  if (path) emit('update:modelValue', path)
}
</script>

<style scoped>
.filepicker { display: flex; flex-direction: column; gap: 6px; }
.filepicker__label { font-size: 13px; font-weight: 600; color: var(--text); }
.filepicker__row { display: flex; align-items: center; gap: 8px; }
.filepicker__value {
  flex: 1;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.filepicker__badge {
  margin-left: 6px;
  padding: 1px 8px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-family: var(--font-ui);
  font-size: 10px;
}
.filepicker__btn {
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--line);
  background: transparent;
  color: var(--text);
  font-family: var(--font-ui);
  font-size: 12px;
  cursor: pointer;
}
</style>
