<template>
  <div class="log-console">
    <div class="log-console__header">
      <span class="log-console__title">日志控制台</span>
      <span class="log-console__counts">
        <span class="log-console__count log-console__count--info">{{ logStore.infoCount }}</span>
        <span class="log-console__count log-console__count--warn">{{ logStore.warnCount }}</span>
        <span class="log-console__count log-console__count--error">{{ logStore.errorCount }}</span>
      </span>
      <button
        class="log-console__action"
        title="清空日志"
        @click="logStore.clearLogs()"
      >清空</button>
      <button
        class="log-console__action"
        :title="logStore.autoScroll ? '停止滚动' : '自动滚动'"
        @click="logStore.toggleAutoScroll()"
      >{{ logStore.autoScroll ? '⊟' : '⊞' }}</button>
      <button
        class="log-console__action"
        title="折叠"
        @click="logStore.toggleCollapsed()"
      >×</button>
    </div>
    <div ref="outputEl" class="log-console__output">
      <div
        v-for="entry in logStore.lines"
        :key="entry.id"
        :class="['log-entry', `log-entry--${entry.level}`]"
      >
        <span class="log-entry__time">{{ entry.time }}</span>
        <span class="log-entry__source" v-if="entry.source">[{{ entry.source }}]</span>
        <span class="log-entry__msg">{{ entry.message }}</span>
      </div>
      <div v-if="logStore.lines.length === 0" class="log-console__empty">暂无日志</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useLogStore } from '@/app/stores/log.store'

const logStore = useLogStore()
const outputEl = ref<HTMLElement | null>(null)

// Auto-scroll to bottom when new lines arrive
watch(
  () => logStore.lines.length,
  async () => {
    if (logStore.autoScroll && outputEl.value) {
      await nextTick()
      outputEl.value.scrollTop = outputEl.value.scrollHeight
    }
  },
)
</script>

<style scoped>
.log-console {
  flex-shrink: 0;
  background: var(--bg2);
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 12px;
  max-height: 180px;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--line);
}

.log-console__header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: var(--bg3);
  border-bottom: 1px solid var(--line);
}

.log-console__title {
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--muted);
  margin-right: auto;
}

.log-console__counts {
  display: flex;
  gap: 4px;
}

.log-console__count {
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  font-weight: 600;
  line-height: 16px;
}

.log-console__count--info {
  background: var(--accent-soft);
  color: var(--accent);
}

.log-console__count--warn {
  background: var(--warn-soft);
  color: var(--warn);
}

.log-console__count--error {
  background: rgba(220, 38, 38, 0.12);
  color: #dc2626;
}

.log-console__action {
  background: none;
  border: none;
  color: var(--muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  line-height: 1;
}

.log-console__action:hover {
  background: var(--accent-soft);
  color: var(--text);
}

.log-console__output {
  flex: 1;
  overflow-y: auto;
  padding: 4px 12px;
}

.log-console__empty {
  color: var(--muted);
  font-style: italic;
  padding: 4px 0;
}

.log-entry {
  padding: 1px 0;
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.log-entry__time {
  color: var(--muted);
  flex-shrink: 0;
}

.log-entry__source {
  color: var(--accent);
  flex-shrink: 0;
  font-size: 11px;
}

.log-entry--info .log-entry__msg {
  color: var(--text);
}

.log-entry--warn .log-entry__msg {
  color: var(--warn);
}

.log-entry--error .log-entry__msg {
  color: #dc2626;
}

.log-entry--debug .log-entry__msg {
  color: var(--muted);
}
</style>
