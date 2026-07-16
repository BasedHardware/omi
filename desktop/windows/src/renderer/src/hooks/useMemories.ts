import { useEffect, useState } from 'react'
import { omiApi } from '../lib/apiClient'
import { fetchAllMemoriesPaged } from '../lib/memoriesBulk'
import { cache, hydrateFromDisk, publish, subscribers } from '../lib/memoriesCache'
import { getCacheUid } from '../lib/persistentCache'

export type Memory = {
  id: string
  uid: string
  content: string
  headline?: string | null
  category?: string
  visibility?: string
  tags?: string[]
  created_at: string
  updated_at: string
  conversation_id?: string | null
  // Canonical product lifecycle layer (short_term/long_term/…), derived from
  // memory_tier on the backend at serialization time. Null for legacy/untiered
  // memories — the tier badge renders ONLY when this is set (mirrors Mac's
  // `tierIsExplicit` rule), and the layer filter is itself hidden unless the
  // server advertises tier exposure (see canonicalLifecycleExposed).
  layer?: string | null
  memory_tier?: string | null
  // Capture provenance — shown in the card footer / detail sheet when present.
  primary_capture_device?: string | null
  capture_device_ids?: string[]
  manually_added?: boolean
  capture_confidence?: number | null
  app_id?: string | null
}

// Axios lowercases response header keys.
const CANONICAL_LIFECYCLE_HEADER = 'x-omi-memory-canonical-lifecycle-exposed'

// Optional extra fields for a created memory. `tags` carries provenance (e.g.
// 'omi-app-index'); `category` is sent best-effort — the server may ignore or
// reassign it, so UI coloring must not depend on it.
export type CreateMemoryExtra = { category?: string; tags?: string[] }

// Fetch EVERY memory for the page, not just the first server page. The backend
// forces limit=5000 whenever offset is 0, so the old single
// `GET /v3/memories?limit=500&offset=0` call silently capped the page at the
// server's first ~5000 rows and never requested a second page — an account with
// more than 5000 memories would never see the tail (while bulk export/purge,
// which already paged via fetchAllMemories, reached all of them). Reuse the one
// shared pager so display and bulk paths can't drift, and read the
// canonical-lifecycle capability header off the first response to gate the
// tier/device filters. Then sort newest-first: the server doesn't return
// memories in created_at order, so freshly created/imported ones would
// otherwise land mid-list and look "missing".
async function fetchMemories(): Promise<Memory[]> {
  const list = await fetchAllMemoriesPaged((r) => {
    const header = r.headers?.[CANONICAL_LIFECYCLE_HEADER]
    if (typeof header === 'string') cache.canonicalLifecycleExposed = header === 'true'
  })
  return list.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
}

// Shared by editMemory and setMemoryVisibility: both PATCH a single field and
// send it as a QUERY param, not a JSON body — that's the backend's actual
// contract for PATCH /v3/memories/{id}[/visibility] (see edit_memory /
// update_memory_visibility in backend/routers/memories.py, plain `value: str`
// function args, which FastAPI binds as query params for non-model types).
// Optimistic; reverts the cache on failure so the UI doesn't show a save that
// didn't happen.
async function patchMemoryOptimistic(
  id: string,
  urlPath: string,
  value: string,
  apply: (m: Memory) => Memory
): Promise<void> {
  const originUid = getCacheUid()
  const prev = cache.list ?? []
  publish(prev.map((m) => (m.id === id ? apply(m) : m)))
  try {
    await omiApi.patch(urlPath, null, { params: { value } })
  } catch (e) {
    // Revert only if still the same account — a switch mid-request already reset
    // A's cache, so re-publishing A's `prev` list would stamp it under B.
    if (getCacheUid() === originUid) publish(prev)
    throw e
  }
}

export function useMemories(): {
  memories: Memory[]
  loading: boolean
  error: string | null
  // True only when the server advertises canonical memory tiering for this
  // account. Gates the tier/device filters so they never render against a
  // backend that would return nothing (prod runs MEMORY_MODE=off). Read at
  // render time — every change to it lands alongside a list publish, which
  // forces the re-render that surfaces the new value.
  canonicalLifecycleExposed: boolean
  createMemory: (content: string, extra?: CreateMemoryExtra) => Promise<void>
  editMemory: (id: string, content: string) => Promise<void>
  setMemoryVisibility: (id: string, visibility: 'public' | 'private') => Promise<void>
  deleteMemory: (id: string) => Promise<void>
  refresh: () => Promise<void>
} {
  hydrateFromDisk()
  const [memories, setMemories] = useState<Memory[]>(cache.list ?? [])
  // Show cached memories immediately on cold start (no spinner) whenever we have a
  // snapshot to render — from disk (hydrateFromDisk) or a prior in-session fetch.
  // Only fall back to the loading state when there is genuinely nothing to show.
  // The revalidating fetch still runs (gated on cache.loaded), so fresh data lands
  // shortly after.
  const [loading, setLoading] = useState(!cache.loaded && (cache.list?.length ?? 0) === 0)
  const [error, setError] = useState<string | null>(cache.error)

  useEffect(() => {
    subscribers.add(setMemories)
    return () => {
      subscribers.delete(setMemories)
    }
  }, [])

  useEffect(() => {
    if (cache.loaded) return

    let cancelled = false
    const originUid = getCacheUid()
    ;(async () => {
      try {
        const list = await fetchMemories()
        // Account-switch guard (belt-and-suspenders alongside `cancelled`): drop the
        // publish if the account changed while the fetch was in flight, so it can't
        // write A's memories under B's uid on a future in-place switch.
        if (!cancelled && getCacheUid() === originUid) {
          cache.error = null
          publish(list)
        }
      } catch (e) {
        if (!cancelled) {
          const msg =
            (e as { response?: { data?: { detail?: string } }; message: string }).response?.data
              ?.detail ?? (e as Error).message
          cache.error = msg
          setError(msg)
        }
      } finally {
        if (!cancelled) {
          // Only mark the module cache "loaded" if this fetch still belongs to the
          // current account. Otherwise a stale fetch would leave loaded=true with
          // list=null (reset by teardown), so account B would skip its own
          // revalidation (if (cache.loaded) return) and show an empty list.
          if (getCacheUid() === originUid) cache.loaded = true
          setLoading(false)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // Create a manual memory, then re-fetch so the list reflects whatever the
  // server actually stored (id, timestamps, category) rather than guessing the
  // POST response shape.
  const createMemory = async (content: string, extra?: CreateMemoryExtra): Promise<void> => {
    const text = content.trim()
    if (!text) return
    const originUid = getCacheUid()
    await omiApi.post('/v3/memories', { content: text, ...extra })
    const list = await fetchMemories()
    // Drop the publish if the account switched while the request was in flight
    // (same guard as the revalidation effect) — never write A's memories under B.
    if (getCacheUid() === originUid) publish(list)
  }

  // Edit a memory's content.
  const editMemory = async (id: string, content: string): Promise<void> => {
    const text = content.trim()
    if (!text) return
    await patchMemoryOptimistic(id, `/v3/memories/${id}`, text, (m) => ({ ...m, content: text }))
  }

  // Same query-param contract as editMemory, for PATCH /v3/memories/{id}/visibility.
  const setMemoryVisibility = async (
    id: string,
    visibility: 'public' | 'private'
  ): Promise<void> => {
    await patchMemoryOptimistic(id, `/v3/memories/${id}/visibility`, visibility, (m) => ({
      ...m,
      visibility
    }))
  }

  // Delete a single memory, optimistically dropping it from the cache and
  // reverting on failure. The Memories page owns the undo window (it keeps the
  // row hidden locally and only calls this once the countdown elapses), so by
  // the time this fires the delete is committed — there's no server call to
  // walk back, only the local list to restore if the request errors.
  const deleteMemory = async (id: string): Promise<void> => {
    const originUid = getCacheUid()
    const prev = cache.list ?? []
    publish(prev.filter((m) => m.id !== id))
    try {
      await omiApi.delete(`/v3/memories/${id}`)
    } catch (e) {
      // Same-account revert only — see patchMemoryOptimistic.
      if (getCacheUid() === originUid) publish(prev)
      throw e
    }
  }

  // Re-pull the server list and broadcast to all mounts. Used after a bulk
  // import so the Memories page and export count reflect the new memories.
  const refresh = async (): Promise<void> => {
    const originUid = getCacheUid()
    const list = await fetchMemories()
    if (getCacheUid() === originUid) publish(list)
  }

  return {
    memories,
    loading,
    error,
    canonicalLifecycleExposed: cache.canonicalLifecycleExposed,
    createMemory,
    editMemory,
    setMemoryVisibility,
    deleteMemory,
    refresh
  }
}
