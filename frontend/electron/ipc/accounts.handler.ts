import { ipcMain } from 'electron'
import path from 'path'
import { spawn } from 'child_process'
import { CODE_DIR, WORKSPACE_DIR, DATA_DIR } from '../backendPath'
import { resolvePythonPath } from '../python/resolve'
import { getCurrentSettings } from './status.handler'
import { isJobActive } from './jobState'
import type { Account } from '../types'
import { IPC_CHANNELS } from '../types'

/**
 * Account management (`python -m chaoxing.accounts`) — list/add/edit/remove.
 * Standalone CLI, decoupled from the job event stream. Prints a SINGLE line of
 * JSON to stdout and exits:
 *   - list   → `{ "type":"ACCOUNTS", "accounts":[{index,account}, ...] }`
 *   - mutate → `{ "type":"ACCOUNTS_OK", ... }` (exit 0)
 *   - fail   → `{ "type":"ERROR", "error":"...", "detail":"..." }`  (exit 1)
 *
 * SECURITY: passwords are never emitted — only each account's index and login
 * id. Mutations only accept the password over IPC; it is never logged.
 */

/** Interpreter for the listing/mutations (no SDK needed — stdlib parse). */
function getAccountsPython(): string {
  return resolvePythonPath().pythonPath
}

const ACCOUNTS_TIMEOUT_MS = 15_000

interface BackendAccount {
  index: number
  account: string
  website?: string
}

interface AccountsErrorPayload {
  type: 'ERROR'
  error: string
  detail?: string
}

interface AccountsOkPayload {
  type: 'ACCOUNTS'
  accounts: BackendAccount[]
}

interface AccountsMutatedPayload {
  type: 'ACCOUNTS_OK'
  action: 'add' | 'edit' | 'remove'
  index: number
  account: string | null
}

type AccountsPayload = AccountsOkPayload | AccountsMutatedPayload | AccountsErrorPayload

function toAccount(b: BackendAccount): Account {
  const now = new Date().toISOString()
  return {
    id: b.index,
    username: b.account,
    website: b.website ?? '',
    enabled: true,
    createdAt: now,
    updatedAt: now,
  }
}

function runAccountsCommand(extraArgs: string[]): Promise<AccountsPayload> {
  return new Promise((resolve, reject) => {
    const pythonPath = getAccountsPython()

    // Same env-whitelist policy as PythonBridge: never leak credentials.
    const ALLOWED_ENV = [
      'PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'TEMP', 'TMP',
      'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
      'PYTHONPATH', 'PYTHONHOME',
      'CHAOXING_WORKSPACE', 'CHAOXING_DATA_DIR', 'CHAOXING_ACCOUNTS_FILE',
    ]
    const safeEnv: Record<string, string> = { PYTHONUNBUFFERED: '1' }
    for (const key of ALLOWED_ENV) {
      if (process.env[key] !== undefined) {
        safeEnv[key] = process.env[key]!
      }
    }
    safeEnv.CHAOXING_WORKSPACE = process.env.CHAOXING_WORKSPACE ?? WORKSPACE_DIR
    safeEnv.CHAOXING_DATA_DIR = process.env.CHAOXING_DATA_DIR ?? DATA_DIR
    const accountsFile = getCurrentSettings().accountsFilePath
    if (accountsFile) safeEnv.CHAOXING_ACCOUNTS_FILE = accountsFile

    let child
    try {
      child = spawn(pythonPath, ['-m', 'chaoxing.accounts', ...extraArgs], {
        cwd: CODE_DIR,
        stdio: ['ignore', 'pipe', 'pipe'],
        env: safeEnv,
      })
    } catch (err: any) {
      reject(new Error(`Failed to launch account command: ${err?.message ?? err}`))
      return
    }

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      settled = true
      child.kill('SIGKILL')
      reject(new Error('账号操作超时（15 秒未返回）。'))
    }, ACCOUNTS_TIMEOUT_MS)

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

      const line = stdout.split('\n').map((l) => l.trim()).filter(Boolean).pop()
      if (!line) {
        const detail = stderr.trim() ? ` (${stderr.trim()})` : ''
        reject(new Error(`账号操作无输出（exit ${code}）${detail}`))
        return
      }

      let parsed: AccountsPayload
      try {
        parsed = JSON.parse(line)
      } catch {
        reject(new Error(`账号操作返回非 JSON：${line}`))
        return
      }

      if (parsed.type === 'ERROR') {
        const errPayload = parsed as AccountsErrorPayload
        const detail = errPayload.detail ? `（${errPayload.detail}）` : ''
        reject(new Error(`${errPayload.error ?? '账号操作失败'}${detail}`))
        return
      }
      resolve(parsed)
    })
  })
}

function requireIdle(): void {
  if (isJobActive()) throw new Error('任务运行中不可修改账号。')
}

export function registerAccountsHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_DEFAULT_PATH, () => {
    return path.join(DATA_DIR, 'passwords', 'chaoxing.txt')
  })

  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_LIST, async () => {
    const parsed = await runAccountsCommand([])
    if (parsed.type !== 'ACCOUNTS') throw new Error('账号列表返回异常。')
    return parsed.accounts.map(toAccount)
  })

  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_ADD, async (_e, p) => {
    requireIdle()
    await runAccountsCommand(['add', '--account', String(p.account),
      '--password', String(p.password),
      ...(p.website ? ['--website', p.website] : [])])
  })

  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_EDIT, async (_e, p) => {
    requireIdle()
    await runAccountsCommand(['edit', '--index', String(p.index),
      ...(p.password ? ['--password', String(p.password)] : []),
      ...(p.website ? ['--website', p.website] : [])])
  })

  ipcMain.handle(IPC_CHANNELS.ACCOUNTS_REMOVE, async (_e, p) => {
    requireIdle()
    await runAccountsCommand(['remove', '--index', String(p.index)])
  })
}
