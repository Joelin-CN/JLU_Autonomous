/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

export {}

// Re-use the full ElectronAPI type from the preload so the renderer
// gets autocomplete and type-checking on window.electronAPI.
import type { ElectronAPI } from '../electron/preload'

declare global {
  interface Window {
    electronAPI?: ElectronAPI
  }
}
