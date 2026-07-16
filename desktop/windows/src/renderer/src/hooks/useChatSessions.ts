import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ChatSession } from '../../../shared/chatSessions'
import {
  createSession as createSessionApi,
  deleteSession as deleteSessionApi,
  listSessions as listSessionsApi,
  updateSession as updateSessionApi
} from '../lib/chatSessionsClient'
import { filterSessions, groupSessionsByDate, type SessionGroup } from '../lib/chatSessionsView'

// The subset of the data-layer client the hook uses. Injectable so the hook
// unit-tests against a fake without mocking the module graph (which pulls in
// axios + Firebase).
export interface SessionsClientLike {
  listSessions: typeof listSessionsApi
  createSession: typeof createSessionApi
  updateSession: typeof updateSessionApi
  deleteSession: typeof deleteSessionApi
}

const realClient: SessionsClientLike = {
  listSessions: listSessionsApi,
  createSession: createSessionApi,
  updateSession: updateSessionApi,
  deleteSession: deleteSessionApi
}

function errorMessage(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  if (e instanceof Error && e.message) return e.message
  return 'Something went wrong'
}

export interface UseChatSessions {
  /** All loaded sessions (server order: `updated_at DESC`). */
  sessions: ChatSession[]
  /** `sessions` after the client-side search filter. */
  filteredSessions: ChatSession[]
  /** `filteredSessions` grouped into date buckets for the list. */
  groupedSessions: SessionGroup[]
  /** The selected session id, or `null` for the default shared thread. The
   *  default thread is NEVER a session id — that is the continuity invariant. */
  currentSessionId: string | null
  loading: boolean
  /** List-load error (a `listSessions` failure). Repaints the list as an error
   *  state — kept separate from `createError` so a failed "+" never mislabels
   *  the whole list as "Failed to load chats". */
  error: string | null
  /** A `createNewSession` failure only. Rendered as a small transient notice
   *  near the "+" — NEVER a list-body swap. Mirrors Mac's `errorMessage` vs
   *  `sessionsLoadError` split. */
  createError: string | null
  searchQuery: string
  showStarredOnly: boolean
  setSearchQuery: (q: string) => void
  /** Toggle the header "Starred" filter; re-queries the server with starred=true. */
  toggleStarredFilter: () => void
  /** Retry after a load error. */
  retryLoad: () => void
  /** Dismiss the transient create-error notice. */
  clearCreateError: () => void
  /** Select a session, or `null` to return to the default shared thread. Sets
   *  `currentSessionId` + the highlight only; the UI layer pairs this with
   *  `useChat().switchThread(id)` to actually re-thread the live chat engine. */
  selectSession: (id: string | null) => void
  /** Create a new desktop-local session and select it. */
  createNewSession: () => Promise<ChatSession | null>
  /** Rename; silently no-ops on an empty or unchanged title. */
  renameSession: (id: string, title: string) => Promise<void>
  /** Toggle a session's starred flag. */
  toggleStar: (id: string) => Promise<void>
  /** Delete a session (server cascades its messages). No undo. */
  removeSession: (id: string) => Promise<void>
}

/**
 * State + data orchestration for the chat-sessions popover. Owns the sessions
 * list, the selected session, the search text, and the starred filter, and
 * drives the data-layer client for CRUD.
 *
 * NOTE: this hook manages session-list state only. Actually re-threading the
 * live chat engine (`useChat`) onto a selected session is done at the UI layer:
 * the header calls `selectSession(id)` here AND `useChat().switchThread(id)` so
 * `chatIdRef` + the loaded transcript follow the highlight.
 */
export function useChatSessions(options?: { client?: SessionsClientLike }): UseChatSessions {
  const client = options?.client ?? realClient

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showStarredOnly, setShowStarredOnly] = useState(false)
  // Bumping this re-runs the fetch effect (retry, or a post-mutation re-query)
  // without changing `showStarredOnly`.
  const [reloadToken, setReloadToken] = useState(0)

  // The fetch is INLINED in the effect (not a shared setState-ing callback) and
  // every write lands after the await, so the effect never triggers a
  // synchronous setState. `loading` is owned by the initializer + the handlers
  // below; a superseded fetch is cancelled by the effect cleanup.
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const rows = await client.listSessions(showStarredOnly ? { starred: true } : {})
        if (cancelled) return
        setSessions(rows)
        setError(null)
      } catch (e) {
        if (cancelled) return
        setError(errorMessage(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [client, showStarredOnly, reloadToken])

  // Event handlers may setState freely (the effect restriction is the concern).
  // Show the spinner, then let the effect fetch and clear it.
  const toggleStarredFilter = useCallback(() => {
    setError(null)
    setLoading(true)
    setShowStarredOnly((v) => !v)
  }, [])
  const retryLoad = useCallback(() => {
    setError(null)
    setLoading(true)
    setReloadToken((t) => t + 1)
  }, [])
  const clearCreateError = useCallback(() => setCreateError(null), [])
  const selectSession = useCallback((id: string | null) => setCurrentSessionId(id), [])

  const createNewSession = useCallback(async (): Promise<ChatSession | null> => {
    setCreateError(null)
    try {
      const created = await client.createSession()
      setSessions((prev) => [created, ...prev])
      setCurrentSessionId(created.id)
      return created
    } catch (e) {
      // Its OWN error channel — a failed "+" must NOT repaint the loaded list
      // as "Failed to load chats" (that is `error`, owned by the load effect).
      setCreateError(errorMessage(e))
      return null
    }
  }, [client])

  // Mutations catch and surface failures via `error` rather than rejecting — the
  // UI fires them as `void toggleStar(...)`, so an unhandled rejection is the
  // real failure mode to guard against. `removeSession` re-throws after setting
  // error so its awaiting caller (the delete-confirm modal) can keep itself open.
  const renameSession = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim()
      const target = sessions.find((s) => s.id === id)
      // Silent no-op on empty or unchanged title (Mac guard).
      if (!trimmed || (target && trimmed === target.title)) return
      try {
        const updated = await client.updateSession(id, { title: trimmed })
        setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title: updated.title } : s)))
      } catch (e) {
        setError(errorMessage(e))
      }
    },
    [client, sessions]
  )

  const toggleStar = useCallback(
    async (id: string) => {
      const target = sessions.find((s) => s.id === id)
      if (!target) return
      const next = !target.starred
      try {
        await client.updateSession(id, { starred: next })
      } catch (e) {
        setError(errorMessage(e))
        return
      }
      if (showStarredOnly) {
        // The starred filter is a server query; re-run it so an unstarred row
        // drops out of (or a starred row is reflected in) the filtered view.
        setReloadToken((t) => t + 1)
      } else {
        setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, starred: next } : s)))
      }
    },
    [client, sessions, showStarredOnly]
  )

  const removeSession = useCallback(
    async (id: string) => {
      try {
        await client.deleteSession(id)
      } catch (e) {
        setError(errorMessage(e))
        throw e
      }
      setSessions((prev) => prev.filter((s) => s.id !== id))
      // Deleting the open session returns to the default shared thread.
      setCurrentSessionId((cur) => (cur === id ? null : cur))
    },
    [client]
  )

  const filteredSessions = useMemo(
    () => filterSessions(sessions, searchQuery),
    [sessions, searchQuery]
  )
  const groupedSessions = useMemo(() => groupSessionsByDate(filteredSessions), [filteredSessions])

  return {
    sessions,
    filteredSessions,
    groupedSessions,
    currentSessionId,
    loading,
    error,
    createError,
    searchQuery,
    showStarredOnly,
    setSearchQuery,
    toggleStarredFilter,
    retryLoad,
    clearCreateError,
    selectSession,
    createNewSession,
    renameSession,
    toggleStar,
    removeSession
  }
}
