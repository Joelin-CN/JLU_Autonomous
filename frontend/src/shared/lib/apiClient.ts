import type { ChaoxingApi } from './types'
import { ElectronApiClient } from './ipcClient'
import { MockApiClient } from './mockClient'

// Re-export so stores can strip ipcRenderer.invoke wrapper text without
// reaching into the concrete client module.
export { stripInvokeErrorPrefix } from './ipcClient'

// Singleton instance — all stores share ONE client.
//
// Previously each of the 5 Pinia stores called createApiClient() at module
// scope, producing 5 independent client instances. In Electron mode that meant
// duplicate IPC listener registrations; in Mock mode it meant 5 copies of the
// mock dataset plus 5 independent simulation timer chains and listener maps.
// Every HMR reload of a store stacked yet another instance. That accumulation
// was the frontend's own memory-management problem. Memoizing here collapses it
// to a single shared client without changing the API surface or transport.
let instance: ChaoxingApi | null = null

export function createApiClient(): ChaoxingApi {
  if (instance) return instance

  if (typeof window !== 'undefined' && (window as any).electronAPI) {
    instance = new ElectronApiClient()
  } else {
    console.info('[Chaoxing] Running in browser mode — using MockApiClient')
    instance = new MockApiClient()
  }
  return instance
}

/**
 * True when the shared client is the in-browser mock (no Electron API).
 * Lets UI surfaces label simulated data (e.g. the dashboard resource panel)
 * so it is not mistaken for a real reading.
 */
export function isMockMode(): boolean {
  return instance instanceof MockApiClient
}

/**
 * Dispose and drop the shared client. Primarily for tests and full
 * teardown; the next createApiClient() call builds a fresh instance.
 */
export function resetApiClient(): void {
  instance?.dispose()
  instance = null
}
