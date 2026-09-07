import { ipcMain } from 'electron'
import os from 'os'
import path from 'path'
import type { SystemResources } from '../types'
import { IPC_CHANNELS } from '../types'
import { DATA_DIR } from '../backendPath'
import { getCurrentSettings } from './status.handler'
import { validatePythonForSettings } from '../python/resolve'
import {
  computeMemoryPlan,
  measureProjectChromeGB,
  measureSystemUsedGB,
} from '../memory/planner'

/**
 * Live system-resource provider (`system:resources`). Reads Node's `os` module
 * in the main process — no Python, no external command. The renderer polls this
 * on an interval to drive the dashboard's resource panel.
 *
 * CPU load has no instantaneous reading: `os.cpus()` exposes cumulative tick
 * counters, so utilization is the delta between two snapshots. We keep the last
 * snapshot and diff against it each call, which yields the average load over the
 * gap since the previous poll (≈ the renderer's poll interval).
 */

interface CpuSnapshot {
  idle: number
  total: number
}

function readCpuSnapshot(): CpuSnapshot {
  let idle = 0
  let total = 0
  for (const cpu of os.cpus()) {
    const t = cpu.times
    idle += t.idle
    total += t.user + t.nice + t.sys + t.idle + t.irq
  }
  return { idle, total }
}

// Seeded at module load so the first poll already has a baseline to diff
// against (otherwise the first reading would be a meaningless 0%).
let lastSnapshot: CpuSnapshot = readCpuSnapshot()

function computeCpuPct(): number {
  const current = readCpuSnapshot()
  const idleDelta = current.idle - lastSnapshot.idle
  const totalDelta = current.total - lastSnapshot.total
  lastSnapshot = current
  // No elapsed ticks (polled too fast / counters unchanged) → report 0 rather
  // than divide by zero.
  if (totalDelta <= 0) return 0
  const usage = 1 - idleDelta / totalDelta
  return Math.round(Math.min(1, Math.max(0, usage)) * 100)
}

/** Bytes → GB, rounded to one decimal. */
function toGB(bytes: number): number {
  return Math.round((bytes / 1024 / 1024 / 1024) * 10) / 10
}

function readResources(): SystemResources {
  const total = os.totalmem()
  const free = os.freemem()
  const used = total - free
  const totalGB = toGB(total)
  const freeGB = toGB(free)
  return {
    ram: {
      total: totalGB,
      free: freeGB,
      used: Math.round((toGB(used)) * 10) / 10,
      pct: total > 0 ? Math.round((used / total) * 100) : 0,
    },
    cpu: {
      pct: computeCpuPct(),
      cores: os.cpus().length,
    },
    uptimeSeconds: Math.round(os.uptime()),
  }
}

export function registerSystemHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.SYSTEM_RESOURCES, async () => {
    return readResources()
  })

  // Validate a candidate pythonPath (existence + Python >= 3.10) without
  // touching settings — used by the settings page for inline feedback while
  // the user is still typing.
  ipcMain.handle(IPC_CHANNELS.SYSTEM_VALIDATE_PYTHON, async (_event, pythonPath: string) => {
    return { reason: await validatePythonForSettings(String(pythonPath ?? '')) }
  })

  ipcMain.handle(IPC_CHANNELS.MEMORY_PLAN, async () => {
    const totalGB = os.totalmem() / 1024 ** 3
    let baselineGB = 0
    try {
      const leftover = await measureProjectChromeGB(path.join(DATA_DIR, 'chrome-profiles'))
      baselineGB = Math.max(0, (await measureSystemUsedGB()) - leftover)
    } catch {
      baselineGB = (os.totalmem() - os.freemem()) / 1024 ** 3
    }
    return computeMemoryPlan(totalGB, baselineGB, os.cpus().length,
      getCurrentSettings().perAccountEstimateGB)
  })
}
