import { omiApi } from './apiClient'
import type { Memory } from '../hooks/useMemories'

// Provenance tag the (now-removed) app-index pipeline stamped on every "Uses
// <App>" memory it synthesized. App→memory synthesis was removed to match the
// macOS app, which keeps app data in the local knowledge graph and never as
// memories. This tag now exists only so the one-time purge below can find and
// delete the legacy memories earlier builds created.
export const APP_MEMORY_TAG = 'omi-app-index'

// Content prefix the pipeline used ("Uses <App>"). Retained because the
// onboarding brain-map model still references it to recognize app-derived
// memories; kept here so that (untouched) file keeps compiling.
export const APP_MEMORY_PREFIX = 'Uses '

function extractList(data: unknown): Memory[] {
  if (Array.isArray(data)) return data as Memory[]
  return ((data as { memories?: Memory[] })?.memories ?? []) as Memory[]
}

// Pure: ids of memories created by the app-index pipeline, matched STRICTLY by
// provenance tag — so legitimate user memories, even ones that happen to start
// with "Uses …", are never deleted.
export function appMemoryIdsToDelete(memories: Memory[]): string[] {
  return memories.filter((m) => m.tags?.includes(APP_MEMORY_TAG)).map((m) => m.id)
}

// One-time cleanup: page through ALL memories collecting the legacy app-index
// ones (paging first, with no deletes, so offsets stay stable), then delete them.
// Best-effort and idempotent. Returns the number deleted.
export async function purgeAppMemories(): Promise<number> {
  const ids: string[] = []
  for (let offset = 0; offset < 5000; offset += 200) {
    const r = await omiApi.get('/v3/memories', { params: { limit: 200, offset } })
    const page = extractList(r.data)
    ids.push(...appMemoryIdsToDelete(page))
    if (page.length < 200) break
  }
  let deleted = 0
  for (const id of ids) {
    try {
      await omiApi.delete(`/v3/memories/${id}`)
      deleted++
    } catch (e) {
      console.warn('[appIndex] failed to delete app memory', id, e)
    }
  }
  return deleted
}

const PURGE_FLAG = 'omi.appMemories.purged'

// Run purgeAppMemories at most once per install. The flag is set only after a
// clean pass, so an unauthenticated early run retries on the next launch.
// Best-effort: never throws, never blocks startup.
export async function purgeAppMemoriesOnce(): Promise<void> {
  try {
    if (localStorage.getItem(PURGE_FLAG)) return
    await purgeAppMemories()
    localStorage.setItem(PURGE_FLAG, '1')
  } catch (e) {
    console.warn('[appIndex] one-time app-memory purge failed; will retry next launch', e)
  }
}

// Deprecated no-op. App→memory synthesis was removed for macOS parity; apps now
// reach the knowledge graph only via the local KG build (deriveAppNodes from the
// file index). Kept exported so the onboarding step that still calls it compiles
// untouched — onboarding's KG wiring is handled separately. Always returns 0.
export async function runAppIndexing(): Promise<number> {
  return 0
}
