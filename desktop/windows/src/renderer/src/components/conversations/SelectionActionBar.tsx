import { Merge, Trash2 } from 'lucide-react'

// Bottom-anchored floating action bar for multi-select mode: selection count,
// select/deselect-all, Merge (enabled at ≥2 cloud conversations), Delete. Merge
// applies to cloud conversations only (needs backend ids); the count reflects the
// mergeable subset so the button is disabled for local-only / chat selections.
export function SelectionActionBar({
  selectedCount,
  mergeableCount,
  allSelected,
  onToggleSelectAll,
  onMerge,
  onDelete,
  deleting
}: {
  selectedCount: number
  mergeableCount: number
  allSelected: boolean
  onToggleSelectAll: () => void
  onMerge: () => void
  onDelete: () => void
  deleting: boolean
}): React.JSX.Element {
  const canMerge = mergeableCount >= 2
  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-6 z-[80] flex justify-center px-6">
      <div className="glass-strong pointer-events-auto flex items-center gap-2 px-3 py-2">
        <span className="px-2 text-sm font-medium tabular-nums text-white/80">
          {selectedCount} selected
        </span>
        <button onClick={onToggleSelectAll} className="btn-ghost px-3 py-1.5 text-xs">
          {allSelected ? 'Deselect all' : 'Select all'}
        </button>
        <div className="mx-1 h-5 w-px bg-white/10" />
        <button
          onClick={onMerge}
          disabled={!canMerge}
          title={
            canMerge ? 'Merge into one conversation' : 'Select 2+ synced conversations to merge'
          }
          className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-40"
        >
          <Merge className="h-3.5 w-3.5" />
          Merge
        </button>
        <button
          onClick={onDelete}
          disabled={deleting || selectedCount === 0}
          className="btn-ghost px-3 py-1.5 text-xs text-red-400 hover:text-red-300 disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
      </div>
    </div>
  )
}
