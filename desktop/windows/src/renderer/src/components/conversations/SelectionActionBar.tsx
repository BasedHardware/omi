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
  const canDelete = !deleting && selectedCount > 0
  // An ENABLED action must not read as disabled: enabled = full-strength label on
  // a lifted surface; disabled = 40% opacity + not-allowed. (Merge previously sat
  // at btn-ghost's resting text-white/70 next to a bright red Delete, so it looked
  // greyed out even with 2 rows selected and merging working.)
  const actionClass = (enabled: boolean): string =>
    `btn-ghost px-3 py-1.5 text-xs ${
      enabled ? 'border-white/25 bg-white/[0.10]' : 'cursor-not-allowed opacity-40'
    }`
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
          className={`${actionClass(canMerge)} ${canMerge ? 'text-white hover:text-white' : ''}`}
        >
          <Merge className="h-3.5 w-3.5" />
          Merge
        </button>
        <button
          onClick={onDelete}
          disabled={!canDelete}
          className={`${actionClass(canDelete)} text-red-400 hover:text-red-300`}
        >
          <Trash2 className="h-3.5 w-3.5" />
          Delete
        </button>
      </div>
    </div>
  )
}
