import { useEffect, useRef, useState } from 'react'
import { Plus, Star, Search, X, Pencil, Trash2, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { LocalConversation } from '../../../../shared/types'

type Session = {
  id: string
  title: string
  preview: string
  starred: boolean
  sortAt: number
}

function dateGroup(ts: number): string {
  const now = new Date()
  const d = new Date(ts)
  const diff = now.getTime() - d.getTime()
  const days = diff / 86_400_000
  if (days < 1) return 'Today'
  if (days < 2) return 'Yesterday'
  if (days < 7) return 'This Week'
  if (days < 30) return 'This Month'
  return d.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
}

const STARRED_KEY = 'omi.chat.starred'
function loadStarred(): Set<string> {
  try { return new Set(JSON.parse(localStorage.getItem(STARRED_KEY) ?? '[]') as string[]) }
  catch { return new Set() }
}
function saveStarred(ids: Set<string>): void {
  try { localStorage.setItem(STARRED_KEY, JSON.stringify([...ids])) } catch {}
}

export function ChatSessionsSidebar({
  activeId,
  onSelect,
  onNew
}: {
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}): React.JSX.Element {
  const [sessions, setSessions] = useState<Session[]>([])
  const [loading, setLoading] = useState(true)
  const [starred, setStarred] = useState<Set<string>>(loadStarred)
  const [showStarredOnly, setShowStarredOnly] = useState(false)
  const [query, setQuery] = useState('')
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const editRef = useRef<HTMLInputElement>(null)

  const load = async (): Promise<void> => {
    try {
      const all = (await window.omi.listLocalConversations()) as LocalConversation[]
      const chats = all.filter((c) => c.kind === 'chat')
      const mapped: Session[] = chats.map((c) => {
        const msgs = c.messages ?? []
        const last = msgs[msgs.length - 1]
        const preview = last?.content?.trim().slice(0, 80) ?? ''
        return {
          id: c.id,
          title: c.title ?? (msgs.length ? 'Chat with Omi' : 'New Chat'),
          preview,
          starred: starred.has(c.id),
          sortAt: c.endedAt || c.startedAt || 0
        }
      })
      mapped.sort((a, b) => b.sortAt - a.sortAt)
      setSessions(mapped)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [])

  // Re-load when active changes (a new session was created)
  useEffect(() => { void load() }, [activeId])

  const toggleStar = (id: string): void => {
    setStarred((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      saveStarred(next)
      return next
    })
  }

  const deleteSession = async (id: string): Promise<void> => {
    setDeletingId(id)
    try {
      await window.omi.deleteLocalConversation(id)
      setSessions((s) => s.filter((x) => x.id !== id))
      if (activeId === id) onNew()
    } finally {
      setDeletingId(null)
    }
  }

  const startEdit = (s: Session): void => {
    setEditingId(s.id)
    setEditTitle(s.title)
    setTimeout(() => editRef.current?.focus(), 0)
  }

  const saveEdit = async (): Promise<void> => {
    if (!editingId) return
    const trimmed = editTitle.trim()
    if (trimmed) {
      await window.omi.updateLocalConversationTitle(editingId, trimmed)
      setSessions((s) => s.map((x) => x.id === editingId ? { ...x, title: trimmed } : x))
    }
    setEditingId(null)
  }

  const filtered = sessions
    .map((s) => ({ ...s, starred: starred.has(s.id) }))
    .filter((s) => {
      if (showStarredOnly && !s.starred) return false
      if (query && !s.title.toLowerCase().includes(query.toLowerCase()) &&
          !s.preview.toLowerCase().includes(query.toLowerCase())) return false
      return true
    })

  const groups: { label: string; items: Session[] }[] = []
  for (const s of filtered) {
    const label = dateGroup(s.sortAt)
    const g = groups.find((x) => x.label === label)
    if (g) g.items.push(s)
    else groups.push({ label, items: [s] })
  }

  return (
    <div className="flex h-full w-[220px] shrink-0 flex-col border-r border-white/10 bg-[#0a0a0a]">
      {/* Top controls */}
      <div className="flex flex-col gap-2 p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2.5 text-sm font-medium text-[color:var(--accent)] transition-colors hover:bg-white/10"
        >
          <Plus className="h-4 w-4" strokeWidth={2} />
          New Chat
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowStarredOnly((v) => !v)}
            className={cn(
              'flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors',
              showStarredOnly
                ? 'bg-amber-400/15 text-amber-400'
                : 'text-white/45 hover:bg-white/[0.06] hover:text-white/70'
            )}
          >
            <Star className="h-3 w-3" strokeWidth={showStarredOnly ? 0 : 1.75} fill={showStarredOnly ? 'currentColor' : 'none'} />
            Starred
          </button>
        </div>
        <div className="flex items-center gap-2 rounded-lg bg-white/[0.06] px-2.5 py-1.5">
          <Search className="h-3 w-3 shrink-0 text-white/35" strokeWidth={1.75} />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats…"
            className="flex-1 bg-transparent text-xs text-white/80 placeholder:text-white/30 focus:outline-none"
          />
          {query && (
            <button onClick={() => setQuery('')} className="text-white/30 hover:text-white/70">
              <X className="h-3 w-3" strokeWidth={2} />
            </button>
          )}
        </div>
      </div>

      <div className="h-px w-full bg-white/[0.06]" />

      {/* Sessions list */}
      <div className="flex-1 overflow-y-auto py-2">
        {loading ? (
          <div className="flex items-center justify-center py-8 text-white/30">
            <Loader2 className="h-4 w-4 animate-spin" />
          </div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center py-10 text-center text-xs text-white/30">
            <p>{query ? 'No results' : showStarredOnly ? 'No starred chats' : 'No chats yet'}</p>
            {!query && !showStarredOnly && (
              <p className="mt-1 text-white/20">Start a conversation</p>
            )}
          </div>
        ) : (
          groups.map(({ label, items }) => (
            <div key={label}>
              <p className="px-4 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-white/30">
                {label}
              </p>
              {items.map((s) => (
                <SessionRow
                  key={s.id}
                  session={s}
                  isActive={s.id === activeId}
                  isDeleting={deletingId === s.id}
                  isEditing={editingId === s.id}
                  editTitle={editTitle}
                  editRef={editRef}
                  onSelect={() => onSelect(s.id)}
                  onDelete={() => void deleteSession(s.id)}
                  onStar={() => toggleStar(s.id)}
                  onStartEdit={() => startEdit(s)}
                  onEditChange={setEditTitle}
                  onSaveEdit={() => void saveEdit()}
                  onCancelEdit={() => setEditingId(null)}
                />
              ))}
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function SessionRow({
  session, isActive, isDeleting, isEditing, editTitle, editRef,
  onSelect, onDelete, onStar, onStartEdit, onEditChange, onSaveEdit, onCancelEdit
}: {
  session: Session
  isActive: boolean
  isDeleting: boolean
  isEditing: boolean
  editTitle: string
  editRef: React.RefObject<HTMLInputElement | null>
  onSelect: () => void
  onDelete: () => void
  onStar: () => void
  onStartEdit: () => void
  onEditChange: (v: string) => void
  onSaveEdit: () => void
  onCancelEdit: () => void
}): React.JSX.Element {
  const [hover, setHover] = useState(false)

  return (
    <button
      onClick={isEditing ? undefined : onSelect}
      onDoubleClick={onStartEdit}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      className={cn(
        'group flex w-full items-start gap-2 rounded-xl px-3 py-2 text-left transition-colors',
        isActive ? 'bg-white/10' : 'hover:bg-white/[0.06]'
      )}
    >
      {session.starred && (
        <Star className="mt-0.5 h-3 w-3 shrink-0 text-amber-400" strokeWidth={0} fill="currentColor" />
      )}
      <div className="min-w-0 flex-1">
        {isEditing ? (
          <input
            ref={editRef as React.RefObject<HTMLInputElement>}
            value={editTitle}
            onChange={(e) => onEditChange(e.target.value)}
            onBlur={onSaveEdit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSaveEdit()
              else if (e.key === 'Escape') onCancelEdit()
            }}
            className="w-full rounded border border-white/20 bg-black/30 px-1.5 py-0.5 text-xs text-white focus:border-white/50 focus:outline-none"
          />
        ) : (
          <>
            <p className={cn('truncate text-[13px] font-medium leading-tight', isActive ? 'text-[color:var(--accent)]' : 'text-white/80')}>
              {session.title}
            </p>
            {session.preview && (
              <p className="mt-0.5 truncate text-[11px] leading-tight text-white/30">
                {session.preview}
              </p>
            )}
          </>
        )}
      </div>
      {/* Hover actions */}
      {hover && !isEditing && !isDeleting && (
        <div className="flex shrink-0 items-center gap-0.5" onClick={(e) => e.stopPropagation()}>
          <button onClick={onStartEdit} className="rounded p-1 text-white/30 hover:bg-white/10 hover:text-white/70">
            <Pencil className="h-3 w-3" strokeWidth={1.75} />
          </button>
          <button onClick={onStar} className={cn('rounded p-1 hover:bg-white/10', session.starred ? 'text-amber-400' : 'text-white/30 hover:text-white/70')}>
            <Star className="h-3 w-3" strokeWidth={session.starred ? 0 : 1.75} fill={session.starred ? 'currentColor' : 'none'} />
          </button>
          <button onClick={onDelete} className="rounded p-1 text-white/30 hover:bg-white/10 hover:text-rose-400">
            <Trash2 className="h-3 w-3" strokeWidth={1.75} />
          </button>
        </div>
      )}
      {isDeleting && <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin text-white/30" />}
    </button>
  )
}
