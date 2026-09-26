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
import {
  getCacheUid,
  readPersistedCache,
  readPersistedValue,
  scopedCacheKey,
  writePersistedCache,
  writePersistedValue
} from './persistentCache'

export type MemoryReadView = 'useful_now' | 'history' | 'all'

export const cache = {
  list: null as Memory[] | null,
  error: null as string | null,
  loaded: false,
  // The server view represented by `list`. Keeping this beside the list avoids
  // showing a cached history row when the default useful-now view is selected.
  view: null as MemoryReadView | null,
  // Whether the server exposes canonical memory tiering for this account
  // (X-Omi-Memory-Canonical-Lifecycle-Exposed). Prod runs MEMORY_MODE=off, so
  // this stays false and the tier/device filters never render. Set from the
  // fetch response immediately BEFORE publish(), so the list re-render that
  // publish triggers reads the fresh value.
  canonicalLifecycleExposed: false,
  // null means the current backend has not advertised the beta capability yet.
  // This is intentionally separate from canonical tiering: a legacy backend may
  // expose tiers while lacking temporal reads, and vice versa.
  beliefEnabled: null as boolean | null
}

// Persist at most this many memories to the per-uid cold-start snapshot. The page
// renders newest-first and caps its own view well under this, so a bounded slice
// is enough to fill the first screen instantly on cold start; the revalidating
// fetch fills in the rest. Bounding it keeps the localStorage write small.
const PERSIST_CAP = 500

// The persisted-cache surface key for memories (scoped per-uid by the helper).
const CACHE_SURFACE = 'memories'

// `import.meta.env` is unavailable in a few isolated unit-test contexts. The
// fallback remains a stable local scope and is never treated as a capability.
function backendScope(): string {
  const base = (import.meta as { env?: Record<string, unknown> }).env?.VITE_OMI_API_BASE
  return typeof base === 'string' && base.trim() ? base.trim() : 'default'
}

const BELIEF_CAPABILITY_SURFACE = 'memory-belief-capability'

function capabilitySurface(): string {
  return scopedCacheKey(BELIEF_CAPABILITY_SURFACE, backendScope())
}

export function readBeliefCapability(): boolean | null {
  if (!getCacheUid()) return null
  const snapshot = readPersistedValue<{ enabled?: unknown }>(capabilitySurface())
  return typeof snapshot?.enabled === 'boolean' ? snapshot.enabled : null
}

export function writeBeliefCapability(enabled: boolean): void {
  cache.beliefEnabled = enabled
  if (!getCacheUid()) return
  writePersistedValue(capabilitySurface(), { enabled })
}

// Every mounted useMemories subscribes here so a refresh/create in one place
// (e.g. the Settings importer) updates the Memories page too — without this the
// module cache only refreshed the component that triggered the write.
export const subscribers = new Set<(list: Memory[]) => void>()

export function publish(list: Memory[], view: MemoryReadView | null = cache.view): void {
  cache.list = list
  cache.view = view
  // Mirror the current list to the per-uid cold-start snapshot so the next app
  // launch renders it instantly (see hydrateFromDisk). Best-effort and bounded.
  const surface = view && view !== 'useful_now' ? `${CACHE_SURFACE}.${view}` : CACHE_SURFACE
  writePersistedCache(surface, list.slice(0, PERSIST_CAP))
  subscribers.forEach((fn) => fn(list))
}

// Cold-start hydration: on the first hook mount of the session, seed the in-memory
// cache from the per-uid persisted snapshot so the Memories page renders the
// last-known memories immediately instead of a spinner. `loaded` stays false, so
// the revalidating fetch still runs and overwrites with fresh data. Runs at
// hook-mount time (not module load) so the signed-in uid is already set.
let hydratedSurface: string | null = null
export function hydrateFromDisk(view: MemoryReadView = 'useful_now'): void {
  const surface = view && view !== 'useful_now' ? `${CACHE_SURFACE}.${view}` : CACHE_SURFACE
  if (hydratedSurface === surface) return
  hydratedSurface = surface
  if (cache.list !== null && cache.view === view) return
  // The list!==null guard is deliberately dropped: hydrating view B with
  // loaded=true left over from view A (list already null) would make the hook's
  // revalidation effect skip its fetch, so view B would never load at all.
  if (cache.view !== view) {
    cache.list = null
    cache.loaded = false
  }
  const persisted = readPersistedCache<Memory>(surface)
  if (persisted && persisted.length > 0) {
    cache.list = persisted
    cache.view = view
  }
  if (cache.beliefEnabled === null) cache.beliefEnabled = readBeliefCapability()
}

// Reset the in-memory cache on sign-out / account switch so a second account on
// the same machine never sees the prior user's memories from this module-level
// singleton. The per-uid disk snapshot is purged separately by
// clearAllPersistedCaches in the same teardown. Called from authTeardown.
export function resetMemoriesCache(): void {
  cache.list = null
  cache.error = null
  cache.loaded = false
  cache.view = null
  cache.canonicalLifecycleExposed = false
  cache.beliefEnabled = null
  hydratedSurface = null
  // Notify any mounted Memories view so it clears the prior user's list without a
  // relaunch, matching invalidateConversationsCache's teardown broadcast (the
  // teardown's whole point is to reflect the wipe in the current window).
  subscribers.forEach((fn) => fn([]))
}
