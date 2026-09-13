import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import type { Settings } from '@/shared/lib/types'
import { DEFAULT_SETTINGS } from '@/shared/lib/constants'
import { applyTheme } from '@/shared/lib/designTokens'
import { createApiClient } from '@/shared/lib/apiClient'

const STORAGE_KEY = 'jlu-study-assistant-settings'
/** 旧品牌时代的存储 key（v0「超星助手」）。首次读取时一次性迁移后删除。 */
const LEGACY_STORAGE_KEY = 'chaoxing-assistant-settings'
const api = createApiClient()

/** 把旧版本持久化结构升级到当前 Settings 形状：
 *  - accountsFilePath 单值 → accountsFilePaths.chaoxing（多平台分文件）
 *  导出供单测（settings.migrate.test.ts）。 */
export function migrateLegacySettings(raw: Record<string, unknown>): Settings {
  const merged = { ...DEFAULT_SETTINGS, ...raw } as Settings & { accountsFilePath?: string }
  if (typeof merged.accountsFilePath === 'string' && !merged.accountsFilePaths?.chaoxing) {
    merged.accountsFilePaths = {
      ...(merged.accountsFilePaths ?? { chaoxing: '', zhihuishu: '' }),
      chaoxing: merged.accountsFilePath,
    }
  }
  delete merged.accountsFilePath
  return merged
}

function loadFromStorage(): Settings {
  try {
    let raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      return migrateLegacySettings(JSON.parse(raw))
    }
    // One-time migration from the legacy brand key, then remove it.
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (legacy) {
      const migrated = migrateLegacySettings(JSON.parse(legacy))
      localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated))
      localStorage.removeItem(LEGACY_STORAGE_KEY)
      return migrated
    }
  } catch {
    // corrupted storage — fall through
  }
  return { ...DEFAULT_SETTINGS }
}

function saveToStorage(settings: Settings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

let syncTimer: ReturnType<typeof setTimeout> | null = null

function debouncedSync(settings: Settings): void {
  if (syncTimer) clearTimeout(syncTimer)
  syncTimer = setTimeout(() => {
    api.setSettings(settings).catch((e: any) => {
      // Rejections here are usually validation failures (e.g. an invalid
      // Python path) — surface them in the log console instead of dying
      // silently while localStorage keeps the unsaved value.
      console.error('[settings] sync to main failed:', e)
      void import('@/app/stores/log.store')
        .then(({ useLogStore }) => {
          useLogStore().addLog('error', `设置保存失败：${e?.message ?? '未知错误'}`, '设置')
        })
        .catch(() => {
          // log store unavailable (early boot) — console.error above suffices
        })
    })
  }, 1000)
}

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<Settings>(loadFromStorage())

  // Apply theme on load
  applyTheme(settings.value.theme)

  // Persist on change
  watch(
    settings,
    (val) => {
      saveToStorage(val)
      applyTheme(val.theme)
      debouncedSync(val)
    },
    { deep: false },
  )

  function updateSetting<K extends keyof Settings>(key: K, value: Settings[K]): void {
    // Replace the whole object to trigger shallow watcher — avoids the
    // performance cost and unnecessary localStorage writes of deep:true.
    settings.value = { ...settings.value, [key]: value }
  }

  function setTheme(theme: 'light' | 'dark'): void {
    settings.value = { ...settings.value, theme }
  }

  function resetSettings(): void {
    settings.value = { ...DEFAULT_SETTINGS }
  }

  return { settings, updateSetting, setTheme, resetSettings }
})
