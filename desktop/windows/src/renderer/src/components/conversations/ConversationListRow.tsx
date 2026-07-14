import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Loader2, Pencil, Star, Trash2 } from 'lucide-react'
import type { ConversationRow } from '../../lib/pageCache'
import type { ConversationFolder } from '../../../../shared/types'
import { isCloudBacked } from '../../lib/conversations/filtering'
import { MoveToFolderMenu } from './MoveToFolderMenu'

// Selected-row tint (Track 4 ruling — purple ports as-is).
const SELECTED_TINT: React.CSSProperties = {
  backgroundColor: 'rgba(139, 92, 246, 0.22)',
  borderColor: 'rgba(139, 92, 246, 0.4)'
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
  if (selectMode) {
    return (
      <button
        onClick={() => onToggleSelect(row.id)}
        style={selected ? SELECTED_TINT : undefined}
        className={`surface-card-interactive flex w-full items-center gap-3 p-3 text-left ${
          selected ? 'border' : ''
        }`}
      >
        <span
          className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors ${
            selected ? 'border-white/40 bg-white/25 text-white' : 'border-white/20 bg-transparent'
          }`}
        >
          {selected && <Check className="h-3.5 w-3.5" />}
        </span>
        <EmojiTile emoji={row.emoji} />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-text-primary">
            {row.title || <span className="italic text-text-tertiary">loading…</span>}
          </div>
          {row.subtitle && (
            <div className="mt-0.5 text-xs text-text-quaternary">{row.subtitle}</div>
          )}
        </div>
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
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-text-primary">
          {row.title || <span className="italic text-text-tertiary">loading…</span>}
        </div>
        {row.subtitle && <div className="mt-0.5 text-xs text-text-quaternary">{row.subtitle}</div>}
      </div>

      {/* Hover-revealed inline actions. */}
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
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
