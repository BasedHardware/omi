import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Check, FolderInput, FolderMinus } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import { DEFAULT_FOLDER_COLOR } from './folderColors'

const MENU_WIDTH = 208 // px — must match the w-52 below
const GAP = 6 // px between the trigger and the panel
const EDGE = 8 // px minimum distance from the viewport edge

// Row action: assign a conversation to a folder (or remove it). Encapsulated
// trigger + dropdown; the trigger is a small icon button revealed on row hover.
//
// The panel is PORTALED to <body> and positioned from the trigger's viewport
// rect. It used to be an absolutely-positioned sibling inside the row's hover
// action group — which is an `opacity-0 group-hover:opacity-100` container — so
// the moment the pointer left the row the *open* menu faded out with it (still
// mounted, still swallowing clicks) and painted half-transparent over the rows
// behind it. A portal has no such ancestor: it is always fully opaque, never
// clipped by a row, and always on top.
export function MoveToFolderMenu({
  folders,
  currentFolderId,
  onMove
}: {
  folders: ConversationFolder[]
  currentFolderId: string | null | undefined
  onMove: (folderId: string | null) => void
}): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null)

  const choose = (folderId: string | null): void => {
    setOpen(false)
    onMove(folderId)
  }

  // Place the panel under the trigger (flipping above when it would overflow the
  // bottom). Runs before paint, so the panel never shows at a stale position.
  useLayoutEffect(() => {
    if (!open) return
    const place = (): void => {
      const trigger = triggerRef.current
      if (!trigger) return
      const r = trigger.getBoundingClientRect()
      const height = panelRef.current?.offsetHeight ?? 0
      const below = r.bottom + GAP
      const top =
        below + height > window.innerHeight - EDGE ? Math.max(EDGE, r.top - GAP - height) : below
      const left = Math.min(
        Math.max(EDGE, r.right - MENU_WIDTH),
        Math.max(EDGE, window.innerWidth - MENU_WIDTH - EDGE)
      )
      setPos({ top, left })
    }
    place()
    // Keep it pinned to the trigger while the list scrolls / the window resizes.
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, folders.length, currentFolderId])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  return (
    <>
      <button
        ref={triggerRef}
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          // Drop any stale placement so a re-open never paints at the old anchor.
          setPos(null)
          setOpen((o) => !o)
        }}
        aria-label="Move to folder"
        aria-expanded={open}
        className="rounded-md p-1.5 text-white/45 transition-colors hover:bg-white/10 hover:text-white"
      >
        <FolderInput className="h-4 w-4" />
      </button>

      {open &&
        createPortal(
          <>
            <div
              className="fixed inset-0 z-[190]"
              onClick={(e) => {
                e.preventDefault()
                e.stopPropagation()
                setOpen(false)
              }}
            />
            <div
              ref={panelRef}
              role="menu"
              aria-label="Move to folder"
              // Opaque raised panel (surface-panel = --bg-tertiary, no alpha) so
              // nothing behind it shows through.
              className="surface-panel fixed z-[200] max-h-72 w-52 overflow-y-auto p-1.5"
              style={{
                top: pos?.top ?? 0,
                left: pos?.left ?? 0,
                visibility: pos ? 'visible' : 'hidden'
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {folders.length === 0 && (
                <div className="px-2.5 py-2 text-xs text-white/45">No folders yet</div>
              )}
              {folders.map((f) => (
                <button
                  key={f.id}
                  role="menuitem"
                  onClick={(e) => {
                    e.stopPropagation()
                    choose(f.id)
                  }}
                  className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-white/80 transition-colors hover:bg-white/10 hover:text-white"
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: f.color ?? DEFAULT_FOLDER_COLOR }}
                  />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  {currentFolderId === f.id && (
                    <Check className="h-3.5 w-3.5 shrink-0 text-white" />
                  )}
                </button>
              ))}
              {currentFolderId != null && (
                <div className="mt-1.5 border-t border-white/10 pt-1.5">
                  <button
                    role="menuitem"
                    onClick={(e) => {
                      e.stopPropagation()
                      choose(null)
                    }}
                    className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-white/60 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    <FolderMinus className="h-3.5 w-3.5 shrink-0" />
                    Remove from folder
                  </button>
                </div>
              )}
            </div>
          </>,
          document.body
        )}
    </>
  )
}
