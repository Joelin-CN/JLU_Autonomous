import fs from 'fs'
import { spawn } from 'child_process'
import { getCurrentSettings } from '../ipc/status.handler'

/**
 * Shared Python interpreter resolution — the single place that decides which
 * python.exe every spawn path uses (job pipeline, courses, accounts, balance,
 * AI test). Resolution order:
 *
 *   1. An explicit per-purpose env override (e.g. CHAOXING_BALANCE_PYTHON).
 *   2. Settings.pythonPath (empty = plain "python" from PATH).
 *   3. 'python'.
 *
 * `failSoft` controls what happens when the configured value is an absolute
 * path that no longer exists: auxiliary CLIs (balance) fall back to 'python'
 * with a warning, while the job pipeline keeps the configured value so the
 * spawn fails fast with the friendly message — silently switching interpreters
 * mid-pipeline would produce confusing missing-dependency errors instead.
 */

/** Rough check for an explicit path (as opposed to a bare command name). */
export function isPathLike(value: string): boolean {
  return (
    value.includes('/') ||
    value.includes('\\') ||
    /^[A-Za-z]:/.test(value) ||
    value.toLowerCase().endsWith('.exe')
  )
}

/** Standard Chinese "interpreter not found" message for ENOENT surfacing. */
export function pythonNotFoundMessage(pythonPath: string, extra = ''): string {
  const suffix = extra ? ` ${extra}` : ''
  return `找不到 Python 解释器：${pythonPath}。请检查「系统设置 → Python 路径」，或将其留空以使用系统 PATH 中的 python。${suffix}`
}

export interface PythonResolution {
  pythonPath: string
  /** Set when a configured path was skipped in failSoft mode. */
  warning?: string
}

export function resolvePythonPath(
  opts: { envOverride?: string; failSoft?: boolean } = {},
): PythonResolution {
  const configured = getCurrentSettings().pythonPath.trim()
  const source = opts.envOverride?.trim() || configured

  if (source) {
    if (opts.failSoft && isPathLike(source) && !fs.existsSync(source)) {
      const warning =
        `配置的解释器 "${source}" 不存在，已回退到 PATH 中的 python。` +
        '请更新「系统设置 → Python 路径」。'
      console.warn(`[python] ${warning}`)
      return { pythonPath: 'python', warning }
    }
    return { pythonPath: source }
  }
  return { pythonPath: 'python' }
}

/**
 * Validate a user-entered pythonPath for saving: the path must exist (when it
 * is path-like) and the interpreter must be Python >= 3.10 (matching the
 * backend's syntax requirements, e.g. `dict | None`).
 *
 * Returns null when valid, otherwise a Chinese reason.
 */
export function validatePythonForSettings(pythonPath: string): Promise<string | null> {
  const value = pythonPath.trim()
  if (!value) return Promise.resolve(null) // empty = PATH python, always allowed

  if (isPathLike(value) && !fs.existsSync(value)) {
    return Promise.resolve(`路径不存在（${value}）。请填写有效的 python.exe 完整路径，或留空使用系统 PATH。`)
  }

  return new Promise((resolve) => {
    // Print major/minor as two ints: minor can be >= 10 (3.10, 3.13), so a
    // single combined number would be ambiguous to decode.
    const child = spawn(value, ['-c', 'import sys; print(sys.version_info[0], sys.version_info[1])'])
    let out = ''
    let settled = false
    const done = (reason: string | null) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(reason)
    }
    const timer = setTimeout(() => {
      child.kill('SIGKILL')
      done('解释器探测超时（5 秒无响应）。')
    }, 5000)
    child.stdout?.on('data', (c: Buffer) => { out += c.toString() })
    child.on('error', (err: NodeJS.ErrnoException) => {
      done(err.code === 'ENOENT'
        ? `无法启动该解释器（${value}）。请确认路径正确或命令在 PATH 中。`
        : `探测失败：${err.message}`)
    })
    child.on('close', (code) => {
      if (code !== 0) {
        done(`解释器启动异常（exit ${code}）。Windows 商店版 python 桩也可能导致此问题，请使用真实 Python 3.10+。`)
        return
      }
      const parts = out.trim().split(/\s+/)
      const major = Number.parseInt(parts[0] ?? '', 10)
      const minor = Number.parseInt(parts[1] ?? '0', 10)
      if (Number.isNaN(major)) {
        done('无法解析 Python 版本输出。')
        return
      }
      if (major < 3 || (major === 3 && minor < 10)) {
        done(`Python 版本过低（检测到 ${major}.${minor}）。后端要求 Python 3.10 或更高。`)
        return
      }
      done(null)
    })
  })
}
