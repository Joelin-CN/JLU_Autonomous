import { app, BrowserWindow, ipcMain } from 'electron'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'
import { execFile } from 'child_process'
import { registerJobHandlers, stopActiveJob } from './ipc/job.handler'
import { registerStatusHandlers } from './ipc/status.handler'
import { registerCourseHandlers } from './ipc/course.handler'
import { registerBalanceHandlers } from './ipc/balance.handler'
import { registerAccountsHandlers } from './ipc/accounts.handler'
import { registerSystemHandlers } from './ipc/system.handler'
import { registerDialogHandlers } from './ipc/dialog.handler'
import { registerAiHandlers } from './ipc/ai.handler'
import { DATA_DIR } from './backendPath'
import { getCurrentSettings } from './ipc/status.handler'
import { ensureWorkspaceSeeded } from './backendPath'

// __dirname is not available in ES modules — reconstruct it
const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

// ----------------------------------------------------------------
// GPU stability: disable hardware acceleration
// Electron's visible window uses GPU compositing. On systems with
// NVIDIA driver instability (observed: RTX 5070 Laptop, driver
// 32.0.15.9621), GPU acceleration is an unnecessary risk factor.
// Headless Playwright Chromium instances do NOT use GPU rendering,
// so this only affects the Electron shell itself.
// ----------------------------------------------------------------
app.commandLine.appendSwitch('disable-gpu')
app.commandLine.appendSwitch('disable-gpu-compositing')

// ----------------------------------------------------------------
// Constants
// ----------------------------------------------------------------

const APP_NAME = 'chaoxing-assistant'

const WINDOW_DEFAULTS = {
  width: 1540,
  height: 960,
  minWidth: 1024,
  minHeight: 680,
  show: false, // show after ready-to-show to avoid white flash
  title: '超星助手 - Chaoxing Assistant',
  icon: path.join(__dirname, '../build/icon.ico'),
  webPreferences: {
    preload: path.join(__dirname, 'preload.js'),
    contextIsolation: true,
    nodeIntegration: false,
    sandbox: true,
  },
} as const

// ----------------------------------------------------------------
// State
// ----------------------------------------------------------------

let mainWindow: BrowserWindow | null = null
let isQuitting = false

// ----------------------------------------------------------------
// Window creation
// ----------------------------------------------------------------

function getMainWindow(): BrowserWindow | null {
  return mainWindow
}

function pruneOldLogs(days: number): void {
  const dir = path.join(DATA_DIR, 'logs')
  if (!fs.existsSync(dir)) return
  const cutoff = Date.now() - days * 86_400_000
  for (const name of fs.readdirSync(dir)) {
    if (!name.endsWith('.log')) continue
    const file = path.join(dir, name)
    try {
      if (fs.statSync(file).mtimeMs < cutoff) fs.unlinkSync(file)
    } catch {
      // A locked log file must never break startup.
    }
  }
}

/**
 * Best-effort cleanup of orphaned Chromium processes that belong to this app.
 * Only targets chrome.exe/chromium.exe whose command line contains the app's
 * data root (the persistent profile path), so unrelated browsers are never
 * force-killed. The playwright-cli session close in stopActiveJob() is the
 * primary cleanup; this is a safety net for crashed sessions.
 */
function cleanupOrphanedChromium(): void {
  if (process.platform !== 'win32') return
  const profileRoot = DATA_DIR.replace(/'/g, "''")
  const script =
    `Get-CimInstance Win32_Process -Filter "Name='chrome.exe' or Name='chromium.exe'" | ` +
    `Where-Object { $_.CommandLine -like '*${profileRoot}*' } | ` +
    `ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }`
  execFile('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script], { timeout: 8000 }, () => {
    // Never block app shutdown on cleanup failures.
  })
}

function createWindow(): BrowserWindow {
  const win = new BrowserWindow(WINDOW_DEFAULTS)

  // Gracefully show when ready
  win.on('ready-to-show', () => {
    if (!isQuitting) {
      win.show()
    }
  })

  win.on('closed', () => {
    mainWindow = null
  })

  // Content Security Policy — defense in depth
  win.webContents.session.webRequest.onHeadersReceived((details, callback) => {
    callback({
      responseHeaders: {
        ...details.responseHeaders,
        'Content-Security-Policy': [
          "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:",
        ],
      },
    })
  })

  // Load content
  if (process.env.VITE_DEV_SERVER_URL) {
    win.loadURL(process.env.VITE_DEV_SERVER_URL)
    win.webContents.openDevTools({ mode: 'detach' })
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'))
  }

  return win
}

// ----------------------------------------------------------------
// Register all IPC handlers
// ----------------------------------------------------------------

function registerAllHandlers(): void {
  registerJobHandlers(getMainWindow)
  registerStatusHandlers()
  registerCourseHandlers()
  registerBalanceHandlers()
  registerAccountsHandlers()
  registerSystemHandlers()
  registerDialogHandlers(getMainWindow)
  registerAiHandlers()
}

// ----------------------------------------------------------------
// App lifecycle
// ----------------------------------------------------------------

app.setName(APP_NAME)

app.whenReady().then(() => {
  // Seed the writable workspace before any handler can spawn the backend
  // (packaged builds: copy config + read-only assets out of read-only
  // resources into userData; no-op in dev). Failure is non-fatal — the
  // backend will surface a clearer error if a required file is truly missing.
  try {
    ensureWorkspaceSeeded()
  } catch (err) {
    console.error('[workspace] Seeding failed:', err)
  }
  try {
    pruneOldLogs(getCurrentSettings().logRetention)
  } catch (err) {
    console.error('[logs] Pruning failed:', err)
  }
  registerAllHandlers()
  mainWindow = createWindow()

  app.on('activate', () => {
    // macOS: re-create window when dock icon is clicked and no windows open
    if (BrowserWindow.getAllWindows().length === 0) {
      mainWindow = createWindow()
    }
  })
})

app.on('window-all-closed', () => {
  // On macOS, keep the app running in the dock unless Cmd+Q
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

app.on('before-quit', () => {
  isQuitting = true
  stopActiveJob()
  // Clean up orphaned Playwright Chromium processes scoped to this app's data
  // root (stopActiveJob already closes the sessions gracefully).
  cleanupOrphanedChromium()
})

app.on('quit', () => {
  // Final cleanup if any remaining processes
  stopActiveJob()
})
