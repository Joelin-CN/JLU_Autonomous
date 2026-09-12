import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { Account, Platform } from '@/shared/lib/types'
import { createApiClient, stripInvokeErrorPrefix } from '@/shared/lib/apiClient'
import { usePlatformStore } from '@/app/stores/platform.store'
import { useSettingsStore } from '@/app/stores/settings.store'

const api = createApiClient()

/**
 * 账号 store —— 按平台分桶缓存（双平台数据可并存，为并行任务做准备）。
 * `accounts` 等 computed 始终指向当前平台（platformStore.currentPlatform）的桶；
 * 仪表盘等跨平台视图通过 accountsFor(platform) 读取其它桶。
 */
export const useAccountStore = defineStore('account', () => {
  const platformStore = usePlatformStore()

  const accountsByPlatform = ref<Record<Platform, Account[]>>({
    chaoxing: [],
    zhihuishu: [],
  })
  const loadedPlatforms = ref<Set<Platform>>(new Set())
  const loading = ref(false)
  const selectedAccountIds = ref<Set<string>>(new Set())
  const error = ref<string | null>(null)
  const pendingFetches = new Map<Platform, Promise<void>>()

  /* computed */

  /** 当前平台的账号列表（绝大多数视图只消费这个）。 */
  const accounts = computed(() => accountsByPlatform.value[platformStore.currentPlatform])

  /** 跨平台读取（仪表盘按平台分组统计、侧栏双平台状态行）。 */
  function accountsFor(platform: Platform): Account[] {
    return accountsByPlatform.value[platform]
  }

  function isLoaded(platform: Platform): boolean {
    return loadedPlatforms.value.has(platform)
  }

  const onlineAccounts = computed(() =>
    accounts.value.filter((a) => a.status === 'online'),
  )

  const accountCount = computed(() => accounts.value.length)

  const selectedAccounts = computed(() =>
    accounts.value.filter((a) => selectedAccountIds.value.has(a.id)),
  )

  const hasSelection = computed(() => selectedAccountIds.value.size > 0)

  // Account ids are per-platform file line numbers ("0", "1", …), so the two
  // platforms collide in one id space. Selection only ever operates on the
  // current platform's bucket — clear it on switch to avoid cross-platform ids
  // leaking into a startJob payload.
  watch(() => platformStore.currentPlatform, () => {
    selectedAccountIds.value = new Set()
  })

  /* actions */

  async function fetchAccounts(
    platform?: Platform,
    opts?: { force?: boolean },
  ): Promise<void> {
    const target = platform ?? platformStore.currentPlatform
    if (!opts?.force && loadedPlatforms.value.has(target)) return
    const inFlight = pendingFetches.get(target)
    if (inFlight) return inFlight

    loading.value = true
    error.value = null
    const request = (async () => {
      try {
        const list = await api.getAccounts(target)
        accountsByPlatform.value = {
          ...accountsByPlatform.value,
          [target]: list.map((a) => ({ ...a, platform: a.platform ?? target })),
        }
        loadedPlatforms.value = new Set([...loadedPlatforms.value, target])
      } catch (e: any) {
        // Surface the reason (e.g. a stale pythonPath) in the log console —
        // otherwise the atlas just shows an empty, confusing account list.
        error.value = stripInvokeErrorPrefix(e?.message ?? '') || '账号列表加载失败'
        void import('@/app/stores/log.store')
          .then(({ useLogStore }) => {
            useLogStore().addLog('error', `账号列表加载失败：${error.value}`, '账号')
          })
          .catch(() => { /* log store unavailable in early boot */ })
      } finally {
        loading.value = false
        pendingFetches.delete(target)
      }
    })()
    pendingFetches.set(target, request)
    return request
  }

  async function refreshAccounts(platform?: Platform): Promise<void> {
    // Bypass the per-platform cache so add/edit/remove/file-switch reflect
    // immediately instead of requiring a page reload.
    const target = platform ?? platformStore.currentPlatform
    loadedPlatforms.value = new Set(
      [...loadedPlatforms.value].filter((p) => p !== target),
    )
    await fetchAccounts(target, { force: true })
  }

  /** 当前平台在设置中的自定义凭据文件路径（空 = 默认路径）。 */
  function accountsFileFor(platform: Platform): string | undefined {
    const configured = useSettingsStore().settings.accountsFilePaths[platform]
    return configured || undefined
  }

  async function addAccount(payload: {
    account: string
    password: string
    website?: string
    platform?: Platform
  }): Promise<void> {
    const platform = payload.platform ?? platformStore.currentPlatform
    await api.addAccount({ ...payload, platform, accountsFile: accountsFileFor(platform) })
    await refreshAccounts(platform)
  }

  async function editAccount(payload: {
    index: number
    password?: string
    website?: string
    platform?: Platform
  }): Promise<void> {
    const platform = payload.platform ?? platformStore.currentPlatform
    await api.editAccount({ ...payload, platform, accountsFile: accountsFileFor(platform) })
    await refreshAccounts(platform)
  }

  async function removeAccount(index: number, platform?: Platform): Promise<void> {
    const target = platform ?? platformStore.currentPlatform
    await api.removeAccount(index, target, accountsFileFor(target))
    await refreshAccounts(target)
  }

  function toggleAccountSelection(accountId: string): void {
    const set = new Set(selectedAccountIds.value)
    if (set.has(accountId)) {
      set.delete(accountId)
    } else {
      set.add(accountId)
    }
    selectedAccountIds.value = set
  }

  function selectAccount(accountId: string): void {
    selectedAccountIds.value = new Set([...selectedAccountIds.value, accountId])
  }

  function deselectAccount(accountId: string): void {
    const set = new Set(selectedAccountIds.value)
    set.delete(accountId)
    selectedAccountIds.value = set
  }

  function selectAll(): void {
    selectedAccountIds.value = new Set(accounts.value.map((a) => a.id))
  }

  function deselectAll(): void {
    selectedAccountIds.value = new Set()
  }

  return {
    accountsByPlatform,
    loading,
    error,
    selectedAccountIds,
    accounts,
    accountsFor,
    isLoaded,
    onlineAccounts,
    accountCount,
    selectedAccounts,
    hasSelection,
    fetchAccounts,
    refreshAccounts,
    addAccount,
    editAccount,
    removeAccount,
    toggleAccountSelection,
    selectAccount,
    deselectAccount,
    selectAll,
    deselectAll,
  }
})
