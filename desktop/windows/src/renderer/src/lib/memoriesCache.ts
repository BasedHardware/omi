// Module-singleton cache for the user's memories, extracted to a leaf module (no
// React, no apiClient imports) so the sign-out teardown can reset it WITHOUT
// creating an import cycle: authTeardown is reachable from firebase.ts, and
// useMemories.ts pulls in React + apiClient (which imports firebase). Mirrors the
// leaf-cache pattern already used by pageCache.ts and localAgentMemoryCache.ts.
// useMemories.ts owns the fetch/mutation logic and imports this state.
//
// `import type` is erased at runtime, so importing the Memory type back from the
// hook creates no runtime cycle (localAgentMemoryCache.ts does the same).
import type { Memory } from '../hooks/useMemories'
import { readPersistedCache, writePersistedCache } from './persistentCache'

export const cache = {
  list: null as Memory[] | null,
  error: null as string | null,
  loaded: false,
  // Whether the server exposes canonical memory tiering for this account
  // (X-Omi-Memory-Canonical-Lifecycle-Exposed). Prod runs MEMORY_MODE=off, so
  // this stays false and the tier/device filters never render. Set from the
  // fetch response immediately BEFORE publish(), so the list re-render that
  // publish triggers reads the fresh value.
  canonicalLifecycleExposed: false
}

// Persist at most this many memories to the per-uid cold-start snapshot. The page
// renders newest-first and caps its own view well under this, so a bounded slice
// is enough to fill the first screen instantly on cold start; the revalidating
// fetch fills in the rest. Bounding it keeps the localStorage write small.
const PERSIST_CAP = 500

// The persisted-cache surface key for memories (scoped per-uid by the helper).
const CACHE_SURFACE = 'memories'

// Every mounted useMemories subscribes here so a refresh/create in one place
// (e.g. the Settings importer) updates the Memories page too — without this the
// module cache only refreshed the component that triggered the write.
export const subscribers = new Set<(list: Memory[]) => void>()

export function publish(list: Memory[]): void {
  cache.list = list
  // Mirror the current list to the per-uid cold-start snapshot so the next app
  // launch renders it instantly (see hydrateFromDisk). Best-effort and bounded.
  writePersistedCache(CACHE_SURFACE, list.slice(0, PERSIST_CAP))
  subscribers.forEach((fn) => fn(list))
}

// Cold-start hydration: on the first hook mount of the session, seed the in-memory
// cache from the per-uid persisted snapshot so the Memories page renders the
// last-known memories immediately instead of a spinner. `loaded` stays false, so
// the revalidating fetch still runs and overwrites with fresh data. Runs at
// hook-mount time (not module load) so the signed-in uid is already set.
let hydratedFromDisk = false
export function hydrateFromDisk(): void {
  if (hydratedFromDisk) return
  hydratedFromDisk = true
  if (cache.list !== null) return
  const persisted = readPersistedCache<Memory>(CACHE_SURFACE)
  if (persisted && persisted.length > 0) cache.list = persisted
}

// Reset the in-memory cache on sign-out / account switch so a second account on
// the same machine never sees the prior user's memories from this module-level
// singleton. The per-uid disk snapshot is purged separately by
// clearAllPersistedCaches in the same teardown. Called from authTeardown.
export function resetMemoriesCache(): void {
  cache.list = null
  cache.error = null
  cache.loaded = false
  cache.canonicalLifecycleExposed = false
  hydratedFromDisk = false
}
