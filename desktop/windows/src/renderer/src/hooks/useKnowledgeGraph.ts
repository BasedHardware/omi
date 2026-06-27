import { useCallback, useEffect, useState } from 'react'
import { fetchKnowledgeGraph, rebuildKnowledgeGraph } from '../lib/knowledgeGraphClient'
import type { KnowledgeGraph } from '../../../shared/types'

const cache = {
  graph: null as KnowledgeGraph | null,
  error: null as string | null,
  loaded: false
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

  // Rebuild kicks off a server-side background job, then re-fetches. The job is
  // async server-side, so the immediate re-fetch may still show the old graph;
  // that's acceptable for v1 (the user can refetch). Errors surface via state.
  const rebuild = async (): Promise<void> => {
    setRebuilding(true)
    setError(null)
    try {
      await rebuildKnowledgeGraph()
      const g = await fetchKnowledgeGraph()
      cache.graph = g
      setGraph(g)
    } catch (e) {
      const msg = errMessage(e)
      cache.error = msg
      setError(msg)
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
