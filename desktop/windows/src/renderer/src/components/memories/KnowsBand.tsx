// "What Omi knows about you" — grouped category and source counts over the
// loaded memory set. Clicking a source count applies that source filter;
// clicking a category chip applies a text filter is intentionally NOT done
// (category chips are read-only context, categories aren't a filter axis here).
import type { Memory } from '../../hooks/useMemories'
import {
  SOURCE_LABELS,
  categoryCounts,
  categoryLabel,
  sourceCounts,
  type MemorySourceKind
} from '../../lib/memoryProvenance'
import { SOURCE_ICONS } from './sourceIcons'

export function KnowsBand(props: {
  memories: Memory[]
  activeSource: MemorySourceKind | 'all'
  onPickSource: (kind: MemorySourceKind | 'all') => void
}): React.JSX.Element | null {
  const { memories, activeSource, onPickSource } = props
  if (memories.length === 0) return null
  const bySource = sourceCounts(memories)
  const byCategory = categoryCounts(memories)

  return (
    <div className="mx-auto mb-5 max-w-4xl">
      <div className="surface-card px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <span className="section-label">What Omi knows about you</span>
          <span className="text-xs text-white/35">
            {memories.length} memor{memories.length === 1 ? 'y' : 'ies'} from {bySource.length}{' '}
            source{bySource.length === 1 ? '' : 's'}
          </span>
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {byCategory.map(({ category, count }) => (
            <span key={category} className="badge">
              {categoryLabel(category)} <span className="ml-1 font-normal text-white/35">{count}</span>
            </span>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2 text-[13px]">
          <span className="text-xs text-white/35">Learned from</span>
          {bySource.map(({ kind, count }) => {
            const Icon = SOURCE_ICONS[kind]
            const active = activeSource === kind
            return (
              <button
                key={kind}
                onClick={() => onPickSource(active ? 'all' : kind)}
                className={`inline-flex items-center gap-1.5 font-medium transition-colors ${
                  active ? 'text-white' : 'text-white/55 hover:text-white'
                }`}
                title={`Show only memories from ${SOURCE_LABELS[kind].toLowerCase()}`}
              >
                <Icon className="h-3.5 w-3.5" />
                {SOURCE_LABELS[kind]} {count}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}
