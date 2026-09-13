import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import type { Course, Platform } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'
import { usePlatformStore } from '@/app/stores/platform.store'

const api = createApiClient()

function addToSet(setRef: { value: Set<string> }, id: string): void {
  const next = new Set(setRef.value)
  next.add(id)
  setRef.value = next
}

function removeFromSet(setRef: { value: Set<string> }, id: string): void {
  const next = new Set(setRef.value)
  next.delete(id)
  setRef.value = next
}

/**
 * 课程 store —— 缓存按 `platform:accountId` 复合键分桶：账号 id 是各平台
 * 凭据文件里的 0 基行号，两个平台的「账号 0」若共用一个键会互相覆盖。
 * 对外 API 仍以 accountId 表达；内部自动限定在当前平台的桶内。
 */
export const useCourseStore = defineStore('course', () => {
  const platformStore = usePlatformStore()

  const coursesByAccount = ref<Record<string, Course[]>>({})
  const activeAccountId = ref<string | null>(null)
  const selectedCourseIds = ref<Set<string>>(new Set())
  const loadedAccountIds = ref<Set<string>>(new Set())
  const scannedAccountIds = ref<Set<string>>(new Set())
  const loadingAccountIds = ref<Set<string>>(new Set())
  const scanningAccountIds = ref<Set<string>>(new Set())
  const error = ref<string | null>(null)

  const pendingFetches = new Map<string, Promise<void>>()
  const pendingScans = new Map<string, Promise<void>>()

  /** Bucket key: platform-scoped so per-platform file line numbers never collide. */
  function bucketKey(accountId: string): string {
    return `${platformStore.currentPlatform}:${accountId}`
  }

  const loading = computed(() => loadingAccountIds.value.size > 0)
  const scanning = computed(() => scanningAccountIds.value.size > 0)

  /** 当前平台所有已加载账号的课程（扁平）。 */
  const allCourses = computed(() => {
    const prefix = `${platformStore.currentPlatform}:`
    return Object.entries(coursesByAccount.value)
      .filter(([key]) => key.startsWith(prefix))
      .flatMap(([, courses]) => courses)
  })

  const activeCourses = computed(() => {
    if (!activeAccountId.value) return []
    return coursesByAccount.value[bucketKey(activeAccountId.value)] ?? []
  })

  /** 当前平台某账号的课程（视图按账号计数用；内部限定当前平台桶）。 */
  function coursesForAccount(accountId: string): Course[] {
    return coursesByAccount.value[bucketKey(accountId)] ?? []
  }

  const selectedCourses = computed(() =>
    allCourses.value.filter((course) => selectedCourseIds.value.has(course.id)),
  )

  const hasSelection = computed(() => selectedCourseIds.value.size > 0)

  // Course ids are platform-scoped too; drop selection + active account when
  // the platform context changes so stale cross-platform ids never leak into
  // a startJob payload.
  watch(() => platformStore.currentPlatform, () => {
    selectedCourseIds.value = new Set()
    activeAccountId.value = null
  })

  function getTargetAccountId(accountId?: string): string {
    return accountId ?? activeAccountId.value ?? 'default'
  }

  function setCoursesForAccount(accountId: string, courses: Course[], platform = platformStore.currentPlatform): void {
    const key = `${platform}:${accountId}`
    const tagged = courses.map((c) => ({ ...c, platform: c.platform ?? platform }))
    coursesByAccount.value = {
      ...coursesByAccount.value,
      [key]: tagged,
    }
    addToSet(loadedAccountIds, key)
    // Non-empty course data is positive evidence the account has been scanned.
    if (tagged.length > 0) {
      addToSet(scannedAccountIds, key)
    }
  }

  async function fetchCourses(accountId?: string, platform?: Platform): Promise<void> {
    const targetId = getTargetAccountId(accountId)
    const scopedPlatform = platform ?? platformStore.currentPlatform
    const key = `${scopedPlatform}:${targetId}`
    if (pendingFetches.has(key)) {
      return pendingFetches.get(key)!
    }
    if (loadedAccountIds.value.has(key) && coursesByAccount.value[key]) {
      return
    }

    error.value = null
    addToSet(loadingAccountIds, key)

    const request = (async () => {
      try {
        const courses = await api.getCourses(targetId, scopedPlatform)
        setCoursesForAccount(targetId, courses, scopedPlatform)
      } catch (e: any) {
        error.value = e?.message ?? 'Failed to fetch courses'
      } finally {
        removeFromSet(loadingAccountIds, key)
        pendingFetches.delete(key)
      }
    })()

    pendingFetches.set(key, request)
    return request
  }

  /** platform 缺省 = 当前 UI 平台；任务完成回读时显式传「任务自己的平台」，
   *  避免双平台并行时把智慧树的发现文件读进超星的桶（反之亦然）。 */
  async function scanCourses(accountId?: string, platform?: Platform): Promise<void> {
    const targetId = getTargetAccountId(accountId)
    const scopedPlatform = platform ?? platformStore.currentPlatform
    const key = `${scopedPlatform}:${targetId}`
    if (pendingScans.has(key)) {
      return pendingScans.get(key)!
    }

    error.value = null
    addToSet(scanningAccountIds, key)

    const request = (async () => {
      try {
        const courses = await api.scanCourses(
          targetId && targetId !== 'default' ? [targetId] : undefined,
          scopedPlatform,
        )
        setCoursesForAccount(targetId, courses, scopedPlatform)
        // scanCourses re-reads the persisted discovery state — a successful
        // read (even when empty) means the account has been scanned already.
        addToSet(scannedAccountIds, key)
      } catch (e: any) {
        error.value = e?.message ?? 'Failed to scan courses'
      } finally {
        removeFromSet(scanningAccountIds, key)
        pendingScans.delete(key)
      }
    })()

    pendingScans.set(key, request)
    return request
  }

  function setActiveAccount(accountId: string): void {
    activeAccountId.value = accountId
  }

  /** 平台切换时由 platformStore.switchPlatform 调用。 */
  function resetActiveAccount(): void {
    activeAccountId.value = null
  }

  function toggleCourseSelection(courseId: string): void {
    const next = new Set(selectedCourseIds.value)
    if (next.has(courseId)) next.delete(courseId)
    else next.add(courseId)
    selectedCourseIds.value = next
  }

  function selectAllCourses(): void {
    selectedCourseIds.value = new Set(allCourses.value.map((course) => course.id))
  }

  function deselectAllCourses(): void {
    selectedCourseIds.value = new Set()
  }

  function selectCourses(ids: string[]): void {
    selectedCourseIds.value = new Set(ids)
  }

  function addSelectedCourses(ids: string[]): void {
    const next = new Set(selectedCourseIds.value)
    for (const id of ids) {
      next.add(id)
    }
    selectedCourseIds.value = next
  }

  function removeSelectedCourses(ids: string[]): void {
    const next = new Set(selectedCourseIds.value)
    for (const id of ids) {
      next.delete(id)
    }
    selectedCourseIds.value = next
  }

  function hasLoadedAccount(accountId: string): boolean {
    return loadedAccountIds.value.has(bucketKey(accountId))
  }

  /** 账号是否已经扫描过：本会话内成功读取过发现文件，或已存在课程数据。 */
  function isAccountScanned(accountId: string): boolean {
    const key = bucketKey(accountId)
    return (
      scannedAccountIds.value.has(key) ||
      (coursesByAccount.value[key]?.length ?? 0) > 0
    )
  }

  return {
    coursesByAccount,
    activeAccountId,
    selectedCourseIds,
    loadingAccountIds,
    scanningAccountIds,
    loading,
    scanning,
    error,
    allCourses,
    activeCourses,
    coursesForAccount,
    selectedCourses,
    hasSelection,
    fetchCourses,
    scanCourses,
    setActiveAccount,
    resetActiveAccount,
    toggleCourseSelection,
    selectAllCourses,
    deselectAllCourses,
    selectCourses,
    addSelectedCourses,
    removeSelectedCourses,
    hasLoadedAccount,
    isAccountScanned,
  }
})
