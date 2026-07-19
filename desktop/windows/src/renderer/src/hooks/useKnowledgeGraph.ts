import { useCallback, useEffect, useState } from 'react'
import { fetchKnowledgeGraph, rebuildKnowledgeGraph } from '../lib/knowledgeGraphClient'
import type { KnowledgeGraph } from '../../../shared/types'
import { toast } from '../lib/toast'

const cache = {
  graph: null as KnowledgeGraph | null,
  error: null as string | null,
  loaded: false
}

// Poll cadence after kicking a rebuild: the server-side job is an LLM pass over
// up to 500 memories, so give it a generous ~60s before giving up (the old
// graph stays on screen either way).
const REBUILD_POLL_DELAYS_MS = [2000, 3000, 5000, 8000, 12000, 15000, 15000]

const wait = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms))

// Polls `fetch` until it returns a non-empty graph — i.e. the background rebuild
// has landed and overwritten the snapshot the rebuild endpoint cleared. When the
// graph was ALREADY empty before the rebuild, the first response is authoritative
// (there is no old graph to protect, and "still empty" may be the correct final
// answer). Returns null when every attempt still saw the cleared snapshot; the
// caller keeps the graph it already has. Fetch errors propagate to the caller.
// Exported for tests.
export async function pollRebuiltGraph(
  fetch: () => Promise<KnowledgeGraph>,
  hadGraph: boolean,
  delays: readonly number[] = REBUILD_POLL_DELAYS_MS,
  sleep: (ms: number) => Promise<void> = wait
): Promise<KnowledgeGraph | null> {
  for (const delay of delays) {
    await sleep(delay)
    const g = await fetch()
    if (g.nodes.length > 0 || !hadGraph) return g
  }
  return null
}

function errMessage(e: unknown): string {
  const ax = e as { response?: { status?: number; data?: { detail?: string } }; message: string }
  if (ax.response?.status === 429) return 'Graph rebuild is cooling down, try again shortly.'
  return ax.response?.data?.detail ?? (e as Error).message
}

export function useKnowledgeGraph(): {
  graph: KnowledgeGraph | null
  loading: boolean
  error: string | null
  rebuilding: boolean
  rebuild: () => Promise<void>
  refetch: () => Promise<void>
} {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(cache.graph)
  const [loading, setLoading] = useState(!cache.loaded)
  const [error, setError] = useState<string | null>(cache.error)
  const [rebuilding, setRebuilding] = useState(false)

  useEffect(() => {
    if (cache.loaded) return
    let cancelled = false
    ;(async () => {
      try {
        const g = await fetchKnowledgeGraph()
        if (!cancelled) {
          cache.graph = g
          cache.error = null
          setGraph(g)
        }
      } catch (e) {
        if (!cancelled) {
          cache.error = errMessage(e)
          setError(cache.error)
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

  // Rebuild kicks off a server-side background job. The endpoint synchronously
  // CLEARS the stored graph before re-deriving it (backend
  // routers/knowledge_graph.py: delete → background task), so an immediate
  // re-fetch deterministically returns the cleared, empty snapshot. Adopting
  // that would blank the brain map everywhere — this hook's module cache feeds
  // both the Memories card and the full-screen page. Instead we keep the graph
  // currently on screen and poll until the rebuilt one lands (see
  // pollRebuiltGraph); on timeout or error the old graph stays and a toast
  // explains, so refresh can never leave a blank page.
  const rebuild = async (): Promise<void> => {
    setRebuilding(true)
    setError(null)
    try {
      await rebuildKnowledgeGraph()
      const hadGraph = (cache.graph?.nodes.length ?? 0) > 0
      const g = await pollRebuiltGraph(fetchKnowledgeGraph, hadGraph)
      if (g) {
        cache.graph = g
        cache.error = null
        setGraph(g)
      } else {
        toast('Rebuild is still running', {
          body: 'Your brain map will update once the rebuild finishes.'
        })
      }
    } catch (e) {
      const msg = errMessage(e)
      cache.error = msg
      setError(msg)
      toast('Could not rebuild the brain map', { tone: 'error', body: msg })
    } finally {
      setRebuilding(false)
    }
  }

  // Force a fresh fetch, bypassing the once-per-session module cache. The graph
  // is cached so navigating to Memories is instant, but that means a delete is
  // never reflected; callers invalidate via refetch when memories change.
  const refetch = useCallback(async (): Promise<void> => {
    try {
      const g = await fetchKnowledgeGraph()
      cache.graph = g
      cache.error = null
      setGraph(g)
      setError(null)
    } catch (e) {
      cache.error = errMessage(e)
      setError(cache.error)
    }
  }, [])

  return { graph, loading, error, rebuilding, rebuild, refetch }
}
