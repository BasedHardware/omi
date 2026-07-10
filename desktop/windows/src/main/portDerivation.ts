// Deterministic renderer-server port selection (pure logic — unit-tested).
//
// The renderer is served at http://localhost:<port> and Firebase auth
// persistence is origin-scoped INCLUDING the port, so the port must be stable
// per install or the user is silently signed out. Deriving it from the
// userData path gives: stable across launches of the same install, distinct
// across OMI_SANDBOX instances (each pins a different userData), and no
// dependence on first-come-first-served port grabbing.
//
// The range 17321–17820 avoids common well-known service ports (5432, 5179
// dev vite, 8080, etc.) while staying out of the OS ephemeral range where
// transient collisions with outbound sockets are likely.

export const PORT_BASE = 17321
export const PORT_SPAN = 500

/** FNV-1a 32-bit hash — tiny, stable, good dispersion for short strings. */
export function fnv1a(input: string): number {
  let hash = 0x811c9dc5
  for (let i = 0; i < input.length; i++) {
    hash ^= input.charCodeAt(i)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash >>> 0
}

/**
 * Derive the stable renderer port for an install from its userData path.
 * Windows paths are case-insensitive and separator-flexible — normalize so
 * `C:\Users\X` and `c:/users/x` derive the same port.
 */
export function derivePort(userDataPath: string): number {
  const normalized = userDataPath
    .trim()
    .toLowerCase()
    .replace(/[\\/]+/g, '/')
    .replace(/\/$/, '')
  return PORT_BASE + (avalanche(fnv1a(normalized)) % PORT_SPAN)
}

/** Murmur3-style finalizer: FNV-1a's low bits disperse poorly for near-identical
 * strings (sibling sandbox paths), and the modulo only sees the low bits. */
function avalanche(h: number): number {
  h ^= h >>> 16
  h = Math.imul(h, 0x85ebca6b)
  h ^= h >>> 13
  h = Math.imul(h, 0xc2b2ae35)
  h ^= h >>> 16
  return h >>> 0
}

export interface PortAttempt {
  port: number
  /** Milliseconds to wait before this attempt (backoff while a dying previous instance releases the port). */
  delayMs: number
  /** True once we've abandoned the derived port — landing here means the saved session may not carry over. */
  isFallback: boolean
}

/** Backoff schedule on the derived port: a dying previous instance (single-instance
 * lock handoff) typically releases within a second or two. */
export const RETRY_DELAYS_MS = [0, 250, 500, 750, 1000]

/** How many sequential fallback ports to try when a foreign process owns the derived port. */
export const FALLBACK_PORTS = 9

/**
 * Full attempt schedule: retry the derived port with backoff first (previous
 * instance dying), then walk the next ports as a fallback. A fallback success
 * must be surfaced to the user — the session is origin-scoped and won't carry.
 */
export function planPortSequence(derivedPort: number): PortAttempt[] {
  const attempts: PortAttempt[] = RETRY_DELAYS_MS.map((delayMs) => ({
    port: derivedPort,
    delayMs,
    isFallback: false
  }))
  for (let i = 1; i <= FALLBACK_PORTS; i++) {
    attempts.push({ port: derivedPort + i, delayMs: 0, isFallback: true })
  }
  return attempts
}
