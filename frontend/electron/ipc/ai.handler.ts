import { ipcMain } from 'electron'
import fs from 'fs'
import path from 'path'
import { spawn } from 'child_process'
import { CODE_DIR, DATA_DIR, WORKSPACE_DIR } from '../backendPath'
import { resolvePythonPath } from '../python/resolve'
import { isJobActive } from './jobState'
import { IPC_CHANNELS } from '../types'

const DOUBAO_FILE = () => path.join(DATA_DIR, 'passwords', 'doubao.txt')

/** Provider specs — mirrors backend chaoxing/ai/doubao.py _PROVIDERS. */
const PROVIDER_SPECS: Record<string, { file: () => string; keyVar: string; label: string }> = {
  'doubao-api': { file: DOUBAO_FILE, keyVar: 'ARK_API_KEY', label: '火山方舟（豆包）' },
  'deepseek-api': {
    file: () => path.join(DATA_DIR, 'passwords', 'deepseek.txt'),
    keyVar: 'DEEPSEEK_API_KEY',
    label: 'DeepSeek',
  },
}

function parseDoubao(): { apiKey: string; model: string } {
  return parseProviderFile('doubao-api')
}

function parseProviderFile(provider: string): { apiKey: string; model: string } {
  const spec = PROVIDER_SPECS[provider] ?? PROVIDER_SPECS['doubao-api']
  const file = spec.file()
  if (!fs.existsSync(file)) return { apiKey: '', model: '' }
  const content = fs.readFileSync(file, 'utf-8')
  const key = content.match(new RegExp(`${spec.keyVar}\\s*=\\s*"?([^"\\s]+)"?`))
  const model = content.match(/model\s*=\s*"?([^"\s]+)"?/)
  return { apiKey: key?.[1] ?? '', model: model?.[1] ?? '' }
}

/** The backend chaoxing_config.json decides which provider actually runs. */
function readBackendProvider(): string {
  for (const candidate of [
    path.join(WORKSPACE_DIR, 'chaoxing_config.json'),
    path.join(CODE_DIR, 'chaoxing_config.json'),
  ]) {
    try {
      if (fs.existsSync(candidate)) {
        const raw = JSON.parse(fs.readFileSync(candidate, 'utf-8'))
        const p = raw?.ai?.provider
        if (typeof p === 'string' && PROVIDER_SPECS[p]) return p
      }
    } catch { /* unreadable config — fall through */ }
  }
  return 'doubao-api'
}

function writeBackendProvider(provider: string): void {
  const target = path.join(WORKSPACE_DIR, 'chaoxing_config.json')
  let raw: Record<string, unknown> = {}
  try {
    if (fs.existsSync(target)) raw = JSON.parse(fs.readFileSync(target, 'utf-8'))
  } catch { /* corrupt — rewrite fresh */ }
  raw.ai = { ...(raw.ai as object ?? {}), provider }
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, JSON.stringify(raw, null, 2), 'utf-8')
}

function atomicWrite(file: string, text: string): void {
  if (fs.existsSync(file)) fs.writeFileSync(`${file}.bak`, fs.readFileSync(file))
  const tmp = `${file}.tmp`
  fs.writeFileSync(tmp, text, 'utf-8')
  fs.renameSync(tmp, file)
}

function validateAndSave(apiKey: string, model: string,
                          provider: string = 'doubao-api'): void {
  if (!model || !model.trim()) throw new Error('模型 ID 不能为空。')
  const spec = PROVIDER_SPECS[provider] ?? PROVIDER_SPECS['doubao-api']
  const existing = parseProviderFile(provider)
  const key = apiKey && apiKey.trim() ? apiKey.trim() : existing.apiKey
  if (!key) throw new Error('请填写 API Key。')
  if (provider === 'doubao-api' && !key.startsWith('ark-')) {
    throw new Error('火山方舟 API Key 格式不正确：应以 ark- 开头。')
  }
  if (provider === 'deepseek-api' && !key.startsWith('sk-')) {
    throw new Error('DeepSeek API Key 格式不正确：应以 sk- 开头。')
  }
  const file = spec.file()
  fs.mkdirSync(path.dirname(file), { recursive: true })
  atomicWrite(file, `${spec.keyVar}="${key}"\nmodel="${model.trim()}"\n`)
  const verify = parseProviderFile(provider)
  if (verify.apiKey !== key || verify.model !== model.trim()) {
    throw new Error('写入后校验失败。')
  }
}

function runAiTest(provider: string = 'doubao-api'): Promise<{ ok: boolean; reason?: string; models?: number }> {
  return new Promise((resolve) => {
    const python = resolvePythonPath().pythonPath
    const env: Record<string, string> = { PYTHONUNBUFFERED: '1' }
    for (const k of ['PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'TEMP', 'TMP',
                     'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH']) {
      if (process.env[k] !== undefined) env[k] = process.env[k]!
    }
    env.CHAOXING_WORKSPACE = process.env.CHAOXING_WORKSPACE ?? WORKSPACE_DIR
    env.CHAOXING_DATA_DIR = process.env.CHAOXING_DATA_DIR ?? DATA_DIR
    const child = spawn(python, ['-m', 'chaoxing.ai_config', 'test',
      '--provider', provider], {
      cwd: CODE_DIR, stdio: ['ignore', 'pipe', 'pipe'], env,
    })
    let out = ''
    let settled = false
    const timer = setTimeout(() => {
      if (!settled) {
        settled = true
        child.kill('SIGKILL')
        resolve({ ok: false, reason: '连通性测试超时。' })
      }
    }, 30000)
    child.stdout?.on('data', (c: Buffer) => { out += c.toString('utf-8') })
    child.on('error', (e) => {
      if (!settled) {
        settled = true
        clearTimeout(timer)
        resolve({ ok: false, reason: `无法启动 Python：${e.message}` })
      }
    })
    child.on('close', () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      try {
        const line = out.split('\n').map(l => l.trim()).filter(Boolean).pop()
        const parsed = line ? JSON.parse(line) : null
        resolve(parsed?.type === 'AI_TEST' ? parsed
          : { ok: false, reason: 'AI 测试返回异常。' })
      } catch {
        resolve({ ok: false, reason: 'AI 测试返回无法解析。' })
      }
    })
  })
}

export function registerAiHandlers(): void {
  ipcMain.handle(IPC_CHANNELS.AI_STATUS, () => {
    const provider = readBackendProvider()
    const c = parseProviderFile(provider)
    return { provider,
             label: PROVIDER_SPECS[provider].label,
             configured: Boolean(c.apiKey && c.model), model: c.model,
             keyTail: c.apiKey ? `…${c.apiKey.slice(-4)}` : '' }
  })
  ipcMain.handle(IPC_CHANNELS.AI_SET, (_e, payload: { provider?: string; apiKey?: string; model?: string }) => {
    if (isJobActive()) throw new Error('任务运行中不可修改 AI 配置。')
    const provider = payload?.provider && PROVIDER_SPECS[payload.provider]
      ? payload.provider : readBackendProvider()
    // Empty model = provider-only switch: just repoint chaoxing_config.json,
    // leaving each provider's credentials file untouched.
    if (payload?.model && payload.model.trim()) {
      validateAndSave(payload?.apiKey ?? '', payload.model, provider)
    }
    if (provider !== readBackendProvider()) writeBackendProvider(provider)
  })
  ipcMain.handle(IPC_CHANNELS.AI_TEST, (_e, provider?: string) =>
    runAiTest(provider && PROVIDER_SPECS[provider] ? provider : readBackendProvider()))
}
