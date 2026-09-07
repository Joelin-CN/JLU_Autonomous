import { defineStore } from 'pinia'
import { ref, computed, nextTick } from 'vue'
import type { LogLine } from '@/shared/lib/types'

const MAX_LINES = 500

let nextId = 1

export const useLogStore = defineStore('log', () => {
  const lines = ref<LogLine[]>([])
  const collapsed = ref(false)
  const autoScroll = ref(true)

  /* computed */

  const recentLines = computed(() => lines.value.slice(-50))

  const infoCount = computed(
    () => lines.value.filter((l) => l.level === 'info').length,
  )
  const warnCount = computed(
    () => lines.value.filter((l) => l.level === 'warn').length,
  )
  const errorCount = computed(
    () => lines.value.filter((l) => l.level === 'error').length,
  )

  /* actions */

  function addLog(
    level: LogLine['level'],
    message: string,
    source?: string,
  ): void {
    const ts = Date.now()
    const d = new Date(ts)
    const hh = String(d.getHours()).padStart(2, '0')
    const mm = String(d.getMinutes()).padStart(2, '0')
    const ss = String(d.getSeconds()).padStart(2, '0')
    const entry: LogLine = {
      id: nextId++,
      timestamp: ts,
      time: `${hh}:${mm}:${ss}`,
      level,
      message,
      source,
    }
    lines.value.push(entry)

    // Enforce line limit
    if (lines.value.length > MAX_LINES) {
      lines.value = lines.value.slice(-MAX_LINES)
    }
  }

  function clearLogs(): void {
    lines.value = []
    nextId = 1
  }

  function toggleCollapsed(): void {
    collapsed.value = !collapsed.value
  }

  function toggleAutoScroll(): void {
    autoScroll.value = !autoScroll.value
  }

  return {
    lines,
    collapsed,
    autoScroll,
    recentLines,
    infoCount,
    warnCount,
    errorCount,
    addLog,
    clearLogs,
    toggleCollapsed,
    toggleAutoScroll,
  }
})
