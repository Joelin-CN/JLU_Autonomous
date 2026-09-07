import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { Course } from '@/shared/lib/types'
import { createApiClient } from '@/shared/lib/apiClient'

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

export const useCourseStore = defineStore('course', () => {
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

  const loading = computed(() => loadingAccountIds.value.size > 0)
  const scanning = computed(() => scanningAccountIds.value.size > 0)

  const allCourses = computed(() => Object.values(coursesByAccount.value).flatMap((courses) => courses))

  const activeCourses = computed(() => {
    if (!activeAccountId.value) return []
    return coursesByAccount.value[activeAccountId.value] ?? []
  })

  const selectedCourses = computed(() =>
    allCourses.value.filter((course) => selectedCourseIds.value.has(course.id)),
  )

  const hasSelection = computed(() => selectedCourseIds.value.size > 0)

  function getTargetAccountId(accountId?: string): string {
    return accountId ?? activeAccountId.value ?? 'default'
  }

  function setCoursesForAccount(accountId: string, courses: Course[]): void {
    coursesByAccount.value = {
      ...coursesByAccount.value,
      [accountId]: courses,
    }
    addToSet(loadedAccountIds, accountId)
    // Non-empty course data is positive evidence the account has been scanned.
    if (courses.length > 0) {
      addToSet(scannedAccountIds, accountId)
    }
  }

  async function fetchCourses(accountId?: string): Promise<void> {
    const targetId = getTargetAccountId(accountId)
    if (pendingFetches.has(targetId)) {
      return pendingFetches.get(targetId)!
    }
    if (loadedAccountIds.value.has(targetId) && coursesByAccount.value[targetId]) {
      return
    }

    error.value = null
    addToSet(loadingAccountIds, targetId)

    const request = (async () => {
      try {
        const courses = await api.getCourses(targetId)
        setCoursesForAccount(targetId, courses)
      } catch (e: any) {
        error.value = e?.message ?? 'Failed to fetch courses'
      } finally {
        removeFromSet(loadingAccountIds, targetId)
        pendingFetches.delete(targetId)
      }
    })()

    pendingFetches.set(targetId, request)
    return request
  }

  async function scanCourses(accountId?: string): Promise<void> {
    const targetId = getTargetAccountId(accountId)
    if (pendingScans.has(targetId)) {
      return pendingScans.get(targetId)!
    }

    error.value = null
    addToSet(scanningAccountIds, targetId)

    const request = (async () => {
      try {
        const courses = await api.scanCourses(targetId ? [targetId] : undefined)
        setCoursesForAccount(targetId, courses)
        // scanCourses re-reads the persisted discovery state — a successful
        // read (even when empty) means the account has been scanned already.
        addToSet(scannedAccountIds, targetId)
      } catch (e: any) {
        error.value = e?.message ?? 'Failed to scan courses'
      } finally {
        removeFromSet(scanningAccountIds, targetId)
        pendingScans.delete(targetId)
      }
    })()

    pendingScans.set(targetId, request)
    return request
  }

  function setActiveAccount(accountId: string): void {
    activeAccountId.value = accountId
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
    return loadedAccountIds.value.has(accountId)
  }

  /** 账号是否已经扫描过：本会话内成功读取过发现文件，或已存在课程数据。 */
  function isAccountScanned(accountId: string): boolean {
    return (
      scannedAccountIds.value.has(accountId) ||
      (coursesByAccount.value[accountId]?.length ?? 0) > 0
    )
  }

  return {
    coursesByAccount,
    activeAccountId,
    selectedCourseIds,
    loadedAccountIds,
    scannedAccountIds,
    loadingAccountIds,
    scanningAccountIds,
    loading,
    scanning,
    error,
    allCourses,
    activeCourses,
    selectedCourses,
    hasSelection,
    fetchCourses,
    scanCourses,
    setActiveAccount,
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
