import { useEffect, useState } from 'react'
import { ChevronRight, MessageSquare } from 'lucide-react'
import { Link } from 'react-router-dom'
import {
  conversationsCache,
  subscribeConversations,
  type ConversationRow
} from '../../lib/pageCache'
import { loadConversations } from '../../lib/conversationLoader'

export function ConversationRail(): React.JSX.Element {
  const [rows, setRows] = useState<ConversationRow[]>(conversationsCache.rows ?? [])

  useEffect(() => {
    let active = true
    void loadConversations().then((nextRows) => {
      if (active) setRows(nextRows)
    })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    const unsubscribe = subscribeConversations(() => {
      void loadConversations(true).then((nextRows) => {
        if (active) setRows(nextRows)
      })
    })
    return () => {
      active = false
      unsubscribe()
    }
  }, [])

  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-white/10 bg-black/10 md:flex">
      <div className="flex items-center justify-between px-4 py-4">
        <div className="flex items-center gap-2 text-sm font-medium text-white/85">
          <MessageSquare className="h-4 w-4 text-white/55" />
          Conversations
        </div>
        <Link
          to="/conversations"
          aria-label="View all conversations"
          className="rounded-lg p-1 text-white/40 transition-colors hover:bg-white/[0.06] hover:text-white/80"
        >
          <ChevronRight className="h-4 w-4" />
        </Link>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {rows.slice(0, 8).map((row) => (
          <Link
            key={row.id}
            to={`/conversations/${row.id}`}
            className="mb-1 block rounded-xl px-3 py-2 text-sm transition-colors hover:bg-white/[0.06]"
          >
            <div className="truncate text-white/75">
              {row.emoji ? `${row.emoji} ` : ''}
              {row.title || 'loading…'}
            </div>
            <div className="mt-0.5 truncate text-xs text-white/35">
              {row.subtitle || row.preview}
            </div>
          </Link>
        ))}
        {rows.length === 0 && (
          <p className="px-3 py-2 text-xs leading-relaxed text-white/35">
            Your recent chats will appear here.
          </p>
        )}
      </div>
      <Link
        to="/conversations"
        className="mx-2 mb-3 flex items-center justify-between rounded-xl px-3 py-2 text-xs text-white/50 transition-colors hover:bg-white/[0.06] hover:text-white/80"
      >
        View all
        <ChevronRight className="h-3.5 w-3.5" />
      </Link>
    </aside>
  )
}
