'use client';

import { useEffect, useRef, useState } from 'react';
import { Check, Pencil, Star, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { toEpochMs } from '@/lib/chatSessionsView';
import type { ChatSession } from '@/types/chatSessions';

/**
 * One row in the chat-history list, ported from the Electron desktop app
 * (`desktop/windows/src/renderer/src/components/chat/HistorySessionRow.tsx`):
 * star, title (double-click to rename in place), preview + relative-date
 * subtitle, and hover actions with an inline delete confirm.
 *
 * One deliberate difference: desktop tints the selected row with `macPurple`,
 * a sanctioned INV-UI-1 exception scoped to `desktop/windows`. The brand
 * ratchet does cover `web/`, so the selection here is neutral.
 */

const MINUTE = 60_000;
const HOUR = 3_600_000;
const DAY = 86_400_000;

/**
 * Compact relative date for the subtitle: "now" / "5m" / "3h" / "2d", and a
 * short month-day for anything older than a week.
 */
export function formatRelativeDate(value: number | string, now = Date.now()): string {
  const ms = toEpochMs(value);
  if (!ms) return '';
  const diff = Math.max(0, now - ms);
  if (diff < MINUTE) return 'now';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`;
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`;
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d`;
  return new Date(ms).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

interface HistorySessionRowProps {
  session: ChatSession;
  selected: boolean;
  onSelect: () => void;
  onRename: (title: string) => void;
  onToggleStar: () => void;
  onDelete: () => void;
}

export function HistorySessionRow({
  session,
  selected,
  onSelect,
  onRename,
  onToggleStar,
  onDelete,
}: HistorySessionRowProps) {
  const [renaming, setRenaming] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [draft, setDraft] = useState(session.title ?? '');
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) inputRef.current?.select();
  }, [renaming]);

  const beginRename = () => {
    setDraft(session.title ?? '');
    setRenaming(true);
  };
  const commitRename = () => {
    setRenaming(false);
    onRename(draft); // the hook no-ops on empty/unchanged
  };
  const cancelRename = () => {
    setRenaming(false);
    setDraft(session.title ?? '');
  };

  const title = session.title?.trim() || 'New Chat';
  const relative = formatRelativeDate(session.updatedAt);
  const subtitleParts = [session.preview?.trim(), relative].filter(Boolean);

  return (
    <div
      role="option"
      aria-selected={selected}
      className={cn(
        'group relative flex cursor-pointer items-start gap-2 rounded-[10px] px-2.5 py-2 transition-colors',
        selected ? 'bg-white/10 text-white' : 'text-white/80 hover:bg-white/5',
      )}
      onClick={renaming ? undefined : onSelect}
    >
      <button
        type="button"
        className={cn(
          'mt-0.5 shrink-0 rounded p-0.5 transition-colors',
          session.starred ? 'text-amber-300' : 'text-white/30 hover:text-white/60',
        )}
        title={session.starred ? 'Unstar' : 'Star'}
        aria-label={`${session.starred ? 'Unstar' : 'Star'} ${title}`}
        onClick={(event) => {
          event.stopPropagation();
          onToggleStar();
        }}
      >
        <Star className="h-3.5 w-3.5" fill={session.starred ? 'currentColor' : 'none'} />
      </button>

      <div className="min-w-0 flex-1">
        {renaming ? (
          <input
            ref={inputRef}
            value={draft}
            aria-label={`Rename ${title}`}
            onChange={(event) => setDraft(event.target.value)}
            onClick={(event) => event.stopPropagation()}
            onKeyDown={(event) => {
              if (event.key === 'Enter') commitRename();
              else if (event.key === 'Escape') cancelRename();
            }}
            onBlur={commitRename}
            maxLength={120}
            className="h-7 w-full rounded-md border border-white/20 bg-black/30 px-2 text-[13px] text-white focus:border-white/50 focus:outline-none"
          />
        ) : (
          <>
            <div
              className="truncate text-[13px] font-medium"
              onDoubleClick={(event) => {
                event.stopPropagation();
                beginRename();
              }}
            >
              {title}
            </div>
            {subtitleParts.length > 0 && (
              <div className="mt-0.5 truncate text-[11px] text-white/40">
                {subtitleParts.join(' · ')}
              </div>
            )}
          </>
        )}
      </div>

      {/* A delete has no undo, so the trash click arms a confirm pair rather
          than deleting outright. */}
      {!renaming && confirmingDelete && (
        <div className="flex shrink-0 items-center gap-0.5">
          <span className="mr-1 text-[11px] text-white/50">Delete?</span>
          <button
            type="button"
            className="rounded p-1 text-error hover:bg-error/20"
            title="Confirm delete"
            aria-label={`Confirm delete ${title}`}
            onClick={(event) => {
              event.stopPropagation();
              setConfirmingDelete(false);
              onDelete();
            }}
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="rounded p-1 text-white/40 hover:bg-white/10 hover:text-white/80"
            title="Cancel"
            aria-label="Cancel delete"
            onClick={(event) => {
              event.stopPropagation();
              setConfirmingDelete(false);
            }}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {!renaming && !confirmingDelete && (
        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          <button
            type="button"
            className="rounded p-1 text-white/40 hover:bg-white/10 hover:text-white/80"
            title="Rename"
            aria-label={`Rename chat ${title}`}
            onClick={(event) => {
              event.stopPropagation();
              beginRename();
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="rounded p-1 text-white/40 hover:bg-error/20 hover:text-error"
            title="Delete"
            aria-label={`Delete chat ${title}`}
            onClick={(event) => {
              event.stopPropagation();
              setConfirmingDelete(true);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
}
