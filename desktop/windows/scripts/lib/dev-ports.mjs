// Plain-Node mirror of the dev-instance PORT MATH in src/main/devInstance.ts, so
// the helper scripts (seed-auth.mjs, bootstrap) can resolve an instance's ports
// without a TypeScript loader. The app itself never imports this file.
//
// KEEP IN SYNC with src/main/devInstance.ts — the arithmetic below is mirrored,
// and devInstance.parity.test.ts fails if the two ever diverge.
import { existsSync, statSync } from 'node:fs'
import { basename, dirname, join } from 'node:path'

export const PRIMARY_RENDERER_PORT = 5179
export const PRIMARY_CDP_PORT = 9222
export const DEV_RENDERER_BASE = 5180
export const DEV_RENDERER_SPAN = 100
export const DEV_CDP_BASE = 9230
export const DEV_CDP_SPAN = 100

/** FNV-1a 32-bit hash. */
export function fnv1a(input) {
  let hash = 0x811c9dc5
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash >>> 0
}

/** Murmur3-style finalizer. */
export function avalanche(h) {
  h ^= h >>> 16
  h = Math.imul(h, 0x85ebca6b)
  h ^= h >>> 13
  h = Math.imul(h, 0xc2b2ae35)
  h ^= h >>> 16
  return h >>> 0
}

function hashToRange(key, base, span) {
  return base + (avalanche(fnv1a(key)) % span)
}

export function deriveRendererPort(name) {
  return hashToRange(name, DEV_RENDERER_BASE, DEV_RENDERER_SPAN)
}

export function deriveCdpPort(name) {
  return hashToRange('cdp:' + name, DEV_CDP_BASE, DEV_CDP_SPAN)
}

export function sanitizeInstanceName(raw) {
  const slug = raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return slug || 'wt'
}

/** Classify a checkout: a linked worktree has a `.git` FILE, the primary a `.git` DIR. */
export function findWorktreeContext(startDir) {
  let dir = startDir
  for (let i = 0; i < 40; i++) {
    const gitPath = join(dir, '.git')
    if (existsSync(gitPath)) {
      let isDir = false
      try {
        isDir = statSync(gitPath).isDirectory()
      } catch {
        /* treat as linked */
      }
      return { name: basename(dir), isPrimary: isDir }
    }
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return { name: 'primary', isPrimary: true }
}

/** Resolve { name, isPrimary, rendererPort, cdpPort } for a checkout dir + env. */
export function resolveInstance(cwd, env = process.env) {
  let { name, isPrimary } = findWorktreeContext(cwd)
  const forced = env.OMI_INSTANCE && env.OMI_INSTANCE.trim()
  if (forced) {
    if (forced.toLowerCase() === 'primary') isPrimary = true
    else {
      isPrimary = false
      name = forced
    }
  }
  if (isPrimary) {
    return {
      name: 'primary',
      isPrimary: true,
      rendererPort: PRIMARY_RENDERER_PORT,
      cdpPort: PRIMARY_CDP_PORT
    }
  }
  const slug = sanitizeInstanceName(name)
  return {
    name: slug,
    isPrimary: false,
    rendererPort: deriveRendererPort(slug),
    cdpPort: deriveCdpPort(slug)
  }
}
