import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Platform } from '@/shared/lib/types'
import { PLATFORM_META, PLATFORM_CAPABILITIES, PLATFORMS, isPlatform } from '@/shared/lib/platforms'

const STORAGE_KEY = 'jlu-study-assistant-platform'

function loadPersistedPlatform(): Platform {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (isPlatform(raw)) return raw
  } catch {
    // storage unavailable — default below
  }
  return 'chaoxing'
}

/**
 * 全局平台上下文 —— 平台是应用的一级维度，所有视图（账号/课程/任务/工单）
 * 共享 currentPlatform，而不是各自维护局部状态。
 *
 * switchPlatform 负责跨 store 编排（运行守卫、清选择、按平台刷新账号）；
 * 依赖的 store 通过动态 import 解入，避免模块级循环依赖。
 */
export const usePlatformStore = defineStore('platform', () => {
  const currentPlatform = ref<Platform>(loadPersistedPlatform())

  const meta = computed(() => PLATFORM_META[currentPlatform.value])
  const capabilities = computed(() => PLATFORM_CAPABILITIES[currentPlatform.value])

  /** 跨平台读取展示属性（仪表盘分块、侧栏双平台状态行）。 */
  function metaFor(platform: Platform) {
    return PLATFORM_META[platform]
  }

  function setPlatform(next: Platform): void {
    if (next === currentPlatform.value) return
    if (!isPlatform(next)) return
    currentPlatform.value = next
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // persist best-effort; in-memory switch still applies
    }
  }

  /**
   * 切换当前平台。账号/课程数据按平台分桶缓存，任务也按平台独立槽位运行
   * （双平台并行），因此任务运行中允许切换 —— 切换的只是 UI 上下文。
   * 编排：清空账号/课程选择 → 重置课程激活账号 → 强制按新平台刷新账号列表。
   */
  async function switchPlatform(next: Platform): Promise<boolean> {
    if (next === currentPlatform.value) return true

    setPlatform(next)

    const [{ useAccountStore }, { useCourseStore }] = await Promise.all([
      import('@/app/stores/account.store'),
      import('@/app/stores/course.store'),
    ])
    useCourseStore().resetActiveAccount()
    useCourseStore().deselectAllCourses()
    const accountStore = useAccountStore()
    accountStore.deselectAll()
    await accountStore.fetchAccounts(next, { force: true })
    return true
  }

  return {
    platforms: PLATFORMS,
    currentPlatform,
    meta,
    capabilities,
    metaFor,
    setPlatform,
    switchPlatform,
  }
})
