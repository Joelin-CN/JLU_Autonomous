import { ipcMain } from 'electron'
import { spawn } from 'child_process'
import { CODE_DIR, WORKSPACE_DIR, DATA_DIR } from '../backendPath'
import { resolvePythonPath } from '../python/resolve'
import type { Course, ScanCoursesPayload } from '../types'
import { IPC_CHANNELS } from '../types'

/**
 * Course listing (`python -m chaoxing.courses --account N`) — reads the
 * discovery state a prior `scan_only` job persisted (output/discovered_courses_*.json).
 *
 * Standalone CLI, decoupled from the job event stream. Prints a SINGLE line of
 * JSON to stdout and exits:
 *   - success → `{ "type":"COURSES", "scanned":true,  "courses":[...] }` (exit 0)
 *   - empty   → `{ "type":"COURSES", "scanned":false, "courses":[] }`    (exit 0, no scan yet)
 *   - failure → `{ "type":"ERROR", "error":"...", "detail":"..." }`      (exit 1)
 *
 * NOTE: this reads already-discovered courses; it does NOT scan the platform
 * (that needs a logged-in browser session and runs through chaoxing.api's job
 * pipeline). When no discovery file exists, the backend returns an empty list
 * with scanned=false — not an error — so the UI can prompt "请先扫描".
 */

/** Interpreter for the listing (plain stdlib read of a JSON file — no SDK). */
function getCoursesPython(): string {
  return resolvePythonPath().pythonPath
}

/** Hard timeout so a hung read can't leave the renderer waiting forever. */
const COURSES_TIMEOUT_MS = 15_000

interface CoursesOkPayload {
  type: 'COURSES'
  scanned: boolean
  courses: Course[]
}

interface CoursesErrorPayload {
  type: 'ERROR'
  error: string
  detail?: string
}

/**
 * Spawn the courses CLI for a single 0-based account index and resolve the
 * discovered courses. Mirrors accounts.handler's spawn/parse contract.
 */
function runCoursesQuery(accountIndex: number): Promise<Course[]> {
  return new Promise((resolve, reject) => {
    const pythonPath = getCoursesPython()

    // Same env-whitelist policy as PythonBridge / accounts: never leak creds.
    const ALLOWED_ENV = [
      'PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'TEMP', 'TMP',
      'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
      'PYTHONPATH', 'PYTHONHOME',
      'CHAOXING_WORKSPACE', 'CHAOXING_DATA_DIR',
    ]
    const safeEnv: Record<string, string> = { PYTHONUNBUFFERED: '1' }
    for (const key of ALLOWED_ENV) {
      if (process.env[key] !== undefined) {
        safeEnv[key] = process.env[key]!
      }
    }
    // Pin workspace so output/discovered_courses_*.json resolves to the right
    // tree regardless of launch cwd (see docs/design/integration.md §4).
    safeEnv.CHAOXING_WORKSPACE = process.env.CHAOXING_WORKSPACE ?? WORKSPACE_DIR
    safeEnv.CHAOXING_DATA_DIR = process.env.CHAOXING_DATA_DIR ?? DATA_DIR

    let child
    try {
      child = spawn(pythonPath, ['-m', 'chaoxing.courses', '--account', String(accountIndex)], {
        cwd: CODE_DIR,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: safeEnv,
      })
    } catch (err: any) {
      reject(new Error(`Failed to launch course listing: ${err?.message ?? err}`))
      return
    }

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill('SIGKILL')
      reject(new Error('读取课程列表超时（15 秒未返回）。'))
    }, COURSES_TIMEOUT_MS)

    child.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf-8') })
    child.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf-8') })

    child.on('error', (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      child.kill('SIGKILL')
      const hint =
        (err as NodeJS.ErrnoException).code === 'ENOENT'
          ? `找不到 Python 解释器：${pythonPath}。请检查设置中的 Python 路径。`
          : err.message
      reject(new Error(hint))
    })

    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)

      // The backend's log() prints to stdout in subcommand mode, so the JSON
      // contract line is the LAST non-empty line (all logging precedes it).
      const line = stdout.split('\n').map((l) => l.trim()).filter(Boolean).pop()

      if (!line) {
        const detail = stderr.trim() ? ` (${stderr.trim()})` : ''
        reject(new Error(`读取课程列表无输出（exit ${code}）${detail}`))
        return
      }

      let parsed: CoursesOkPayload | CoursesErrorPayload
      try {
        parsed = JSON.parse(line)
      } catch {
        reject(new Error(`课程列表返回非 JSON：${line}`))
        return
      }

      if (parsed.type === 'COURSES') {
        // scanned=false (no discovery file yet) is a valid empty result, not
        // an error — the renderer shows a "请先扫描" hint for an empty list.
        resolve(parsed.courses ?? [])
        return
      }

      const errPayload = parsed as CoursesErrorPayload
      const detail = errPayload.detail ? `（${errPayload.detail}）` : ''
      reject(new Error(`${errPayload.error ?? '读取课程列表失败'}${detail}`))
    })
  })
}

/** Read discovered courses for several accounts and flatten the results. */
async function runCoursesForAccounts(accountIndices: number[]): Promise<Course[]> {
  const perAccount = await Promise.all(accountIndices.map((idx) => runCoursesQuery(idx)))
  return perAccount.flat()
}

// ================================================================
// Handler registration
// ================================================================

export function registerCourseHandlers(): void {
  // ---- courses:scan ----
  // Reads the discovery state for the requested accounts. The actual platform
  // scan runs through the job pipeline (job:start mode=scan_only); this surfaces
  // whatever that job already persisted.
  ipcMain.handle(IPC_CHANNELS.COURSES_SCAN, async (_event, payload: ScanCoursesPayload) => {
    if (!payload.accountIds || payload.accountIds.length === 0) {
      throw new Error('At least one accountId is required')
    }
    return runCoursesForAccounts(payload.accountIds)
  })

  // ---- courses:list ----
  ipcMain.handle(IPC_CHANNELS.COURSES_LIST, async (_event, accountId: number) => {
    // accountId is the 0-based index (id=index contract); 0 is valid.
    if (accountId == null || Number.isNaN(accountId)) {
      throw new Error('accountId is required')
    }
    return runCoursesQuery(accountId)
  })
}
