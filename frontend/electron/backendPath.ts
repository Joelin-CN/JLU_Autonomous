import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'
import { app } from 'electron'

// __dirname is not available in ES modules — reconstruct it. After the
// vite-plugin-electron build everything is bundled into dist-electron/main.js,
// so this resolves to <repo>/frontend/dist-electron at runtime.
const here = path.dirname(fileURLToPath(import.meta.url))

/**
 * Backend path model — two distinct roots that coincide in dev but diverge
 * once the app is packaged:
 *
 *   CODE_DIR      The directory that holds the `chaoxing` Python package. Used
 *                 as the spawn `cwd` so `python -m chaoxing.*` can import it.
 *                 In a packaged build this is `resources/backend` and is READ
 *                 ONLY (inside the install dir, possibly Program Files).
 *
 *   WORKSPACE_DIR The directory the backend reads/writes at runtime — config,
 *                 passwords/, output/, temp/, logs/, scripts/ (captcha images),
 *                 chrome-profiles/, chrome-cache/. Passed to the backend as
 *                 CHAOXING_WORKSPACE (see docs/design/integration.md §4). In a packaged
 *                 build this lives under the user's writable userData dir; in
 *                 dev it is the same as CODE_DIR (the backend subtree itself).
 *
 * Keeping these separate is what lets a read-only install still write its
 * runtime state to a per-user location.
 */

/**
 * Locate the directory containing `chaoxing/api.py`.
 *
 * Resolution order:
 *   1. `CHAOXING_BACKEND_DIR` env override (non-standard layouts).
 *   2. When packaged: `process.resourcesPath/backend` (shipped via
 *      electron-builder `extraResources`).
 *   3. Dev: walk up from the compiled main process location looking for a
 *      `backend/chaoxing/api.py` marker — robust to dev vs. build layout.
 *   4. Fallback to the standard layout relative to dist-electron/.
 */
function resolveCodeDir(): string {
  const override = process.env.CHAOXING_BACKEND_DIR
  if (override && fs.existsSync(path.join(override, 'chaoxing', 'api.py'))) {
    return path.resolve(override)
  }

  if (app.isPackaged) {
    return path.join(process.resourcesPath, 'backend')
  }

  let dir = here
  for (let i = 0; i < 6; i++) {
    const candidate = path.join(dir, 'backend')
    if (fs.existsSync(path.join(candidate, 'chaoxing', 'api.py'))) {
      return candidate
    }
    const parent = path.dirname(dir)
    if (parent === dir) break
    dir = parent
  }

  return path.resolve(here, '../../backend')
}

/** Read-only directory holding the `chaoxing` package (spawn cwd). */
export const CODE_DIR = resolveCodeDir()

/**
 * Writable runtime workspace (CHAOXING_WORKSPACE).
 *   - dev:      same as CODE_DIR (write straight into the backend subtree).
 *   - packaged: `<userData>/workspace` (CODE_DIR is read-only).
 * An explicit `CHAOXING_WORKSPACE` env value always wins.
 */
function resolveWorkspaceDir(): string {
  const override = process.env.CHAOXING_WORKSPACE
  if (override) return path.resolve(override)
  if (app.isPackaged) {
    return path.join(app.getPath('userData'), 'workspace')
  }
  return CODE_DIR
}

export const WORKSPACE_DIR = resolveWorkspaceDir()

/**
 * Writable runtime data root (CHAOXING_DATA_DIR). Holds credentials, browser
 * profiles, logs, screenshots, output and temp artifacts.
 *   - dev:      `<repo>/data` (next to the backend subtree)
 *   - packaged: `<userData>/data` (WORKSPACE_DIR is `<userData>/workspace`)
 * An explicit `CHAOXING_DATA_DIR` env value always wins.
 */
function resolveDataDir(): string {
  const override = process.env.CHAOXING_DATA_DIR
  if (override) return path.resolve(override)
  return path.resolve(WORKSPACE_DIR, '../data')
}

export const DATA_DIR = resolveDataDir()

/**
 * Backward-compatible alias. Historically a single `BACKEND_DIR` served as both
 * cwd and workspace; now it maps to CODE_DIR. New code should import CODE_DIR /
 * WORKSPACE_DIR explicitly.
 */
export const BACKEND_DIR = CODE_DIR

// ── First-launch workspace seeding ───────────────────────────────

/** Read-only assets the backend loads from `scripts/` at runtime. The rest of
 *  `scripts/` is legacy `.py` dead code and is NOT shipped (see handoff §4.3). */
const SEED_SCRIPT_ASSETS = ['_table.json', '_decrypt_font.js', '_v17_section_player.js']

/** Directories the backend writes into; created empty so first run never trips
 *  on a missing dir. `scripts/` is writable too (captcha images, see §4.2). */
const SEED_EMPTY_DIRS = ['passwords', 'output', 'temp', 'logs', 'scripts']

/** Runtime data subdirectories under DATA_DIR, seeded on first launch. */
const SEED_DATA_DIRS = [
  'passwords', 'output', 'temp', 'logs', 'screenshots', 'chrome-profiles',
  'documents',
]

function copyIfAbsent(src: string, dest: string): void {
  if (fs.existsSync(dest)) return
  if (!fs.existsSync(src)) return
  fs.mkdirSync(path.dirname(dest), { recursive: true })
  fs.copyFileSync(src, dest)
}

/**
 * Idempotently seed the writable workspace on first launch (packaged builds).
 *
 * Copies `chaoxing_config.json` and the read-only `scripts/` assets out of the
 * read-only CODE_DIR into WORKSPACE_DIR, and creates the empty runtime dirs.
 * Existing files are never overwritten, so user edits (config tweaks, the
 * passwords they create) survive upgrades. No-op in dev (the two dirs coincide).
 *
 * Must be called after `app.whenReady()` — it touches the userData path.
 */
export function ensureWorkspaceSeeded(): void {
  if (WORKSPACE_DIR === CODE_DIR) return // dev: nothing to seed

  fs.mkdirSync(WORKSPACE_DIR, { recursive: true })
  fs.mkdirSync(DATA_DIR, { recursive: true })

  for (const dir of SEED_EMPTY_DIRS) {
    fs.mkdirSync(path.join(WORKSPACE_DIR, dir), { recursive: true })
  }

  for (const dir of SEED_DATA_DIRS) {
    fs.mkdirSync(path.join(DATA_DIR, dir), { recursive: true })
  }

  // The real chaoxing_config.json never ships (it holds the developer's
  // course IDs/progress) — fall back to the packaged example so the workspace
  // still gets a valid, user-editable config on first launch.
  copyIfAbsent(
    path.join(CODE_DIR, 'chaoxing_config.json'),
    path.join(WORKSPACE_DIR, 'chaoxing_config.json'),
  )
  copyIfAbsent(
    path.join(CODE_DIR, 'chaoxing_config.example.json'),
    path.join(WORKSPACE_DIR, 'chaoxing_config.json'),
  )

  copyIfAbsent(
    path.join(CODE_DIR, '.playwright', 'cli.config.json'),
    path.join(WORKSPACE_DIR, '.playwright', 'cli.config.json'),
  )

  for (const asset of SEED_SCRIPT_ASSETS) {
    copyIfAbsent(
      path.join(CODE_DIR, 'scripts', asset),
      path.join(WORKSPACE_DIR, 'scripts', asset),
    )
  }
}
