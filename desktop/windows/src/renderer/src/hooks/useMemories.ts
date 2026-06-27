import { useEffect, useState } from 'react'
import { omiApi } from '../lib/apiClient'

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
}

const cache = {
  list: null as Memory[] | null,
  error: null as string | null,
  loaded: false
}

// Every mounted useMemories subscribes here so a refresh/create in one place
// (e.g. the Settings importer) updates the Memories page too — without this the
// module cache only refreshed the component that triggered the write.
const subscribers = new Set<(list: Memory[]) => void>()

function publish(list: Memory[]): void {
  cache.list = list
  subscribers.forEach((fn) => fn(list))
}

function extractList(data: unknown): Memory[] {
  if (Array.isArray(data)) return data as Memory[]
  return ((data as { memories?: Memory[] })?.memories ?? []) as Memory[]
}

// Optional extra fields for a created memory. `tags` carries provenance (e.g.
// 'omi-app-index'); `category` is sent best-effort — the server may ignore or
// reassign it, so UI coloring must not depend on it.
export type CreateMemoryExtra = { category?: string; tags?: string[] }

// Match the server KG's build budget (it's built from up to 500 memories), so
// the brain map can scope itself to roughly the same memory set the graph was
// derived from rather than just the first 100. Also lets the Memories list show
// more than one page.
async function fetchMemories(): Promise<Memory[]> {
  const r = await omiApi.get('/v3/memories', { params: { limit: 500, offset: 0 } })
  // The server doesn't return memories newest-first, so freshly created/imported
  // ones land mid-list and look "missing". Sort by created_at desc here so new
  // memories surface at the top of the Memories page right after a write.
  return extractList(r.data).sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  )
}

export function useMemories(): {
  memories: Memory[]
  loading: boolean
  error: string | null
  createMemory: (content: string, extra?: CreateMemoryExtra) => Promise<void>
  refresh: () => Promise<void>
} {
  const [memories, setMemories] = useState<Memory[]>(cache.list ?? [])
  const [loading, setLoading] = useState(!cache.loaded)
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
    ;(async () => {
      try {
        const list = await fetchMemories()
        if (!cancelled) {
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
          cache.loaded = true
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
    await omiApi.post('/v3/memories', { content: text, ...extra })
    publish(await fetchMemories())
  }

  // Re-pull the server list and broadcast to all mounts. Used after a bulk
  // import so the Memories page and export count reflect the new memories.
  const refresh = async (): Promise<void> => {
    publish(await fetchMemories())
  }

  return { memories, loading, error, createMemory, refresh }
}
