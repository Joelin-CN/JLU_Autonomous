import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Account } from '@/shared/lib/types'
import { createApiClient, stripInvokeErrorPrefix } from '@/shared/lib/apiClient'

const api = createApiClient()

export const useAccountStore = defineStore('account', () => {
  const accounts = ref<Account[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const selectedAccountIds = ref<Set<string>>(new Set())
  const error = ref<string | null>(null)
  let pendingFetch: Promise<void> | null = null

  /* computed */

  const onlineAccounts = computed(() =>
    accounts.value.filter((a) => a.status === 'online'),
  )

  const accountCount = computed(() => accounts.value.length)

  const selectedAccounts = computed(() =>
    accounts.value.filter((a) => selectedAccountIds.value.has(a.id)),
  )

  const hasSelection = computed(() => selectedAccountIds.value.size > 0)

  /* actions */

  async function fetchAccounts(): Promise<void> {
    if (loading.value && pendingFetch) return pendingFetch
    if (loaded.value) return

    loading.value = true
    error.value = null
    pendingFetch = (async () => {
      try {
        accounts.value = await api.getAccounts()
        loaded.value = true
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
        pendingFetch = null
      }
    })()
    return pendingFetch
  }

  async function refreshAccounts(): Promise<void> {
    // Bypass the loaded-cache so add/edit/remove/file-switch reflect
    // immediately instead of requiring a page reload.
    loaded.value = false
    pendingFetch = null
    await fetchAccounts()
  }

  async function addAccount(payload: { account: string; password: string; website?: string }): Promise<void> {
    await api.addAccount(payload)
    await refreshAccounts()
  }

  async function editAccount(payload: { index: number; password?: string; website?: string }): Promise<void> {
    await api.editAccount(payload)
    await refreshAccounts()
  }

  async function removeAccount(index: number): Promise<void> {
    await api.removeAccount(index)
    await refreshAccounts()
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
    accounts,
    loading,
    loaded,
    error,
    selectedAccountIds,
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
