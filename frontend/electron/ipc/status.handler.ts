import { ipcMain, app } from 'electron'
import path from 'path'
import fs from 'fs'
import type { AccountStatus, Settings, Ticket } from '../types'
import { IPC_CHANNELS, DEFAULT_SETTINGS } from '../types'
import { isJobActive } from './jobState'
import { validatePythonForSettings } from '../python/resolve'

// ----------------------------------------------------------------
// Settings persistence
// ----------------------------------------------------------------

function getSettingsPath(): string {
  return path.join(app.getPath('userData'), 'settings.json')
}

function loadSettings(): Settings {
  const filePath = getSettingsPath()
  try {
    if (fs.existsSync(filePath)) {
      const raw = fs.readFileSync(filePath, 'utf-8')
      return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }
    }
  } catch (err) {
    console.error('[settings] Failed to load settings:', err)
  }
  return { ...DEFAULT_SETTINGS }
}

function saveSettings(settings: Settings): void {
  const filePath = getSettingsPath()
  try {
    const dir = path.dirname(filePath)
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true })
    }
    fs.writeFileSync(filePath, JSON.stringify(settings, null, 2), 'utf-8')
  } catch (err) {
    console.error('[settings] Failed to save settings:', err)
    throw new Error('Failed to save settings')
  }
}

// ----------------------------------------------------------------
// In-memory stores
// TODO: Replace with filesystem/DB-backed stores
// ----------------------------------------------------------------

const tickets: Ticket[] = []

let currentSettings: Settings = loadSettings()

/**
 * Read-only accessor for the persisted settings, for non-IPC modules that need
 * to honor user config (e.g. PythonBridge reading `pythonPath`/`headless`).
 * Returns a shallow copy so callers can't mutate the live store.
 */
export function getCurrentSettings(): Settings {
  return { ...currentSettings }
}

// TODO: Replace with real data source (filesystem/DB/Python backend).
// These stubs provide placeholder data for development when the Python backend is unavailable.

// Mock account statuses
const mockAccountStatuses: Map<number, AccountStatus> = new Map([
  [
    1,
    {
      accountId: 1,
      loggedIn: true,
      scanning: false,
      running: false,
      courseCount: 12,
      completedCount: 8,
    },
  ],
])

// ================================================================
// Handler registration
// ================================================================

export function registerStatusHandlers(): void {
  // ---- accounts:status ----
  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_STATUS, async (_event, accountId: number) => {
    const status = mockAccountStatuses.get(accountId)
    if (!status) {
      throw new Error(`Account ${accountId} not found`)
    }
    return { ...status }
  })

  // ---- settings:get ----
  ipcMain.handle(IPC_CHANNELS.SETTINGS_GET, async () => {
    return { ...currentSettings }
  })

  // ---- settings:set ----
  ipcMain.handle(IPC_CHANNELS.SETTINGS_SET, async (_event, partial: Partial<Settings>) => {
    const lockedKeys = ['accountsFilePath', 'concurrencyTarget', 'perAccountEstimateGB']
    if (isJobActive() && lockedKeys.some((k) => k in partial)) {
      throw new Error('任务运行中不可修改该设置。')
    }
    // Catch a broken interpreter at save time — otherwise every later spawn
    // fails with ENOENT for a reason the user can't see in the settings page.
    if (typeof partial.pythonPath === 'string' && partial.pythonPath.trim()) {
      const reason = await validatePythonForSettings(partial.pythonPath)
      if (reason) throw new Error(`Python 路径无效：${reason}`)
    }
    currentSettings = { ...currentSettings, ...partial }
    saveSettings(currentSettings)
  })

  // ---- tickets:list ----
  ipcMain.handle(IPC_CHANNELS.TICKETS_LIST, async () => {
    return tickets.map(t => ({ ...t }))
  })

  // ---- tickets:resolve ----
  ipcMain.handle(IPC_CHANNELS.TICKETS_RESOLVE, async (_event, ticketId: string, resolution: string) => {
    // Real tickets reach the renderer over the ON_TICKET event stream, not via
    // this in-memory array, so a ticket the user resolves in the UI usually
    // isn't here. Treat a miss as a no-op rather than an error — the renderer
    // store is the source of truth and has already marked it resolved. If the
    // ticket does happen to be tracked here, keep it in sync.
    const ticket = tickets.find(t => t.id === ticketId)
    if (!ticket) return
    ticket.resolved = true
    ticket.resolution = resolution
    ticket.resolvedAt = Date.now()
  })
}
