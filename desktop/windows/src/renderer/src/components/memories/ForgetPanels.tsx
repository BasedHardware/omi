// Selective-forget panels: the consequence preview shown before any delete
// happens (replaces window.confirm) and the honest progress panel shown while
// the existing paced delete runs.
import { Clock, Loader2, Trash2 } from 'lucide-react'
import type { Memory } from '../../hooks/useMemories'
import {
  SOURCE_LABELS,
  categoryLabel,
  describeFilters,
  estimateForgetSeconds,
  forgetPreview,
  formatDuration,
  type MemoryFilters
} from '../../lib/memoryProvenance'

const MAX_BAR_ROWS = 4

function BarRows(props: { rows: { label: string; count: number }[] }): React.JSX.Element {
  const rows = props.rows.slice(0, MAX_BAR_ROWS)
  const max = rows[0]?.count ?? 1
  return (
    <div className="space-y-1.5">
      {rows.map(({ label, count }) => (
        <div key={label} className="flex items-center gap-2 text-xs">
          <span className="w-24 shrink-0 truncate text-white/60">{label}</span>
          <span className="h-1 flex-1 overflow-hidden rounded-full bg-white/10">
            <span
              className="block h-full rounded-full bg-white/45"
              style={{ width: `${Math.max(4, Math.round((count / max) * 100))}%` }}
            />
          </span>
          <span className="w-8 shrink-0 text-right text-white/40">{count}</span>
        </div>
      ))}
    </div>
  )
}

// Consequence preview: exact count, where the selected memories came from and
// what they are about, the plain-language outcome, and the honest pacing
// estimate — all before anything is deleted.
export function ForgetPreviewPanel(props: {
  selected: Memory[]
  filters: MemoryFilters
  onCancel: () => void
  onConfirm: () => void
}): React.JSX.Element {
  const { selected, filters, onCancel, onConfirm } = props
  const preview = forgetPreview(selected)
  const scope = describeFilters(filters)
  const eta = formatDuration(estimateForgetSeconds(preview.count))

  return (
    <div className="surface-card mx-auto mb-5 max-w-4xl animate-fade-in p-5">
      <div className="font-display text-lg font-bold text-white">
        Forget {preview.count} memor{preview.count === 1 ? 'y' : 'ies'}?{' '}
        {scope && <span className="font-body text-sm font-normal text-white/50">{scope}</span>}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-5 sm:grid-cols-2">
        <div>
          <div className="section-label mb-2">Where they came from</div>
          <BarRows
            rows={preview.bySource.map(({ kind, count }) => ({
              label: SOURCE_LABELS[kind],
              count
            }))}
          />
        </div>
        <div>
          <div className="section-label mb-2">What they are about</div>
          <BarRows
            rows={preview.byCategory.map(({ category, count }) => ({
              label: categoryLabel(category),
              count
            }))}
          />
        </div>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-white/70">
        {preview.count === 1 ? 'This memory' : `These ${preview.count} memories`} will be
        permanently removed from your account and from everything Omi says from now on. The
        recordings and conversations they came from are not touched. This cannot be undone.
      </p>
      <p className="mt-2 flex items-start gap-2 text-xs leading-relaxed text-white/45">
        <Clock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        The server allows about 60 deletions per hour, so this will take {eta}. You can stop
        anytime and resume later; memories already forgotten stay forgotten.
      </p>
      <div className="mt-4 flex items-center justify-end gap-2">
        <button onClick={onCancel} className="btn-ghost px-3 py-2">
          Cancel
        </button>
        <button onClick={onConfirm} className="btn-primary px-4 py-2">
          <Trash2 className="h-4 w-4" />
          Forget {preview.count} memor{preview.count === 1 ? 'y' : 'ies'}
        </button>
      </div>
    </div>
  )
}

// Progress panel while the paced delete runs: live tally, remaining-time
// estimate, visible rate-limit pauses, and Stop.
export function ForgetProgressPanel(props: {
  deleted: number
  failed: number
  total: number
  waitSeconds: number
  onStop: () => void
}): React.JSX.Element {
  const { deleted, failed, total, waitSeconds, onStop } = props
  const done = deleted + failed
  const remaining = Math.max(0, total - done)
  const pct = total > 0 ? Math.round((done / total) * 100) : 0

  return (
    <div className="surface-card mx-auto mb-5 max-w-4xl animate-fade-in p-5">
      <div className="flex flex-wrap items-center gap-3">
        <Loader2 className="h-4 w-4 animate-spin text-white/70" />
        <span className="font-display text-base font-bold text-white">
          Forgetting {Math.min(done + 1, total)} of {total}…
        </span>
        <span className="text-xs text-white/45">
          {deleted} forgotten, {failed} failed
        </span>
        <button onClick={onStop} className="btn-ghost ml-auto px-3 py-1.5 text-sm">
          Stop
        </button>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full rounded-full bg-white/60 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-white/40">
        {remaining > 0 && (
          // Never show an estimate shorter than a pause we know we're in.
          <span>{formatDuration(Math.max(estimateForgetSeconds(remaining), waitSeconds))} left</span>
        )}
        {waitSeconds > 0 && (
          <span>Paused by the server rate limit — resuming in about {waitSeconds}s</span>
        )}
        <span>Memories already forgotten stay forgotten if you stop.</span>
      </div>
    </div>
  )
}
