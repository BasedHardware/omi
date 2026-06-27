export type ConversationRow = {
  id: string
  title: string
  /** Topic emoji from the backend's structured summary (macOS parity). Undefined
   *  when none / still processing. */
  emoji?: string
  subtitle: string
  preview: string
  source: 'cloud' | 'local'
  // For local rows: distinguishes captured recordings from saved Omi chats so
  // the list can badge them differently. Undefined for cloud rows.
  localKind?: 'recording' | 'chat'
  // True for optimistic placeholder rows shown immediately on finalize (titled
  // client-side, dropped once the backend's real conversation arrives).
  pending?: boolean
  sortAt: number
}

export const conversationsCache = {
  rows: null as ConversationRow[] | null,
  error: null as string | null,
  loaded: false
}

// Notify a mounted Conversations list that the local store changed so it can
// refresh in real time (e.g. while an Omi chat is being saved) without waiting
// for a remount. Subscribers should re-read local conversations only.
const subscribers = new Set<() => void>()

export function subscribeConversations(cb: () => void): () => void {
  subscribers.add(cb)
  return () => {
    subscribers.delete(cb)
  }
}

export function invalidateConversationsCache(): void {
  conversationsCache.loaded = false
  conversationsCache.rows = null
  conversationsCache.error = null
  subscribers.forEach((cb) => cb())
}

// Separate channel for forcing a CLOUD re-fetch (e.g. the continuous-recording
// host after the backend signals `memory_creating`). The local-only
// `subscribeConversations` channel above re-reads local rows; this one tells a
// mounted Conversations list to re-run its full cloud+local fetch.
const cloudRefreshSubscribers = new Set<() => void>()

export function subscribeCloudRefresh(cb: () => void): () => void {
  cloudRefreshSubscribers.add(cb)
  return () => {
    cloudRefreshSubscribers.delete(cb)
  }
}

// Debounced so the host/live-view cleanups (which each call this) coalesce into a
// single cloud re-fetch instead of a burst. `loaded` is cleared immediately so any
// fresh mount still re-fetches; the subscriber notify (which drives in-place
// re-fetch on a mounted list) is the part that's debounced.
let refreshTimer: ReturnType<typeof setTimeout> | null = null

export function refreshCloudConversations(): void {
  conversationsCache.loaded = false
  if (refreshTimer) clearTimeout(refreshTimer)
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    cloudRefreshSubscribers.forEach((cb) => cb())
  }, 400)
}

// Optimistic "pending" conversations: shown in the list the instant a conversation
// is finalized (so it never sits waiting on the slow backend), titled client-side,
// and dropped once the backend's real cloud conversation for that window arrives.
// Pure data ops only — the client-side titling lives in pendingConversations.ts so
// this module stays firebase-free / unit-testable.
let pending: ConversationRow[] = []

export function getPendingConversations(): ConversationRow[] {
  return pending
}

// Add a placeholder row (empty title → the list renders "loading…" in italic) and
// notify mounted lists. Returns its id so the titler can fill it in.
export function addPendingConversation(transcript: string): string {
  const id = `pending-${Date.now()}-${Math.random().toString(36).slice(2)}`
  const now = Date.now()
  pending = [
    {
      id,
      title: '',
      emoji: undefined,
      subtitle: new Date(now).toLocaleString(),
      preview: transcript.slice(0, 200) || '(no transcript)',
      source: 'cloud',
      pending: true,
      sortAt: now
    },
    ...pending
  ]
  // Lightweight re-merge (no cloud refetch) — the list folds pendings in alongside
  // its already-loaded rows.
  subscribers.forEach((cb) => cb())
  return id
}

export function setPendingTopic(id: string, title: string, emoji: string): void {
  pending = pending.map((p) => (p.id === id ? { ...p, title, emoji: emoji || p.emoji } : p))
  subscribers.forEach((cb) => cb())
}

// Drop pendings the backend has now produced (a cloud conversation within ~2min of
// the pending), plus any past a TTL safety net. Call with the freshly-fetched cloud
// rows during a list load.
export function reconcilePending(cloudRows: ConversationRow[]): void {
  const TTL = 5 * 60_000
  const now = Date.now()
  pending = pending.filter((p) => {
    if (now - p.sortAt > TTL) return false
    const replaced = cloudRows.some((c) => c.sortAt >= p.sortAt - 30_000 && c.sortAt <= p.sortAt + 180_000)
    return !replaced
  })
}
