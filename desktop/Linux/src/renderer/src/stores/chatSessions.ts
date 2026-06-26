import { create } from 'zustand'
import { api } from '../api/client'
import type { ChatSession } from '../api/types'

interface ChatSessionsStore {
  sessions: ChatSession[]
  currentId: string | null
  loading: boolean
  starredOnly: boolean
  query: string
  load: () => Promise<void>
  select: (id: string | null) => void
  create: () => Promise<string | null>
  remove: (id: string) => Promise<void>
  toggleStar: (id: string) => Promise<void>
  rename: (id: string, title: string) => Promise<void>
  setStarredOnly: (v: boolean) => void
  setQuery: (v: string) => void
}

/** Date-bucket labels, mirroring ChatSessionsSidebar.swift's groupedSessions. */
export type SessionGroupLabel = 'Today' | 'Yesterday' | 'Previous 7 days' | 'Older'

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

/** Which date bucket a session falls into, based on its created_at day. */
export function sessionGroupLabel(session: ChatSession, now: Date = new Date()): SessionGroupLabel {
  const today = startOfDay(now)
  const day = 86400_000
  const ts = session.created_at ? new Date(session.created_at).getTime() : NaN
  if (Number.isNaN(ts)) return 'Older'
  const created = startOfDay(new Date(ts))
  if (created >= today) return 'Today'
  if (created >= today - day) return 'Yesterday'
  if (created >= today - 7 * day) return 'Previous 7 days'
  return 'Older'
}

/** Apply the starred filter and the case-insensitive title search. */
export function filterSessions(sessions: ChatSession[], starredOnly: boolean, query: string): ChatSession[] {
  const q = query.trim().toLowerCase()
  return sessions.filter((s) => {
    if (starredOnly && !s.starred) return false
    if (q && !(s.title || 'New Chat').toLowerCase().includes(q)) return false
    return true
  })
}

const GROUP_ORDER: SessionGroupLabel[] = ['Today', 'Yesterday', 'Previous 7 days', 'Older']

/** Group already-filtered sessions into ordered [label, sessions] date buckets. */
export function groupSessions(
  sessions: ChatSession[],
  now: Date = new Date()
): Array<[SessionGroupLabel, ChatSession[]]> {
  const buckets = new Map<SessionGroupLabel, ChatSession[]>()
  for (const s of sessions) {
    const label = sessionGroupLabel(s, now)
    const arr = buckets.get(label)
    if (arr) arr.push(s)
    else buckets.set(label, [s])
  }
  return GROUP_ORDER.filter((label) => buckets.has(label)).map((label) => [label, buckets.get(label)!])
}

export const useChatSessions = create<ChatSessionsStore>((set, get) => ({
  sessions: [],
  currentId: null,
  loading: false,
  starredOnly: false,
  query: '',
  load: async () => {
    set({ loading: true })
    try {
      const sessions = await api.listChatSessions(50)
      set({ sessions, loading: false })
      if (!get().currentId && sessions.length > 0) set({ currentId: sessions[0].id })
    } catch {
      set({ loading: false })
    }
  },
  select: (id) => set({ currentId: id }),
  create: async () => {
    try {
      const s = await api.createChatSession()
      set({ sessions: [s, ...get().sessions], currentId: s.id })
      return s.id
    } catch {
      return null
    }
  },
  remove: async (id) => {
    const next = get().sessions.filter((s) => s.id !== id)
    set({ sessions: next, currentId: get().currentId === id ? (next[0]?.id ?? null) : get().currentId })
    try {
      await api.deleteChatSession(id)
    } catch {
      await get().load()
    }
  },
  toggleStar: async (id) => {
    const s = get().sessions.find((x) => x.id === id)
    if (!s) return
    const starred = !s.starred
    set({ sessions: get().sessions.map((x) => (x.id === id ? { ...x, starred } : x)) })
    try {
      await api.patchChatSession(id, { starred })
    } catch {
      await get().load()
    }
  },
  rename: async (id, title) => {
    set({ sessions: get().sessions.map((x) => (x.id === id ? { ...x, title } : x)) })
    await api.patchChatSession(id, { title })
  },
  setStarredOnly: (v) => set({ starredOnly: v }),
  setQuery: (v) => set({ query: v })
}))
