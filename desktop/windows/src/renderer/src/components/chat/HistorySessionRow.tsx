import { useEffect, useRef, useState } from 'react'
import { Star, Pencil, Trash2, Check, X } from 'lucide-react'
import type { ChatSession } from '../../../../shared/chatSessions'
import { toEpochMs } from '../../lib/chatSessionsView'
import { macPurple } from '../../lib/macPalette'
import { cn } from '../../lib/utils'

// One row in the chat-history popover: star, title (double-click to rename in
// place), preview + relative-date subtitle, and hover actions (rename/star/
// delete). The selected row is tinted with Mac's purplePrimary (the sanctioned
// INV-UI-1 exception, `macPurple` — NOT var(--accent)); everything else is
// neutral. Ported from Mac's ChatHistoryRow.

const MINUTE = 60_000
const HOUR = 3_600_000
const DAY = 86_400_000

/** Compact relative date for the subtitle: "now" / "5m" / "3h" / "2d" / a short
 *  month-day for anything older than a week. */
function formatRelativeDate(value: number | string, now = Date.now()): string {
  const ms = toEpochMs(value)
  if (!ms) return ''
  const diff = Math.max(0, now - ms)
  if (diff < MINUTE) return 'now'
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)}m`
  if (diff < DAY) return `${Math.floor(diff / HOUR)}h`
  if (diff < 7 * DAY) return `${Math.floor(diff / DAY)}d`
  return new Date(ms).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function HistorySessionRow(props: {
  session: ChatSession
  selected: boolean
  onSelect: () => void
  onRename: (title: string) => void
  onToggleStar: () => void
  onDelete: () => void
}): React.JSX.Element {
  const { session, selected, onSelect, onRename, onToggleStar, onDelete } = props
  const [renaming, setRenaming] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [draft, setDraft] = useState(session.title ?? '')
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (renaming) inputRef.current?.select()
  }, [renaming])

  const beginRename = (): void => {
    setDraft(session.title ?? '')
    setRenaming(true)
  }
  const commitRename = (): void => {
    setRenaming(false)
    onRename(draft) // hook no-ops on empty/unchanged
  }
  const cancelRename = (): void => {
    setRenaming(false)
    setDraft(session.title ?? '')
  }

  const title = session.title?.trim() || 'New Chat'
  const relative = formatRelativeDate(session.updatedAt)
  const subtitleParts = [session.preview?.trim(), relative].filter(Boolean)

  return (
    <div
      className={cn(
        'group relative flex cursor-pointer items-start gap-2 rounded-[10px] px-2.5 py-2 transition-colors',
        selected ? 'text-white' : 'text-white/80 hover:bg-white/5'
      )}
      style={selected ? { background: macPurple('0.16') } : undefined}
      onClick={renaming ? undefined : onSelect}
    >
      {/* Star toggle — filled when starred; otherwise a faint outline that fills in on hover. */}
      <button
        type="button"
        className={cn(
          'focus-ring mt-0.5 shrink-0 rounded p-0.5 transition-colors',
          session.starred ? 'text-amber-300' : 'text-white/30 hover:text-white/60'
        )}
        title={session.starred ? 'Unstar' : 'Star'}
        onClick={(e) => {
          e.stopPropagation()
          onToggleStar()
        }}
      >
        <Star className="h-3.5 w-3.5" fill={session.starred ? 'currentColor' : 'none'} />
      </button>

      <div className="min-w-0 flex-1">
        {renaming ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename()
              else if (e.key === 'Escape') cancelRename()
            }}
            onBlur={commitRename}
            maxLength={120}
            className="input-field h-7 w-full text-[13px]"
          />
        ) : (
          <>
            <div
              className="truncate text-[13px] font-medium"
              onDoubleClick={(e) => {
                e.stopPropagation()
                beginRename()
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

      {/* Inline delete confirm — a destructive action with no undo, so the trash
          click arms a check/cancel pair rather than deleting on the first click.
          Kept in-row (not a Modal) so it never fights the Popover's dismiss. */}
      {!renaming && confirmingDelete && (
        <div className="flex shrink-0 items-center gap-0.5">
          <span className="mr-1 text-[11px] text-white/50">Delete?</span>
          <button
            type="button"
            className="focus-ring rounded p-1 text-[var(--error)] hover:bg-[var(--error)]/20"
            title="Confirm delete"
            onClick={(e) => {
              e.stopPropagation()
              setConfirmingDelete(false)
              onDelete()
            }}
          >
            <Check className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="focus-ring rounded p-1 text-white/40 hover:bg-white/10 hover:text-white/80"
            title="Cancel"
            onClick={(e) => {
              e.stopPropagation()
              setConfirmingDelete(false)
            }}
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Hover actions — hidden until row hover (or focus-within for keyboard). */}
      {!renaming && !confirmingDelete && (
        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          <button
            type="button"
            className="focus-ring rounded p-1 text-white/40 hover:bg-white/10 hover:text-white/80"
            title="Rename"
            onClick={(e) => {
              e.stopPropagation()
              beginRename()
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            className="focus-ring rounded p-1 text-white/40 hover:bg-[var(--error)]/20 hover:text-[var(--error)]"
            title="Delete"
            onClick={(e) => {
              e.stopPropagation()
              setConfirmingDelete(true)
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}
