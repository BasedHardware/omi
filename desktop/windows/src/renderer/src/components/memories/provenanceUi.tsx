// Small shared pieces for the Memories audit surface: the provenance meta line
// rendered on every memory card and the filter chip used by the source/date
// toolbars and the "What Omi knows" band.
import { Info, type LucideIcon } from 'lucide-react'
import type { Memory } from '../../hooks/useMemories'
import {
  SOURCE_LABELS,
  isSeenOnce,
  memorySource,
  type MemorySourceKind
} from '../../lib/memoryProvenance'
import { SOURCE_ICONS } from './sourceIcons'

export function SourceTag({ kind }: { kind: MemorySourceKind }): React.JSX.Element {
  const Icon = SOURCE_ICONS[kind]
  return (
    <span className="inline-flex items-center gap-1.5 font-medium text-white/55">
      <Icon className="h-3.5 w-3.5" />
      {SOURCE_LABELS[kind]}
    </span>
  )
}

function Dot(): React.JSX.Element {
  return <span className="h-[3px] w-[3px] shrink-0 rounded-full bg-white/25" />
}

// The provenance meta line on a memory card: source (icon + label), capture
// time, category badge, and the low-evidence "seen once" marker when the server
// flagged the memory as single-source. Fields that are missing simply don't
// render — nothing is faked.
export function ProvenanceLine({ memory }: { memory: Memory }): React.JSX.Element {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-text-quaternary">
      <SourceTag kind={memorySource(memory)} />
      <Dot />
      <time>{new Date(memory.created_at).toLocaleString()}</time>
      {memory.category && <span className="badge text-text-tertiary">{memory.category}</span>}
      {isSeenOnce(memory) && (
        <span
          className="badge border-dashed text-white/50"
          title="Backed by a single source so far — independent confirmations raise Omi's confidence."
        >
          <Info className="mr-1 h-3 w-3" />
          seen once
        </span>
      )}
    </div>
  )
}

export function FilterChip(props: {
  label: string
  count?: number
  active: boolean
  onClick: () => void
  icon?: LucideIcon
  disabled?: boolean
}): React.JSX.Element {
  const { label, count, active, onClick, icon: Icon, disabled } = props
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition-colors disabled:opacity-40 ${
        active
          ? 'border-white/30 bg-white/15 text-white'
          : 'border-white/10 bg-black/20 text-white/65 hover:border-white/20 hover:text-white'
      }`}
    >
      {Icon && <Icon className="h-3 w-3" />}
      {label}
      {count !== undefined && (
        <span className={active ? 'font-normal text-white/60' : 'font-normal text-white/35'}>
          {count}
        </span>
      )}
    </button>
  )
}
