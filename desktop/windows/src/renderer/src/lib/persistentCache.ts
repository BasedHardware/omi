// Per-uid localStorage persistence for the in-memory page caches, so data
// surfaces render last-known values instantly on cold start (before the network
// revalidates) instead of flashing an empty/loading state. This closes the
// cold-start gap the in-memory module caches leave open: those survive in-session
// navigation but are empty after an app restart, so the first mount of the session
// would otherwise show a spinner until the network returns.
//
// Keys are scoped by the signed-in uid so a second account on the same machine can
// never read the prior user's cache; the sign-out teardown purges every key via
// clearAllPersistedCaches (see authTeardown.ts).
//
// Leaf module: no React, no apiClient, no firebase imports — safe to import from
// hooks and from authTeardown without creating an import cycle.

const PREFIX = 'omi.cache.'

// The uid the app last hydrated for, written by reconcileAccountForSignIn on every
// sign-in (see authTeardown.ts). Read lazily (at hook-mount time, never at module
// load) so it is already set by the time a surface reads its cache.
const LAST_UID_KEY = 'omi.lastSignedInUid'

function currentUid(): string | null {
  try {
    return localStorage.getItem(LAST_UID_KEY)
  } catch {
    return null
  }
}

function keyFor(surface: string, uid: string): string {
  return `${PREFIX}${surface}.${uid}`
}

// The uid the persistent caches are currently scoped to (the last signed-in uid,
// null when signed out). Async fetch paths capture this at fetch START and re-check
// it before committing their result, so a fetch that resolves AFTER an account
// switch is dropped instead of writing the prior account's data — in memory or to
// disk — under the new uid. The teardown purge alone can't catch this: the switch
// runs teardown first, then the stale fetch resolves and writes after it.
export function getCacheUid(): string | null {
  return currentUid()
}

// Last-known persisted rows for a surface, scoped to the current uid. Returns null
// on a miss, when signed out, on a parse error, or when the payload is not an array
// (tolerant of shape drift across app versions). Callers treat null as "no cache".
export function readPersistedCache<T>(surface: string): T[] | null {
  const uid = currentUid()
  if (!uid) return null
  try {
    const raw = localStorage.getItem(keyFor(surface, uid))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as T[]) : null
  } catch {
    return null
  }
}

// Persist last-known rows for a surface under the current uid (best-effort — a
// quota or privacy-mode failure just means the next cold start falls back to the
// network, which is the pre-existing behavior). Callers should pass a bounded
// slice (e.g. what the page renders) rather than an unbounded list to stay well
// under the localStorage quota.
export function writePersistedCache<T>(surface: string, rows: T[]): void {
  const uid = currentUid()
  if (!uid) return
  try {
    localStorage.setItem(keyFor(surface, uid), JSON.stringify(rows))
  } catch {
    /* quota / privacy mode — cache-first is best-effort */
  }
}

// Object variant of read/writePersistedCache, for surfaces whose cold-start
// snapshot is a record of several fields rather than a single list (e.g. the Apps
// page persists { sections, allApps, installedPool, enabled }). Same per-uid
// scoping, best-effort semantics, and teardown purge (clearAllPersistedCaches
// covers every omi.cache.* key regardless of shape). readPersistedValue returns
// null unless the payload is a non-null, non-array object.
export function readPersistedValue<T>(surface: string): T | null {
  const uid = currentUid()
  if (!uid) return null
  try {
    const raw = localStorage.getItem(keyFor(surface, uid))
    if (!raw) return null
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as T) : null
  } catch {
    return null
  }
}

export function writePersistedValue<T>(surface: string, value: T): void {
  const uid = currentUid()
  if (!uid) return
  try {
    localStorage.setItem(keyFor(surface, uid), JSON.stringify(value))
  } catch {
    /* quota / privacy mode — cache-first is best-effort */
  }
}

// Purge every persisted page cache (all surfaces, all uids). Called from the
// sign-out teardown so a second account on the same machine never reads the prior
// user's cached data. Only touches keys under the PREFIX namespace; device- and
// window-scoped localStorage is left intact.
export function clearAllPersistedCaches(): void {
  try {
    const toRemove: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(PREFIX)) toRemove.push(k)
    }
    for (const k of toRemove) localStorage.removeItem(k)
  } catch {
    /* privacy mode */
  }
}
