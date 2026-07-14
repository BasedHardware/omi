import { useState } from 'react'
import { Check, FolderInput, FolderMinus } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import { DEFAULT_FOLDER_COLOR } from './folderColors'

// Row action: assign a conversation to a folder (or remove it). Encapsulated
// trigger + dropdown; the trigger is a small icon button revealed on row hover.
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

  const choose = (folderId: string | null): void => {
    setOpen(false)
    onMove(folderId)
  }

  return (
    <div className="relative">
      <button
        onClick={(e) => {
          e.preventDefault()
          e.stopPropagation()
          setOpen((o) => !o)
        }}
        aria-label="Move to folder"
        className="rounded-md p-1.5 text-white/45 transition-colors hover:bg-white/10 hover:text-white"
      >
        <FolderInput className="h-4 w-4" />
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-[90]"
            onClick={(e) => {
              e.preventDefault()
              e.stopPropagation()
              setOpen(false)
            }}
          />
          <div
            className="surface-panel absolute right-0 z-[100] mt-1 max-h-64 w-52 overflow-y-auto p-1.5"
            onClick={(e) => e.preventDefault()}
          >
            {folders.length === 0 && (
              <div className="px-2.5 py-2 text-xs text-white/45">No folders yet</div>
            )}
            {folders.map((f) => (
              <button
                key={f.id}
                onClick={(e) => {
                  e.stopPropagation()
                  choose(f.id)
                }}
                className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-white/80 hover:bg-white/10"
              >
                <span
                  className="h-2 w-2 shrink-0 rounded-full"
                  style={{ backgroundColor: f.color ?? DEFAULT_FOLDER_COLOR }}
                />
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                {currentFolderId === f.id && <Check className="h-3.5 w-3.5 shrink-0 text-white" />}
              </button>
            ))}
            {currentFolderId != null && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  choose(null)
                }}
                className="mt-1 flex w-full items-center gap-2 rounded-lg border-t border-white/10 px-2.5 py-1.5 text-left text-sm text-white/60 hover:bg-white/10 hover:text-white"
              >
                <FolderMinus className="h-3.5 w-3.5 shrink-0" />
                Remove from folder
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
