import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { MemoryEvent, MemoryPlan, Platform } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'
import { useLogStore } from '@/app/stores/log.store'

/**
 * 内存事件/计划 —— 按平台分桶。双平台并行时两路 MEMORY 事件（主进程已按槽位
 * 盖 platform 章）各入各桶；单仪表视图（设置/仪表盘）读兼容 getter `latest`
 * 与 `plan`（最近一路 / 全局计划）。
 */
export const useMemoryStore = defineStore('memory', () => {
  const latestByPlatform = ref<Partial<Record<Platform, MemoryEvent>>>({})
  const planByPlatform = ref<Partial<Record<Platform, MemoryPlan>>>({})
  /** memory:plan IPC 的全局口径（无任务时的仪表兜底）。 */
  const globalPlan = ref<MemoryPlan | null>(null)
  const running = ref(false)
  const api = createApiClient()
  let cleanup: (() => void) | null = null
  let planFailLogged = false
  let lastPlatform: Platform | null = null

  /** 兼容单仪表视图：最近一路事件（两路事件交替到达时随之切换）。 */
  const latest = computed<MemoryEvent | null>(() =>
    lastPlatform ? (latestByPlatform.value[lastPlatform] ?? null) : null)
  /** 兼容单仪表视图：最近一路的平台份额计划，无任务时回落全局计划。 */
  const plan = computed<MemoryPlan | null>(() =>
    (lastPlatform ? planByPlatform.value[lastPlatform] : undefined) ?? globalPlan.value)

  function latestFor(platform: Platform): MemoryEvent | null {
    return latestByPlatform.value[platform] ?? null
  }

  function planFor(platform: Platform): MemoryPlan | null {
    return planByPlatform.value[platform] ?? globalPlan.value
  }

  function start(): void {
    running.value = true
    if (cleanup) return
    cleanup = api.onMemory((e) => {
      const p = e.platform
      if (p === 'chaoxing' || p === 'zhihuishu') {
        latestByPlatform.value = { ...latestByPlatform.value, [p]: e }
        lastPlatform = p
      }
    })
  }

  function stop(): void {
    // 只降标志、不注销订阅：双平台并行时另一平台的 MEMORY 事件仍需送达
    // （一个任务结束不应掐掉另一路的仪表）。
    running.value = false
  }

  /** 写某平台的任务份额计划；platform=null 时清空全部任务份额。 */
  function setPlan(platform: Platform | null, value: MemoryPlan | null = null): void {
    if (platform === null) {
      planByPlatform.value = {}
      return
    }
    planByPlatform.value = { ...planByPlatform.value, [platform]: value }
  }

  async function refreshPlan(): Promise<void> {
    try {
      globalPlan.value = await api.getMemoryPlan()
      planFailLogged = false
    } catch {
      if (!planFailLogged) {
        planFailLogged = true
        useLogStore().addLog('warn', '无法读取内存计划，仪表显示最后一次结果。', '内存')
      }
    }
  }

  return {
    latestByPlatform,
    planByPlatform,
    globalPlan,
    latest,
    plan,
    running,
    latestFor,
    planFor,
    start,
    stop,
    setPlan,
    refreshPlan,
  }
})
