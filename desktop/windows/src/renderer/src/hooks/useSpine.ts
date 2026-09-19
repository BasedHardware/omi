// Loads the four sources the Activity spine composes, and holds the view state
// that is deliberately NOT persisted.
//
// Screen days are fetched separately from the rest, because they are the only
// source whose cost scales with how much the user captured. The day list is one
// cheap call; each day's projection is another. A day that has not been
// projected yet is absent from `screen` AND from `loadedScreenDays`, which is
// what lets the rail say "counting" instead of claiming the day held nothing.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { omiApi } from '../lib/apiClient'
import type { Conversation, MemoryDB } from '../lib/omiApi.generated'
import type { SpineScreenDay } from '../../../shared/types'
import {
  composeSpine,
  filterSpine,
  type SpineDay,
  type SpineDayScreen,
  type SpineKind
} from '../lib/spine/spineModel'
import {
  compact,
  toScreenMap,
  toSpineConversation,
  toSpineMemory,
  toSpineTask
} from '../lib/spine/spineSources'

/** Conversations and memories pulled for the stream. Deep enough to cover a
 *  couple of weeks for an ordinary account without paging on first paint. */
export const CONVERSATION_LIMIT = 200
export const MEMORY_LIMIT = 300
export const TASK_LIMIT = 300
/** Screen days projected up front. The rest report a null count until asked. */
export const SCREEN_DAYS = 14

export interface UseSpine {
  days: SpineDay[]
  /** Unfiltered, for counts that should not move when a chip is pressed. */
  allDays: SpineDay[]
  loading: boolean
  /** True when a source failed; the stream still shows whatever loaded. */
  degraded: boolean
  kind: SpineKind | null
  setKind: (kind: SpineKind | null) => void
  query: string
  setQuery: (query: string) => void
  folded: ReadonlySet<number>
  toggleFold: (dayId: number) => void
  reload: () => void
}

async function loadConversations(): Promise<Conversation[] | null> {
  try {
    const r = await omiApi.get<Conversation[]>('/v1/conversations', {
      params: { limit: CONVERSATION_LIMIT, offset: 0 }
    })
    return Array.isArray(r.data) ? r.data : []
  } catch {
    return null
  }
}

async function loadMemories(): Promise<MemoryDB[] | null> {
  try {
    const r = await omiApi.get<MemoryDB[]>('/v3/memories', {
      params: { limit: MEMORY_LIMIT, offset: 0 }
    })
    return Array.isArray(r.data) ? r.data : []
  } catch {
    return null
  }
}

async function loadTasks(): Promise<ReturnType<typeof toSpineTask>[] | null> {
  const api = window.omi
  if (!api?.tasksListIncomplete) return null
  try {
    const [incomplete, completed] = await Promise.all([
      api.tasksListIncomplete({ limit: TASK_LIMIT }),
      api.tasksListCompleted?.({ limit: TASK_LIMIT }) ?? Promise.resolve([])
    ])
    // Completed tasks belong in a timeline: the point of looking back at a day
    // is often to see what got finished in it.
    return [...incomplete, ...completed].map(toSpineTask)
  } catch {
    return null
  }
}

async function loadScreen(): Promise<{
  screen: Record<number, SpineDayScreen>
  loaded: Set<number>
} | null> {
  const api = window.omi
  if (!api?.spineScreenDays || !api?.spineScreenDay) return null
  try {
    const dayIds = await api.spineScreenDays(SCREEN_DAYS)
    const projections = await Promise.all(dayIds.map((id) => api.spineScreenDay(id)))
    const present = projections.filter((p): p is SpineScreenDay => p !== null)
    return { screen: toScreenMap(present), loaded: new Set(present.map((p) => p.dayId)) }
  } catch {
    return null
  }
}

export function useSpine(): UseSpine {
  // One piece of state for the whole load, null until the first answer arrives.
  // `loading` is DERIVED from it rather than stored, so there is no path that
  // leaves a spinner up over results that already loaded.
  const [result, setResult] = useState<{ days: SpineDay[]; degraded: boolean } | null>(null)
  const [kind, setKind] = useState<SpineKind | null>(null)
  const [query, setQuery] = useState('')
  // Fold state is keyed by the day's own identity, never by index, so paging
  // older days in cannot move which day is folded. Session-only on purpose: a
  // day folded last week should not still be hidden today.
  const [folded, setFolded] = useState<ReadonlySet<number>>(() => new Set())
  const [nonce, setNonce] = useState(0)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      const [conversations, memories, tasks, screen] = await Promise.all([
        loadConversations(),
        loadMemories(),
        loadTasks(),
        loadScreen()
      ])
      if (cancelled || !mounted.current) return
      // Any source may be null; the stream shows what did load and says so,
      // because a timeline missing one source is far more useful than none.
      setResult({
        degraded: conversations === null || memories === null || tasks === null || screen === null,
        days: composeSpine({
          conversations: compact((conversations ?? []).map(toSpineConversation)),
          memories: compact((memories ?? []).map(toSpineMemory)),
          tasks: compact(tasks ?? []),
          screen: screen?.screen ?? {},
          loadedScreenDays: screen?.loaded ?? new Set()
        })
      })
    })()
    return () => {
      cancelled = true
    }
  }, [nonce])

  // Memoised so the identity is stable across renders; without it the filter
  // below would recompute on every render even when nothing changed.
  const days = useMemo(() => result?.days ?? [], [result])
  const filtered = useMemo(() => filterSpine(days, kind, query), [days, kind, query])

  const toggleFold = useCallback((dayId: number) => {
    setFolded((prev) => {
      const next = new Set(prev)
      if (next.has(dayId)) next.delete(dayId)
      else next.add(dayId)
      return next
    })
  }, [])

  const reload = useCallback(() => {
    setResult(null)
    setNonce((n) => n + 1)
  }, [])

  return {
    days: filtered,
    allDays: days,
    loading: result === null,
    degraded: result?.degraded ?? false,
    kind,
    setKind,
    query,
    setQuery,
    folded,
    toggleFold,
    reload
  }
}
