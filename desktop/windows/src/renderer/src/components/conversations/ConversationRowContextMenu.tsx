import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { ChevronRight, Copy, FolderInput, Link2, Pencil, Trash2 } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import type { ConversationRow } from '../../lib/pageCache'
import { isCloudBacked } from '../../lib/conversations/filtering'
import { getConversationShareLink } from '../../lib/conversations/mutations'
import { loadRowTranscript } from '../../lib/conversations/transcript'
import { toast } from '../../lib/toast'
import { FolderPickerList } from './FolderPickerList'

const EDGE = 8 // px minimum distance from the viewport edge
const GAP = 4 // px between the parent item and the folder submenu
const MENU_WIDTH = 224 // px — must match the w-56 below
const SUB_WIDTH = 208 // px — must match the w-52 below
const SUB_MAX_HEIGHT = 240 // px — vertical clearance kept for the max-h-72 submenu

// Right-click context menu for a conversation row — the Windows-idiomatic
// affordance (File Explorer et al.) mirroring the macOS row's `.contextMenu`.
// It is ADDITIVE: the hover-icon buttons on the row stay exactly as they are.
//
// Modeled on MoveToFolderMenu: a hand-rolled menu PORTALED to <body>, positioned
// at the cursor with viewport-edge clamping, closed by a full-screen backdrop,
// Escape, or choosing an item. `surface-panel` is opaque so nothing shows through.
//
// Item order matches Mac (ConversationRowView.swift): Copy Transcript, Copy Link,
// divider, Edit Title, Move to Folder ▸, divider, Delete. isCloudBacked(row) gates
// the two backend-id actions (Copy Link, Move to Folder) exactly like the row's
// hover buttons — a local-only row omits them rather than showing a broken action.
export function ConversationRowContextMenu({
  row,
  folders,
  position,
  onClose,
  onEditTitle,
  onMoveToFolder,
  onDelete
}: {
  row: ConversationRow
  folders: ConversationFolder[]
  position: { x: number; y: number }
  onClose: () => void
  onEditTitle: () => void
  onMoveToFolder: (folderId: string | null) => void
  onDelete: () => void
}): React.JSX.Element {
  const cloud = isCloudBacked(row)
  const panelRef = useRef<HTMLDivElement>(null)
  const moveItemRef = useRef<HTMLButtonElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)
  const [submenuOpen, setSubmenuOpen] = useState(false)
  const [subPos, setSubPos] = useState<{ top: number; left: number } | null>(null)
  const closeSubmenu = (): void => setSubmenuOpen(false)

  // Clamp the menu to the viewport from the cursor point. Runs before paint so
  // the panel never flashes at an off-screen position.
  useLayoutEffect(() => {
    const panel = panelRef.current
    if (!panel) return
    const w = panel.offsetWidth || MENU_WIDTH
    const h = panel.offsetHeight
    const left = Math.max(EDGE, Math.min(position.x, window.innerWidth - w - EDGE))
    const top = Math.max(EDGE, Math.min(position.y, window.innerHeight - h - EDGE))
    setPos({ top, left })
  }, [position.x, position.y])

  // Place the folder submenu beside the "Move to Folder" item, flipping to its
  // left when it would overflow the right edge.
  useLayoutEffect(() => {
    if (!submenuOpen) return
    const item = moveItemRef.current
    if (!item) return
    const r = item.getBoundingClientRect()
    const toRight = r.right + GAP
    const left =
      toRight + SUB_WIDTH > window.innerWidth - EDGE
        ? Math.max(EDGE, r.left - GAP - SUB_WIDTH)
        : toRight
    const top = Math.max(EDGE, Math.min(r.top, window.innerHeight - EDGE - SUB_MAX_HEIGHT))
    setSubPos({ top, left })
  }, [submenuOpen, folders.length])

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Copy actions fire-and-forget: close the menu first (so it can't linger over
  // the async work), then copy and confirm via toast. Mac copies silently; a
  // toast is the Windows-idiomatic confirmation now that the menu is gone.
  const copyToClipboard = (label: string, load: () => Promise<string>): void => {
    onClose()
    void (async (): Promise<void> => {
      try {
        await navigator.clipboard.writeText(await load())
        toast(`${label} copied`, { tone: 'success' })
      } catch (e) {
        toast(`Could not copy ${label.toLowerCase()}`, {
          tone: 'error',
          body: (e as Error).message
        })
      }
    })()
  }

  const chooseFolder = (folderId: string | null): void => {
    onClose()
    onMoveToFolder(folderId)
  }

  // Shared item chrome; `danger` swaps the hover text color for Delete.
  const itemClass = (variant: 'default' | 'danger' = 'default'): string =>
    `flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-white/80 transition-colors hover:bg-white/10 ${
      variant === 'danger' ? 'hover:text-red-300' : 'hover:text-white'
    }`
  const divider = <div className="my-1 border-t border-white/10" />

  return createPortal(
    <>
      {/* Backdrop: a click (or a second right-click) anywhere dismisses. */}
      <div
        className="fixed inset-0 z-[190]"
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onClose()
        }}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          onClose()
        }}
      />

      <div
        ref={panelRef}
        role="menu"
        aria-label="Conversation actions"
        className="surface-panel fixed z-[200] w-56 p-1.5"
        style={{
          top: pos?.top ?? 0,
          left: pos?.left ?? 0,
          visibility: pos ? 'visible' : 'hidden'
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          role="menuitem"
          onMouseEnter={closeSubmenu}
          onClick={() => copyToClipboard('Transcript', () => loadRowTranscript(row))}
          className={itemClass()}
        >
          <Copy className="h-4 w-4 shrink-0 text-white/55" />
          Copy Transcript
        </button>

        {cloud && (
          <button
            role="menuitem"
            onMouseEnter={closeSubmenu}
            onClick={() => copyToClipboard('Link', () => getConversationShareLink(row.id))}
            className={itemClass()}
          >
            <Link2 className="h-4 w-4 shrink-0 text-white/55" />
            Copy Link
          </button>
        )}

        {divider}

        <button
          role="menuitem"
          onMouseEnter={closeSubmenu}
          onClick={() => {
            onClose()
            onEditTitle()
          }}
          className={itemClass()}
        >
          <Pencil className="h-4 w-4 shrink-0 text-white/55" />
          Edit Title
        </button>

        {cloud && (
          <button
            ref={moveItemRef}
            role="menuitem"
            aria-haspopup="menu"
            aria-expanded={submenuOpen}
            onMouseEnter={() => setSubmenuOpen(true)}
            onClick={() => setSubmenuOpen((o) => !o)}
            className={itemClass()}
          >
            <FolderInput className="h-4 w-4 shrink-0 text-white/55" />
            <span className="flex-1">Move to Folder</span>
            <ChevronRight className="h-4 w-4 shrink-0 text-white/45" />
          </button>
        )}

        {divider}

        <button
          role="menuitem"
          onMouseEnter={closeSubmenu}
          onClick={() => {
            onClose()
            onDelete()
          }}
          className={itemClass('danger')}
        >
          <Trash2 className="h-4 w-4 shrink-0 text-white/55" />
          Delete
        </button>
      </div>

      {/* Folder submenu (fixed-position sibling — no ancestor clips it). Kept open
          while the pointer is on the parent item or over the submenu itself;
          entering any sibling item closes it (no timers). */}
      {cloud && submenuOpen && (
        <div
          role="menu"
          aria-label="Move to folder"
          className="surface-panel fixed z-[200] max-h-72 w-52 overflow-y-auto p-1.5"
          style={{
            top: subPos?.top ?? 0,
            left: subPos?.left ?? 0,
            visibility: subPos ? 'visible' : 'hidden'
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <FolderPickerList
            folders={folders}
            currentFolderId={row.folderId}
            onChoose={chooseFolder}
          />
        </div>
      )}
    </>,
    document.body
  )
}
