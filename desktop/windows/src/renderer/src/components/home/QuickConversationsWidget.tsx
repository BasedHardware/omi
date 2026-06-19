import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { MessageSquare, ChevronRight } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { auth, onAuthStateChanged } from '../../lib/firebase'
import { cn } from '../../lib/utils'

type ConvSummary = {
  id: string
  title?: string | null
  created_at?: string
  structured?: { title?: string | null; emoji?: string | null } | null
}

function relTime(isoStr?: string): string {
  if (!isoStr) return ''
  const ts = new Date(isoStr).getTime()
  if (isNaN(ts)) return ''
  const diff = Date.now() - ts
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return new Date(isoStr).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

const MAX_SHOWN = 3

export function QuickConversationsWidget({
  onReady,
  className
}: {
  onReady?: () => void
  className?: string
}): React.JSX.Element | null {
  const [convs, setConvs] = useState<ConvSummary[] | null>(null)
  const { pathname } = useLocation()
  const readyFired = useRef(false)

  useEffect(() => {
    if (convs !== null && !readyFired.current) {
      readyFired.current = true
      onReady?.()
    }
  }, [convs, onReady])

  const [userId, setUserId] = useState<string | null>(auth.currentUser?.uid ?? null)
  useEffect(() => onAuthStateChanged(auth, (u) => setUserId(u?.uid ?? null)), [])

  const fetchConvs = useCallback((): (() => void) => {
    let cancelled = false
    omiApi
      .get('/v1/conversations', { params: { limit: 10, offset: 0 } })
      .then((res) => {
        const data = res.data as ConvSummary[] | { conversations?: ConvSummary[] }
        const list = Array.isArray(data) ? data : (data.conversations ?? [])
        if (!cancelled) setConvs(list.slice(0, MAX_SHOWN))
      })
      .catch(() => {
        if (!cancelled) setConvs((prev) => prev ?? [])
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!userId) return
    return fetchConvs()
  }, [userId, fetchConvs])

  useEffect(() => {
    if (pathname !== '/home') return
    return fetchConvs()
  }, [pathname, fetchConvs])

  // Still loading — withhold rendering so the parent can reveal all widgets together.
  if (!convs) return null

  const shown = convs.slice(0, MAX_SHOWN)

  return (
    <Link
      to="/conversations"
      className={cn(
        'group flex flex-col rounded-2xl border border-white/10 bg-[color:var(--surface)] p-4 transition-colors duration-200 hover:bg-[color:var(--nav-sel)]',
        className
      )}
    >
      <div className="flex items-center gap-3">
        <div className="glass-subtle flex h-9 w-9 shrink-0 items-center justify-center rounded-xl">
          <MessageSquare className="h-4 w-4 text-white/70" />
        </div>
        <div className="flex flex-1 items-center gap-1.5 text-sm font-medium text-white/85">
          Recent Conversations
        </div>
        <ChevronRight className="h-4 w-4 shrink-0 text-white/25 transition-colors group-hover:text-white/50" />
      </div>

      {shown.length === 0 ? (
        <p className="mt-3 text-[12px] text-white/35">
          No conversations yet — start recording to create one.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {shown.map((c) => {
            const title = c.structured?.title || c.title || 'Untitled'
            const emoji = c.structured?.emoji
            const time = relTime(c.created_at)
            return (
              <div key={c.id} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="truncate text-white/65">
                  {emoji ? `${emoji} ` : ''}
                  {title}
                </span>
                {time && <span className="shrink-0 text-white/35">{time}</span>}
              </div>
            )
          })}
        </div>
      )}
    </Link>
  )
}
