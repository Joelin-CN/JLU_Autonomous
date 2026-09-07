import { EventEmitter } from 'events'
import { spawn, ChildProcess } from 'child_process'
import { CODE_DIR, WORKSPACE_DIR, DATA_DIR } from '../backendPath'
import { getCurrentSettings } from '../ipc/status.handler'
import { resolvePythonPath, pythonNotFoundMessage } from './resolve'
import type {
  PythonBridgeEvent,
  PythonProgressEvent,
  PythonPhaseEvent,
  PythonLogEvent,
  PythonTicketEvent,
  PythonErrorEvent,
  PythonDoneEvent,
  PythonResultEvent,
  PythonMemoryEvent,
} from '../types'

// ----------------------------------------------------------------
// Memory safety constants
// ----------------------------------------------------------------

/** Estimated RAM (MB) consumed by a single headless Chromium session.
 *  Empirical measurement: ~300-400MB per Playwright Chromium instance.
 *  Using 350MB as a conservative estimate to avoid underestimating. */
const CHROMIUM_RAM_PER_ACCOUNT_MB = 350

/** Maximum fraction of free system RAM we're willing to consume with
 *  Chromium sessions. Using 0.7 leaves 30% headroom for OS + GPU driver. */
const MAX_RAM_USAGE_RATIO = 0.7

/** Upper bound for buffered stdout (bytes). A misbehaving backend that floods
 *  output without line breaks would otherwise grow `buffer` without limit. */
const MAX_STDOUT_BUFFER_BYTES = 1_000_000

// ----------------------------------------------------------------
// Type guards
// ----------------------------------------------------------------

function isBridgeEvent(obj: unknown): obj is PythonBridgeEvent {
  if (typeof obj !== 'object' || obj === null) return false
  const o = obj as Record<string, unknown>
  const known = ['PROGRESS', 'LOG', 'PHASE', 'TICKET', 'RESULT', 'ERROR', 'DONE', 'MEMORY']
  return typeof o.type === 'string' && known.includes(o.type)
}

// ----------------------------------------------------------------
// PythonBridge
// ----------------------------------------------------------------

export interface PythonBridgeEvents {
  progress: [PythonProgressEvent]
  phase: [PythonPhaseEvent]
  log: [PythonLogEvent]
  ticket: [PythonTicketEvent]
  error: [PythonErrorEvent]
  result: [PythonResultEvent]
  memory: [PythonMemoryEvent]
  done: [PythonDoneEvent]
  exit: [code: number | null]
}

export declare interface PythonBridge {
  on<E extends keyof PythonBridgeEvents>(event: E, listener: (...args: PythonBridgeEvents[E]) => void): this
  emit<E extends keyof PythonBridgeEvents>(event: E, ...args: PythonBridgeEvents[E]): boolean
}

export class PythonBridge extends EventEmitter {
  private process: ChildProcess | null = null
  private buffer = ''
  private stopping = false
  private jobId = 'main'
  private killTimer1: NodeJS.Timeout | null = null
  private killTimer2: NodeJS.Timeout | null = null
  private safetyTimer: NodeJS.Timeout | null = null
  private bufferTruncated = false

  // ================================================================
  // Real process
  // ================================================================

  start(args: string[], jobId?: string): void {
    this.buffer = ''
    this.bufferTruncated = false
    if (jobId) this.jobId = jobId
    // Canonical backend entry is the JSON-line protocol module
    // `python -m chaoxing.api` (NOT the legacy scripts/ shim, which does not
    // speak the protocol). It must run with cwd = backend root so the
    // `chaoxing` package is importable.
    //
    // Whitelist: only forward necessary env vars to the Python subprocess.
    // Using ...process.env would leak sensitive variables like ARK_API_KEY,
    // DOUBAO_TOKEN, and other credentials stored in the environment.
    const ALLOWED_ENV = [
      'PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'TEMP', 'TMP',
      'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
      'PYTHONPATH', 'PYTHONHOME',
      'CHAOXING_WORKSPACE', 'CHAOXING_DATA_DIR', 'CHAOXING_HEADED',
      'CHAOXING_ACCOUNTS_FILE',
    ]
    const safeEnv: Record<string, string> = { PYTHONUNBUFFERED: '1' }
    for (const key of ALLOWED_ENV) {
      if (process.env[key] !== undefined) {
        safeEnv[key] = process.env[key]!
      }
    }
    // Pin the workspace to the writable runtime root (= backend subtree in dev,
    // userData/workspace when packaged) so chaoxing_config.json and output/
    // temp/ logs/ resolve there, not next to the read-only code. An explicit env
    // value (e.g. for a relocated workspace) still wins.
    safeEnv.CHAOXING_WORKSPACE = process.env.CHAOXING_WORKSPACE ?? WORKSPACE_DIR
    safeEnv.CHAOXING_DATA_DIR = process.env.CHAOXING_DATA_DIR ?? DATA_DIR

    // Honor the user's headless setting. The backend reads CHAOXING_HEADED ("1"
    // launches a visible browser); headless:true (the default) leaves it "0".
    const settings = getCurrentSettings()
    safeEnv.CHAOXING_HEADED = settings.headless ? '0' : '1'
    if (settings.accountsFilePath) {
      safeEnv.CHAOXING_ACCOUNTS_FILE = settings.accountsFilePath
    }
    safeEnv.CHAOXING_TIMEOUT_PAGE_LOAD = String(settings.pageLoadTimeout)
    safeEnv.CHAOXING_TIMEOUT_SNAPSHOT = String(settings.snapshotTimeout)
    safeEnv.CHAOXING_TIMEOUT_CLICK_ACTION = String(settings.clickTimeout)
    safeEnv.CHAOXING_TIMEOUT_VIDEO_WATCH = String(settings.videoWatchTimeout)
    safeEnv.CHAOXING_TIMEOUT_QUIZ_ANSWER = String(settings.quizAnswerTimeout)
    safeEnv.CHAOXING_TIMEOUT_SECTION_COMPLETE = String(settings.sectionCompleteTimeout)
    safeEnv.CHAOXING_RETRY_QUIZ_MAX = String(settings.quizRetryCount)
    safeEnv.CHAOXING_RETRY_TARGET_SCORE = String(settings.targetAccuracy)

    const fullArgs = ['-m', 'chaoxing.api', ...args]

    // Honor the configured interpreter via the shared resolver (empty = 'python'
    // from PATH). Strict mode: a configured-but-missing path is kept so the
    // spawn fails fast with the friendly message below instead of silently
    // switching interpreters under a running pipeline.
    const pythonPath = resolvePythonPath().pythonPath

    this.process = spawn(pythonPath, fullArgs, {
      cwd: CODE_DIR,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: safeEnv,
    })

    // Hard safety: kill Python after 2 hours max runtime to prevent
    // runaway processes from consuming system resources indefinitely.
    this.safetyTimer = setTimeout(() => {
      if (this.process && !this.process.killed) {
        this.process.kill('SIGTERM')
        setTimeout(() => {
          if (this.process && !this.process.killed) {
            this.process.kill('SIGKILL')
          }
        }, 5000)
      }
    }, 7_200_000) // 2 hours

    this.process.stdout?.on('data', (chunk: Buffer) => {
      this.buffer += chunk.toString('utf-8')
      // Hard cap: if the backend floods stdout without line breaks, drop the
      // head so the buffer cannot grow without bound. One warning per process
      // lifetime keeps the log from being spammed.
      if (this.buffer.length > MAX_STDOUT_BUFFER_BYTES) {
        this.buffer = this.buffer.slice(-MAX_STDOUT_BUFFER_BYTES)
        if (!this.bufferTruncated) {
          this.bufferTruncated = true
          this.emit('log', {
            type: 'LOG',
            jobId: this.jobId,
            level: 'error',
            message: `[pythonBridge] stdout buffer exceeded ${MAX_STDOUT_BUFFER_BYTES} bytes; head dropped`,
            timestamp: new Date().toISOString(),
          })
        }
      }
      this.flushBuffer()
    })

    this.process.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString('utf-8').trim()
      if (msg) {
        this.emit('log', {
          type: 'LOG',
          jobId: this.jobId,
          level: 'error',
          message: `[stderr] ${msg}`,
          timestamp: new Date().toISOString(),
        })
      }
    })

    this.process.on('exit', (code) => {
      this.clearKillTimers()
      if (this.safetyTimer) {
        clearTimeout(this.safetyTimer)
        this.safetyTimer = null
      }
      this.flushBuffer()
      this.emit('exit', code)
      this.process = null
    })

    this.process.on('error', (err: NodeJS.ErrnoException) => {
      // ENOENT means the configured interpreter does not exist — the single
      // most common fresh-machine failure. Translate it so the renderer shows
      // actionable Chinese guidance instead of the raw Node message.
      const isENOENT = err.code === 'ENOENT' || /ENOENT/.test(err.message)
      const message = isENOENT
        ? pythonNotFoundMessage(pythonPath)
        : `Python 进程错误：${err.message}`
      this.emit('error', {
        type: 'ERROR',
        jobId: this.jobId,
        error: message,
        stack: err.stack ?? err.message,
      })
      // A spawn failure (e.g. ENOENT for the configured interpreter) is
      // terminal: no 'exit' event is guaranteed, so clean up timers and the
      // process reference here and let listeners observe the bridge going
      // away. job.handler treats 'exit' as the release point for
      // activeJobId/bridge; the already-emitted ERROR message is preserved
      // because the job status has already been set to 'error'.
      this.clearKillTimers()
      if (this.safetyTimer) {
        clearTimeout(this.safetyTimer)
        this.safetyTimer = null
      }
      this.process = null
      this.emit('exit', null)
    })
  }

  pause(): void {
    this.sendSignal('PAUSE')
  }

  resume(): void {
    this.sendSignal('RESUME')
  }

  /**
   * Send a captcha/ticket resolution back to the Python backend.
   *
   * The backend's StdinController reads newline-delimited JSON. It routes the
   * answer to the per-account file by `accountId`, so the frontend never needs
   * to know the file name. `action: 'skip'` tells the backend to abandon the
   * current course's content phase for this account and move on.
   */
  resolveTicket(payload: {
    ticketId: string
    accountId: number
    answer?: string
    action?: 'skip'
  }): void {
    this.sendJson({ type: 'RESOLVE_TICKET', ...payload })
  }

  private sendJson(obj: unknown): void {
    if (this.process?.stdin?.writable) {
      this.process.stdin.write(`${JSON.stringify(obj)}\n`)
    }
  }

  stop(): void {
    if (!this.process) return

    this.stopping = true

    // Ask nicely first
    this.sendSignal('STOP')

    // Force SIGTERM after 5 seconds
    this.killTimer1 = setTimeout(() => {
      if (this.process && !this.process.killed) {
        this.process.kill('SIGTERM')
      }
    }, 5000)

    // Hard SIGKILL after 8 seconds regardless
    this.killTimer2 = setTimeout(() => {
      if (this.process && !this.process.killed) {
        this.process.kill('SIGKILL')
      }
    }, 8000)
  }

  private clearKillTimers(): void {
    if (this.killTimer1) {
      clearTimeout(this.killTimer1)
      this.killTimer1 = null
    }
    if (this.killTimer2) {
      clearTimeout(this.killTimer2)
      this.killTimer2 = null
    }
  }

  isRunning(): boolean {
    return this.process !== null && !this.process.killed
  }

  // ================================================================
  // Internal helpers
  // ================================================================

  private sendSignal(signal: string): void {
    if (this.process?.stdin?.writable) {
      this.process.stdin.write(`${signal}\n`)
    }
  }

  private flushBuffer(): void {
    const lines = this.buffer.split('\n')
    // Keep the last (possibly incomplete) line
    this.buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed) continue

      try {
        const obj = JSON.parse(trimmed)
        if (isBridgeEvent(obj)) {
          this.dispatch(obj)
        }
      } catch {
        // Non-JSON line — emit as log
        this.emit('log', {
          type: 'LOG',
          jobId: this.jobId,
          level: 'info',
          message: trimmed,
          timestamp: new Date().toISOString(),
        })
      }
    }
  }

  private dispatch(event: PythonBridgeEvent): void {
    switch (event.type) {
      case 'PROGRESS':
        this.emit('progress', event)
        break
      case 'PHASE':
        this.emit('phase', event)
        break
      case 'LOG':
        this.emit('log', event)
        break
      case 'TICKET':
        this.emit('ticket', event)
        break
      case 'ERROR':
        this.emit('error', event)
        break
      case 'RESULT':
        this.emit('result', event)
        break
      case 'MEMORY':
        this.emit('memory', event)
        break
      case 'DONE':
        this.emit('done', event)
        break
    }
  }

}
