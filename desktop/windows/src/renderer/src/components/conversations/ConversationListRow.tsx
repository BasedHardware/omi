import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Loader2, Pencil, Star, Trash2 } from 'lucide-react'
import type { ConversationRow } from '../../lib/pageCache'
import type { ConversationFolder } from '../../../../shared/types'
import { isCloudBacked } from '../../lib/conversations/filtering'
import { macPurple } from '../../lib/macPalette'
import { MoveToFolderMenu } from './MoveToFolderMenu'

// Selected-row tint (Track 4 ruling — purple ports as-is). Applied inline so it
// beats the component-layer surface background AND the hover background, i.e. a
// selected row stays unmistakably purple whether or not the pointer is on it.
const SELECTED_TINT: React.CSSProperties = {
  backgroundColor: macPurple('0.22'),
  borderColor: macPurple('0.55')
}

// Placeholder previews minted upstream when a conversation has no text yet —
// never worth a line of its own.
const PREVIEW_PLACEHOLDERS = new Set(['(no transcript)', '(empty chat)', '(empty transcript)'])

function previewOf(row: ConversationRow): string | null {
  const p = row.preview?.trim()
  if (!p || PREVIEW_PLACEHOLDERS.has(p)) return null
  return p
}

/** The 36×36 topic-emoji tile. Falls back to 💬 (Mac parity). */
function EmojiTile({ emoji }: { emoji?: string }): React.JSX.Element {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-bg-raised text-lg leading-none">
      {emoji || '💬'}
    </span>
  )
}

// Right-hand sync badge (unchanged semantics from the old list): local recordings
// surface their outbox state; cloud/chat rows show their own marker.
function SyncBadge({
  r,
  onRetry
}: {
  r: ConversationRow
  onRetry?: (id: string) => void
}): React.JSX.Element | null {
  if (r.localKind === 'chat') return <span className="badge shrink-0">Chat</span>
  if (r.source !== 'local') return null
  if (r.sync === 'pending') return <span className="badge shrink-0">Sync pending</span>
  if (r.sync === 'failed') {
    return (
      <span className="flex shrink-0 items-center gap-1.5">
        <span className="badge-warning">Sync failed</span>
        {onRetry && (
          <button
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              onRetry(r.id)
            }}
            className="text-xs font-medium text-white/70 transition-colors hover:text-white"
          >
            Retry
          </button>
        )}
      </span>
    )
  }
  return <span className="badge-warning shrink-0">Not synced</span>
}

/** Title, single-line overview snippet (when the conversation has one), timestamp. */
function RowBody({ row }: { row: ConversationRow }): React.JSX.Element {
  const preview = previewOf(row)
  return (
    <div className="min-w-0 flex-1">
      <div className="truncate text-sm font-medium text-text-primary">
        {row.title || <span className="italic text-text-tertiary">loading…</span>}
      </div>
      {preview && <div className="mt-0.5 truncate text-xs text-text-tertiary">{preview}</div>}
      {row.subtitle && <div className="mt-0.5 text-xs text-text-quaternary">{row.subtitle}</div>}
    </div>
  )
}

export function ConversationListRow({
  row,
  folders,
  selectMode,
  selected,
  onToggleSelect,
  onStar,
  onMoveToFolder,
  onRename,
  onDelete,
  onRetrySync
}: {
  row: ConversationRow
  folders: ConversationFolder[]
  selectMode: boolean
  selected: boolean
  onToggleSelect: (id: string) => void
  onStar: (row: ConversationRow, next: boolean) => void
  onMoveToFolder: (row: ConversationRow, folderId: string | null) => void
  onRename: (row: ConversationRow, title: string) => void
  onDelete: (row: ConversationRow) => void
  onRetrySync?: (id: string) => void
}): React.JSX.Element {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(row.title)
  const cloud = isCloudBacked(row)

  // --- Optimistic "Processing" placeholder (no server doc yet). ---
  if (row.pending) {
    return (
      <div className="surface-card flex cursor-default items-center gap-3 p-3 opacity-70">
        <EmojiTile emoji={row.emoji} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-text-primary">
            {row.title || <span className="italic text-text-tertiary">loading…</span>}
          </div>
          {row.subtitle && (
            <div className="mt-0.5 text-xs text-text-quaternary">{row.subtitle}</div>
          )}
        </div>
        <span className="badge flex shrink-0 items-center gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin" aria-hidden />
          Processing
        </span>
      </div>
    )
  }

  // --- Inline rename (replaces the Link so a click doesn't navigate). ---
  if (editing) {
    const commit = (): void => {
      const next = draft.trim()
      if (next && next !== row.title) onRename(row, next)
      setEditing(false)
    }
    return (
      <div className="surface-card flex items-center gap-3 p-3">
        <EmojiTile emoji={row.emoji} />
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commit()
            if (e.key === 'Escape') {
              setDraft(row.title)
              setEditing(false)
            }
          }}
          maxLength={120}
          className="input-field flex-1 py-1.5 text-sm"
        />
      </div>
    )
  }

  // --- Select mode (checkbox + purple selected tint). ---
  // Deliberately NOT .surface-card-interactive: its `transition-all` faded the
  // selected tint in over 200ms (and its hover fill is a dark wash that reads as
  // "highlighted" too). Here selection paints instantly and unmistakably — purple
  // fill + purple border + filled checkbox — while hover is a faint white lift
  // that can never be mistaken for it.
  if (selectMode) {
    return (
      <button
        onClick={() => onToggleSelect(row.id)}
        aria-pressed={selected}
        style={selected ? SELECTED_TINT : undefined}
        className={`surface-card flex w-full items-center gap-3 border p-3 text-left ${
          selected ? '' : 'hover:bg-white/[0.06]'
        }`}
      >
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
            selected ? 'border-white/50 bg-white/30 text-white' : 'border-white/25 bg-transparent'
          }`}
        >
          {selected && <Check className="h-3.5 w-3.5" />}
        </span>
        <EmojiTile emoji={row.emoji} />
        <RowBody row={row} />
        <SyncBadge r={row} />
      </button>
    )
  }

  // --- Normal row: Link nav + hover actions + trailing star. ---
  return (
    <Link
      to={`/conversations/${row.id}`}
      className="group surface-card-interactive flex items-center gap-3 p-3"
    >
      <EmojiTile emoji={row.emoji} />
      <RowBody row={row} />

      {/* Hover-revealed inline actions. `focus-within` keeps them painted while a
          menu they own is open (the move-to-folder trigger holds focus), so the
          group can't fade out from under an open dropdown. */}
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            setDraft(row.title)
            setEditing(true)
          }}
          aria-label="Rename"
          className="rounded-md p-1.5 text-white/45 transition-colors hover:bg-white/10 hover:text-white"
        >
          <Pencil className="h-4 w-4" />
        </button>
        {cloud && (
          <MoveToFolderMenu
            folders={folders}
            currentFolderId={row.folderId}
            onMove={(folderId) => onMoveToFolder(row, folderId)}
          />
        )}
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onDelete(row)
          }}
          aria-label="Delete"
          className="rounded-md p-1.5 text-white/45 transition-colors hover:bg-white/10 hover:text-red-300"
        >
          <Trash2 className="h-4 w-4" />
        </button>
      </div>

      <SyncBadge r={row} onRetry={onRetrySync} />

      {/* Trailing star (cloud conversations only — backend-backed). */}
      {cloud && (
        <button
          onClick={(e) => {
            e.preventDefault()
            e.stopPropagation()
            onStar(row, !row.starred)
          }}
          aria-label={row.starred ? 'Unstar' : 'Star'}
          className="shrink-0 rounded-md p-1.5 transition-colors hover:bg-white/10"
        >
          <Star
            className={`h-4 w-4 ${row.starred ? 'text-amber-400' : 'text-white/35 hover:text-white/70'}`}
            fill={row.starred ? 'currentColor' : 'none'}
          />
        </button>
      )}
    </Link>
  )
}
