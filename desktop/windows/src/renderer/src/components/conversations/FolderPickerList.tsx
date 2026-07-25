import { Check, FolderMinus } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import { DEFAULT_FOLDER_COLOR } from './folderColors'

// The folder-list body shared by the two move-to-folder surfaces: the row's
// hover MoveToFolderMenu dropdown and the row context menu's "Move to Folder"
// submenu. Renders the empty state, one menuitem per folder (color dot + name +
// current check), and a "Remove from folder" footer when the row is filed.
//
// It renders the items only — each caller owns its own portal/positioning/panel
// wrapper and supplies `onChoose`, which is responsible for closing the menu and
// performing the move. Kept as one component so the two surfaces can't drift.
export function FolderPickerList({
  folders,
  currentFolderId,
  onChoose
}: {
  folders: ConversationFolder[]
  currentFolderId: string | null | undefined
  onChoose: (folderId: string | null) => void
}): React.JSX.Element {
  return (
    <>
      {folders.length === 0 && (
        <div className="px-2.5 py-2 text-xs text-white/45">No folders yet</div>
      )}
      {folders.map((f) => (
        <button
          key={f.id}
          role="menuitem"
          onClick={(e) => {
            e.stopPropagation()
            onChoose(f.id)
          }}
          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-white/80 transition-colors hover:bg-white/10 hover:text-white"
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
        <div className="mt-1.5 border-t border-white/10 pt-1.5">
          <button
            role="menuitem"
            onClick={(e) => {
              e.stopPropagation()
              onChoose(null)
            }}
            className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm text-white/60 transition-colors hover:bg-white/10 hover:text-white"
          >
            <FolderMinus className="h-3.5 w-3.5 shrink-0" />
            Remove from folder
          </button>
        </div>
      )}
    </>
  )
}
