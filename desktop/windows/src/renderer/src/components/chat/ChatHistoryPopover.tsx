import { Plus, Search, Star, MessageSquare, AlertCircle } from 'lucide-react'
import type { UseChatSessions } from '../../hooks/useChatSessions'
import { HistorySessionRow } from './HistorySessionRow'
import { Spinner } from '../ui/Spinner'
import { cn } from '../../lib/utils'

// The chat-history popover body: a header (title + starred filter + "+"), a
// search field, then the loading / load-error / empty / date-grouped list. Ported
// from Mac's ChatHistoryPopover. Purely presentational over `useChatSessions` —
// the container owns the hook and pairs selection with useChat().switchThread.
//
// createError (a failed "+") renders as a small transient inline notice near the
// header — NEVER a body swap (that is what the list-load `error` state is for).

export function ChatHistoryPopover(props: {
  sessions: UseChatSessions
  currentThreadId: string | null
  onSelect: (id: string | null) => void
  onCreate: () => void
  // Delete is routed through the container (not called on the hook directly)
  // because deleting the ACTIVE session must also re-thread the engine back to
  // the default thread — see HubChatHeader.handleDelete.
  onDelete: (id: string) => void
}): React.JSX.Element {
  const { sessions: s, currentThreadId, onSelect, onCreate, onDelete } = props

  return (
    <div className="flex max-h-[min(70vh,480px)] flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-white/10 px-3 py-2.5">
        <span className="flex-1 text-[13px] font-semibold text-white">Chats</span>
        <button
          type="button"
          className={cn(
            'focus-ring rounded-md p-1.5 transition-colors',
            s.showStarredOnly
              ? 'bg-white/10 text-amber-300'
              : 'text-white/45 hover:bg-white/10 hover:text-white/80'
          )}
          title={s.showStarredOnly ? 'Show all chats' : 'Show starred only'}
          onClick={s.toggleStarredFilter}
        >
          <Star className="h-4 w-4" fill={s.showStarredOnly ? 'currentColor' : 'none'} />
        </button>
        <button
          type="button"
          className="focus-ring rounded-md p-1.5 text-white/60 transition-colors hover:bg-white/10 hover:text-white"
          title="New chat"
          onClick={onCreate}
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>

      {/* Transient create-error notice (never a list swap). */}
      {s.createError && (
        <div className="flex items-center gap-2 border-b border-white/10 bg-[var(--error)]/10 px-3 py-1.5 text-[12px] text-[var(--error)]">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          <span className="flex-1 truncate">{s.createError}</span>
          <button
            type="button"
            className="focus-ring rounded px-1 text-white/50 hover:text-white/80"
            onClick={s.clearCreateError}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Search */}
      <div className="relative px-3 py-2">
        <Search className="pointer-events-none absolute left-5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30" />
        <input
          value={s.searchQuery}
          onChange={(e) => s.setSearchQuery(e.target.value)}
          placeholder="Search chats"
          className="input-field h-8 w-full pl-7 text-[13px]"
        />
      </div>

      {/* Body */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {s.loading ? (
          <div className="flex items-center justify-center py-10">
            <Spinner />
          </div>
        ) : s.error ? (
          <div className="flex flex-col items-center gap-3 px-4 py-10 text-center">
            <AlertCircle className="h-6 w-6 text-white/30" />
            <p className="text-[13px] text-white/60">{s.error}</p>
            <button
              type="button"
              className="focus-ring rounded-md bg-white/10 px-3 py-1 text-[12px] text-white/80 hover:bg-white/15"
              onClick={s.retryLoad}
            >
              Retry
            </button>
          </div>
        ) : s.groupedSessions.length === 0 ? (
          <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
            <MessageSquare className="h-6 w-6 text-white/25" />
            <p className="text-[13px] text-white/50">
              {s.searchQuery.trim() || s.showStarredOnly ? 'No matching chats' : 'No chats yet'}
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3 pt-1">
            {s.groupedSessions.map((group) => (
              <div key={group.label} className="flex flex-col gap-0.5">
                <div className="px-2.5 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-wider text-white/30">
                  {group.label}
                </div>
                {group.sessions.map((session) => (
                  <HistorySessionRow
                    key={session.id}
                    session={session}
                    selected={session.id === currentThreadId}
                    onSelect={() => onSelect(session.id)}
                    onRename={(title) => void s.renameSession(session.id, title)}
                    onToggleStar={() => void s.toggleStar(session.id)}
                    onDelete={() => onDelete(session.id)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
