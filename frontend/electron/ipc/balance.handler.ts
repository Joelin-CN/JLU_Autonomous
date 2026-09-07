import { ipcMain } from 'electron'
import { spawn } from 'child_process'
import { CODE_DIR, WORKSPACE_DIR, DATA_DIR } from '../backendPath'
import { resolvePythonPath } from '../python/resolve'
import type { BalanceResult } from '../types'
import { IPC_CHANNELS } from '../types'

/**
 * Balance query (`python -m chaoxing.balance`) — see API manual §4.7.
 *
 * This is a standalone CLI, fully decoupled from the job event stream. It takes
 * none of the --job-id/--accounts/--mode args, prints a SINGLE line of JSON to
 * stdout, and exits:
 *   - success → `{ "type": "BALANCE", ... }`  (exit code 0)
 *   - failure → `{ "type": "ERROR", "error": "...", "detail": "..." }` (exit 1)
 *
 * IMPORTANT: it depends on `volcengine-python-sdk`. If the configured
 * interpreter lacks the SDK, set CHAOXING_BALANCE_PYTHON to one that has it
 * (e.g. an Anaconda python). Resolution is delegated to the shared resolver
 * (env override → Settings.pythonPath → 'python'), failSoft so a stale
 * absolute path falls back to a launchable interpreter instead of ENOENT.
 */

/** Hard timeout so a hung SDK call can't leave the renderer waiting forever. */
const BALANCE_TIMEOUT_MS = 30_000

interface BalanceErrorPayload {
  type: 'ERROR'
  error: string
  detail?: string
}

function runBalanceQuery(provider: 'doubao' | 'deepseek' = 'doubao'): Promise<BalanceResult> {
  return new Promise((resolve, reject) => {
    // The DeepSeek query only needs httpx (shipped with openai) — any
    // interpreter works, no failSoft special-casing required.
    const { pythonPath, warning } = resolvePythonPath({
      envOverride: provider === 'deepseek'
        ? process.env.CHAOXING_DEEPSEEK_BALANCE_PYTHON ?? process.env.CHAOXING_BALANCE_PYTHON
        : process.env.CHAOXING_BALANCE_PYTHON,
      failSoft: true,
    })
    if (warning) console.warn(`[balance] ${warning}`)

    // Same env-whitelist policy as PythonBridge: never leak ARK_API_KEY etc.
    // Credentials come from passwords/volc_billing.txt, not the environment.
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
    // Pin workspace to the writable runtime root (see docs/design/integration.md §4),
    // so volc_billing.txt and config resolve there regardless of launch cwd.
    safeEnv.CHAOXING_WORKSPACE = process.env.CHAOXING_WORKSPACE ?? WORKSPACE_DIR
    safeEnv.CHAOXING_DATA_DIR = process.env.CHAOXING_DATA_DIR ?? DATA_DIR

    let child
    try {
      const args = provider === 'deepseek'
        ? ['-m', 'chaoxing.balance', '--provider', 'deepseek-api']
        : ['-m', 'chaoxing.balance']
      child = spawn(pythonPath, args, {
        cwd: CODE_DIR,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: safeEnv,
      })
    } catch (err: any) {
      reject(new Error(`Failed to launch balance query: ${err?.message ?? err}`))
      return
    }

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill('SIGKILL')
      reject(new Error('余额查询超时（30 秒未返回）。'))
    }, BALANCE_TIMEOUT_MS)

    child.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString('utf-8') })
    child.stderr?.on('data', (chunk: Buffer) => { stderr += chunk.toString('utf-8') })

    child.on('error', (err) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      // ENOENT → the configured interpreter was not found on PATH / at the path.
      const hint =
        (err as NodeJS.ErrnoException).code === 'ENOENT'
          ? `找不到 Python 解释器：${pythonPath}。请检查设置中的 Python 路径，或设置 CHAOXING_BALANCE_PYTHON 环境变量指向装有 volcengine-python-sdk 的解释器。`
          : err.message
      reject(new Error(hint))
    })

    child.on('close', (code) => {
      if (settled) return
      settled = true
      clearTimeout(timer)

      // Parse the last non-empty stdout line as JSON (stdout is strictly single
      // line per the manual; we take the last to be robust against stray output).
      const line = stdout.split('\n').map((l) => l.trim()).filter(Boolean).pop()

      if (!line) {
        const detail = stderr.trim() ? ` (${stderr.trim()})` : ''
        reject(new Error(`余额查询无输出（exit ${code}）${detail}`))
        return
      }

      let parsed: BalanceResult | BalanceErrorPayload
      try {
        parsed = JSON.parse(line)
      } catch {
        reject(new Error(`余额查询返回非 JSON：${line}`))
        return
      }

      if (parsed.type === 'BALANCE') {
        resolve(parsed)
        return
      }

      // type === 'ERROR' (or exit ≠ 0): surface the backend's error + detail.
      const errPayload = parsed as BalanceErrorPayload
      const detail = errPayload.detail ? `（${errPayload.detail}）` : ''
      reject(new Error(`${errPayload.error ?? '余额查询失败'}${detail}`))
    })
  })
}

export function registerBalanceHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.BALANCE_QUERY, async (_e, provider?: string) => {
    return runBalanceQuery(provider === 'deepseek' ? 'deepseek' : 'doubao')
  })
}
