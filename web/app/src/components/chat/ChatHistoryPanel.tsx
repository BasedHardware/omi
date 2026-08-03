'use client';

import { useMemo, useState } from 'react';
import { MessageSquarePlus, Search } from 'lucide-react';
import { useChatSessions } from '@/hooks/useChatSessions';
import { deleteAndRethread } from '@/lib/chatSessionDelete';
import { filterSessions, groupSessionsByDate } from '@/lib/chatSessionsView';
import { cn } from '@/lib/utils';
import { HistorySessionRow } from './HistorySessionRow';

interface ChatHistoryPanelProps {
  /** null means the default shared thread every client reads. */
  activeSessionId: string | null;
  onSelectSession: (id: string | null) => void;
}

/**
 * Chat history: search, date-bucketed sessions, and per-row rename/star/delete.
 * Ported from the Electron desktop app's history popover, using the same
 * `filterSessions`/`groupSessionsByDate` helpers so the buckets match.
 */
export function ChatHistoryPanel({
  activeSessionId,
  onSelectSession,
}: ChatHistoryPanelProps) {
  const {
    sessions,
    loading,
    error,
    addSession,
    renameSession,
    toggleStar,
    removeSession,
  } = useChatSessions();
  const [query, setQuery] = useState('');

  const groups = useMemo(
    () => groupSessionsByDate(filterSessions(sessions, query)),
    [sessions, query],
  );

  const startNewChat = async () => {
    const created = await addSession();
    if (created) onSelectSession(created.id);
  };

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-stroke bg-bg-secondary">
      <div className="flex items-center gap-2 px-3 py-3">
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-white/30" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search chats"
            aria-label="Search chats"
            className="h-8 w-full rounded-md border border-white/10 bg-black/30 pl-8 pr-2 text-[13px] text-white placeholder:text-white/30 focus:border-white/40 focus:outline-none"
          />
        </div>
        <button
          type="button"
          onClick={() => void startNewChat()}
          title="New chat"
          aria-label="New chat"
          className="rounded-md p-1.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white"
        >
          <MessageSquarePlus className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3" role="listbox">
        <button
          type="button"
          onClick={() => onSelectSession(null)}
          aria-selected={activeSessionId === null}
          role="option"
          className={cn(
            'mb-1 flex w-full items-center rounded-[10px] px-2.5 py-2 text-left text-[13px] font-medium transition-colors',
            activeSessionId === null
              ? 'bg-white/10 text-white'
              : 'text-white/80 hover:bg-white/5',
          )}
        >
          Main chat
        </button>

        {error && <p className="px-2.5 py-2 text-[11px] text-error">{error}</p>}

        {loading && sessions.length === 0 ? (
          <div className="space-y-1 px-1">
            {[0, 1, 2].map((key) => (
              <div key={key} className="h-11 animate-pulse rounded-[10px] bg-white/5" />
            ))}
          </div>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mt-3 first:mt-1">
              <div className="px-2.5 pb-1 text-[10px] font-semibold uppercase tracking-wide text-white/30">
                {group.label}
              </div>
              {group.sessions.map((session) => (
                <HistorySessionRow
                  key={session.id}
                  session={session}
                  selected={session.id === activeSessionId}
                  onSelect={() => onSelectSession(session.id)}
                  onRename={(title) => void renameSession(session.id, title)}
                  onToggleStar={() => void toggleStar(session.id)}
                  onDelete={() =>
                    void deleteAndRethread(
                      removeSession,
                      activeSessionId,
                      onSelectSession,
                      session.id,
                    )
                  }
                />
              ))}
            </div>
          ))
        )}

        {!loading && sessions.length > 0 && groups.length === 0 && (
          <p className="px-2.5 py-4 text-[11px] text-white/40">
            No chats match “{query}”.
          </p>
        )}
      </div>
    </aside>
  );
}
