import { Pencil, Plus, Star } from 'lucide-react'
import type { ConversationFolder } from '../../../../shared/types'
import type { FolderFilter } from '../../lib/conversations/filtering'
import { DEFAULT_FOLDER_COLOR } from './folderColors'

// Horizontal folder strip: fixed "All" + "Starred" chips, one chip per folder,
// then a "+" create button. Selected chip = textPrimary@0.12 fill + @0.3 stroke
// (Mac — neutral, NOT purple). Folder chips show a color dot, a purple count
// badge, and a hover-revealed edit affordance. Purple appears only in the count
// badge (Track 4 ruling: purple ports as-is; chips stay neutral).

function chipClass(active: boolean): string {
  return [
    'flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors duration-150',
    active
      ? 'border-white/30 bg-white/[0.12] text-white'
      : 'border-white/10 bg-transparent text-white/60 hover:bg-white/5 hover:text-white/90'
  ].join(' ')
}

function CountBadge({ n }: { n: number }): React.JSX.Element | null {
  if (n <= 0) return null
  // Purple count badge (Track 4 ruling — purple ports as-is).
  return (
    <span
      className="ml-0.5 rounded-full px-1.5 py-px text-[10px] font-semibold tabular-nums text-white"
      style={{ backgroundColor: 'rgba(139, 92, 246, 0.30)' }}
    >
      {n}
    </span>
  )
}

export function FolderTabsStrip({
  folders,
  selected,
  onSelect,
  onCreate,
  onEditFolder
}: {
  folders: ConversationFolder[]
  selected: FolderFilter
  onSelect: (f: FolderFilter) => void
  onCreate: () => void
  onEditFolder: (folder: ConversationFolder) => void
}): React.JSX.Element {
  return (
    <div className="no-scrollbar flex items-center gap-2 overflow-x-auto px-6 pb-3 lg:px-10">
      <button
        onClick={() => onSelect({ kind: 'all' })}
        className={chipClass(selected.kind === 'all')}
      >
        All
      </button>
      <button
        onClick={() => onSelect({ kind: 'starred' })}
        className={chipClass(selected.kind === 'starred')}
      >
        <Star className="h-3.5 w-3.5" />
        Starred
      </button>

      {folders.map((f) => {
        const active = selected.kind === 'folder' && selected.id === f.id
        return (
          <div key={f.id} className="group relative flex shrink-0 items-center">
            <button
              onClick={() => onSelect({ kind: 'folder', id: f.id })}
              className={chipClass(active) + ' group-hover:pr-7'}
            >
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: f.color ?? DEFAULT_FOLDER_COLOR }}
              />
              <span className="max-w-[160px] truncate">{f.name}</span>
              <CountBadge n={f.conversationCount} />
            </button>
            {/* Hover-revealed edit affordance (system folders aren't editable). */}
            {!f.isSystem && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  onEditFolder(f)
                }}
                aria-label={`Edit ${f.name}`}
                className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-white/50 hover:text-white group-hover:block"
              >
                <Pencil className="h-3 w-3" />
              </button>
            )}
          </div>
        )
      })}

      <button
        onClick={onCreate}
        aria-label="New folder"
        className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/10 text-white/60 transition-colors hover:border-white/20 hover:bg-white/5 hover:text-white"
      >
        <Plus className="h-4 w-4" />
      </button>
    </div>
  )
}
