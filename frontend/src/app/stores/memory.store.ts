import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { MemoryEvent, MemoryPlan } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'
import { useLogStore } from '@/app/stores/log.store'

export const useMemoryStore = defineStore('memory', () => {
  const latest = ref<MemoryEvent | null>(null)
  const plan = ref<MemoryPlan | null>(null)
  const running = ref(false)
  const api = createApiClient()
  let cleanup: (() => void) | null = null
  let planFailLogged = false

  function start(): void {
    if (cleanup) return
    running.value = true
    cleanup = api.onMemory((e) => { latest.value = e })
  }

  function stop(): void {
    cleanup?.()
    cleanup = null
    running.value = false
  }

  function setPlan(value: MemoryPlan | null): void {
    plan.value = value
  }

  async function refreshPlan(): Promise<void> {
    try {
      plan.value = await api.getMemoryPlan()
      planFailLogged = false
    } catch {
      if (!planFailLogged) {
        planFailLogged = true
        useLogStore().addLog('warn', '无法读取内存计划，仪表显示最后一次结果。', '内存')
      }
    }
  }

  return { latest, plan, running, start, stop, setPlan, refreshPlan }
})
