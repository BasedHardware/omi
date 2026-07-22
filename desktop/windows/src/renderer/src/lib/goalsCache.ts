// Module-singleton cache for the user's goals, extracted to a leaf module (no
// React, no apiClient imports) so the sign-out teardown can reset it without an
// import cycle: authTeardown is reachable from firebase.ts, and Goals.tsx pulls in
// React + apiClient (which imports firebase). Mirrors memoriesCache.ts / pageCache.ts.
// Goals.tsx owns the fetch/mutation logic and imports this state.
//
// `import type` is erased at runtime, so importing the Goal type creates no runtime
// cycle even though omiApi.generated carries the client.
import type { GoalResponse as Goal } from './omiApi.generated'
import { readPersistedCache, writePersistedCache } from './persistentCache'

export const cache = {
  goals: null as Goal[] | null,
  loaded: false
}

const CACHE_SURFACE = 'goals'
const PERSIST_CAP = 500

// Single write path for the goals list. Mirrors it to the per-uid cold-start
// snapshot so the next launch paints it instantly (see hydrateGoalsFromDisk).
// Best-effort and bounded.
export function writeCache(list: Goal[]): void {
  cache.goals = list
  writePersistedCache(CACHE_SURFACE, list.slice(0, PERSIST_CAP))
}

// Cold-start hydration: seed the in-memory cache from the per-uid snapshot on the
// first mount so the Goals page paints last-known goals immediately instead of a
// spinner. `loaded` stays false so the revalidating fetch still runs. Runs at
// component-mount time (not module load) so the signed-in uid is already set.
let hydratedFromDisk = false
export function hydrateGoalsFromDisk(): void {
  if (hydratedFromDisk) return
  hydratedFromDisk = true
  if (cache.goals !== null) return
  const persisted = readPersistedCache<Goal>(CACHE_SURFACE)
  if (persisted && persisted.length > 0) cache.goals = persisted
}

// Reset the in-memory cache on sign-out / account switch so a second account on
// the same machine never sees the prior user's goals from this module-level
// singleton. The per-uid disk snapshot is purged separately by
// clearAllPersistedCaches in the same teardown. Called from authTeardown.
export function resetGoalsCache(): void {
  cache.goals = null
  cache.loaded = false
  hydratedFromDisk = false
}
