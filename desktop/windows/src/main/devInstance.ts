// Per-worktree dev-instance derivation, so several `pnpm dev` sessions run side
// by side without colliding on the Vite port, the Electron single-instance lock,
// or the shared Chromium profile.
//
// Why this is needed: in dev the renderer is served by Vite at
// http://localhost:<port>, and Firebase web auth + onboarding/prefs persist in
// localStorage scoped to that ORIGIN (port included) — see firebase.ts
// (`browserLocalPersistence`) and rendererServer.ts. A single pinned port
// therefore lets only one dev app run. Each LINKED git worktree instead derives
// its OWN renderer port + CDP port + window-title suffix from its folder name,
// and auto-isolates its userData (via OMI_SANDBOX, applied in dev/bench.ts). The
// PRIMARY checkout keeps the canonical values (5179 / default profile) so nothing
// changes for the main flow.
//
// This module is pure/deterministic and DEV-only in effect: packaged builds serve
// the renderer from rendererServer.ts (portDerivation.ts) and never call it at a
// point that changes behavior. `scripts/lib/dev-ports.mjs` mirrors the port math
// for the plain-Node helper scripts; devInstance.parity.test.ts guards the mirror.
import { existsSync, statSync } from 'node:fs'
import { basename, dirname, join, relative, isAbsolute } from 'node:path'
import { fnv1a, avalanche } from './portDerivation'

/** Canonical primary-checkout ports — unchanged from the historical defaults. */
export const PRIMARY_RENDERER_PORT = 5179
export const PRIMARY_CDP_PORT = 9222

// Worktree renderer ports sit just above the canonical 5179 so they still read as
// "the Vite dev server". 5180–5279 avoids 5432 (postgres) and stays out of the OS
// ephemeral range where transient collisions with outbound sockets are likely.
export const DEV_RENDERER_BASE = 5180
export const DEV_RENDERER_SPAN = 100
// CDP (OMI_DEV_REMOTE_DEBUG) ports live in a separate band so a renderer port and
// a CDP port can never coincide for the same instance.
export const DEV_CDP_BASE = 9230
export const DEV_CDP_SPAN = 100

export interface DevInstance {
  /** 'primary' for the main checkout, else the sanitized worktree folder name. */
  name: string
  isPrimary: boolean
  /** Vite dev-server port (strictPort). */
  rendererPort: number
  /** Chrome DevTools Protocol port (OMI_DEV_REMOTE_DEBUG) — powers auth seeding + inspection. */
  cdpPort: number
  /** Appended to the native window title so overlapping dev windows are tellable apart ('' for primary). */
  titleSuffix: string
}

/** Slug that is safe as a port-hash key, a userData dir suffix, and an OMI_SANDBOX value. */
export function sanitizeInstanceName(raw: string): string {
  const slug = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'wt'
}

function hashToRange(key: string, base: number, span: number): number {
  return base + (avalanche(fnv1a(key)) % span)
}

export function deriveRendererPort(name: string): number {
  return hashToRange(name, DEV_RENDERER_BASE, DEV_RENDERER_SPAN)
}

export function deriveCdpPort(name: string): number {
  // Salt so the CDP hash decorrelates from the renderer hash for the same name
  // (otherwise both would share the same low-bit offset within their bands).
  return hashToRange('cdp:' + name, DEV_CDP_BASE, DEV_CDP_SPAN)
}

function intEnv(value: string | undefined, fallback: number): number {
  const n = value ? Number.parseInt(value, 10) : NaN
  return Number.isInteger(n) && n > 0 && n < 65536 ? n : fallback
}

/**
 * Pure instance computation. `isPrimary` selects the branch; env vars override
 * individual fields so any checkout can be pinned back to canonical values:
 *   OMI_INSTANCE=primary  → force the primary instance (default profile, 5179)
 *   OMI_INSTANCE=<name>   → force a named instance (ports derived from <name>)
 *   OMI_DEV_PORT=<n>      → force the renderer port
 *   OMI_DEV_CDP_PORT=<n>  → force the CDP port
 */
export function computeDevInstance(
  rawName: string,
  isPrimary: boolean,
  env: NodeJS.ProcessEnv = process.env
): DevInstance {
  const forced = env.OMI_INSTANCE?.trim()
  if (forced) {
    if (forced.toLowerCase() === 'primary') {
      isPrimary = true
    } else {
      isPrimary = false
      rawName = forced
    }
  }

  if (isPrimary) {
    return {
      name: 'primary',
      isPrimary: true,
      rendererPort: intEnv(env.OMI_DEV_PORT, PRIMARY_RENDERER_PORT),
      cdpPort: intEnv(env.OMI_DEV_CDP_PORT, PRIMARY_CDP_PORT),
      titleSuffix: ''
    }
  }

  const name = sanitizeInstanceName(rawName)
  return {
    name,
    isPrimary: false,
    rendererPort: intEnv(env.OMI_DEV_PORT, deriveRendererPort(name)),
    cdpPort: intEnv(env.OMI_DEV_CDP_PORT, deriveCdpPort(name)),
    titleSuffix: ` — ${name}`
  }
}

/**
 * Walk up from `startDir` to the git worktree root and classify it. A LINKED
 * worktree has a `.git` FILE (a `gitdir:` pointer); the PRIMARY checkout has a
 * `.git` DIRECTORY. Returns the worktree folder name + whether it is primary.
 * Falls back to primary when no `.git` is found (e.g. an installed/packaged app),
 * which keeps the canonical behavior as the safe default.
 */
export function findWorktreeContext(startDir: string): { name: string; isPrimary: boolean } {
  let dir = startDir
  for (let i = 0; i < 40; i++) {
    const gitPath = join(dir, '.git')
    if (existsSync(gitPath)) {
      let isDir = false
      try {
        isDir = statSync(gitPath).isDirectory()
      } catch {
        /* race with a worktree repair — treat as linked (safer: isolates) */
      }
      if (!isDir) return { name: basename(dir), isPrimary: false }
      // A `.git` DIRECTORY is the primary checkout root. But a linked worktree
      // whose own `.git` POINTER FILE was deleted (a known Windows worktree bug —
      // see ~/CLAUDE.md worktree-integrity notes) walks up into its parent primary
      // and would otherwise misdetect as primary — binding 5179 + the DEFAULT
      // profile and clobbering the real signed-in session. Recover the linked
      // identity when startDir sits under `<primary>/.worktrees/<name>`.
      const recovered = linkedNameUnderWorktrees(dir, startDir)
      return recovered
        ? { name: recovered, isPrimary: false }
        : { name: basename(dir), isPrimary: true }
    }
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return { name: 'primary', isPrimary: true }
}

/** If `startDir` lives under `<primaryRoot>/.worktrees/<name>/…`, return `<name>`; else null. */
function linkedNameUnderWorktrees(primaryRoot: string, startDir: string): string | null {
  const rel = relative(join(primaryRoot, '.worktrees'), startDir)
  if (!rel || rel.startsWith('..') || isAbsolute(rel)) return null
  const first = rel.split(/[\\/]+/)[0]
  return first || null
}

/** Resolve the active dev instance from the process cwd + env. Memoized per process. */
let cached: DevInstance | null = null
export function resolveDevInstance(
  cwd: string = process.cwd(),
  env: NodeJS.ProcessEnv = process.env
): DevInstance {
  if (cached && cwd === process.cwd() && env === process.env) return cached
  const { name, isPrimary } = findWorktreeContext(cwd)
  const instance = computeDevInstance(name, isPrimary, env)
  if (cwd === process.cwd() && env === process.env) cached = instance
  return instance
}
