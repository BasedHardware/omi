import { useState } from 'react'
import { Loader2, AlertCircle } from 'lucide-react'
import { Modal } from '../ui/Modal'
import { toast } from '../../lib/toast'
import {
  taskCleanupPreview,
  taskCleanupExecute,
  type CleanupPreviewResult,
  type CleanupStrategy
} from '../../lib/taskCleanup'

type Phase = 'config' | 'loading' | 'preview' | 'deleting'

const STRATEGIES: {
  id: CleanupStrategy
  label: string
  detail: string
  slow?: true
}[] = [
  {
    id: 'stale_age',
    label: 'Stale tasks',
    detail: 'Open tasks older than 90 days with no due date'
  },
  {
    id: 'overdue',
    label: 'Long overdue',
    detail: 'Tasks with a due date more than 30 days in the past'
  },
  {
    id: 'vague',
    label: 'Vague / context-lost',
    detail: 'Tasks with unresolved pronouns ("put it away", "fix those", "Speaker 1")'
  },
  {
    id: 'semantic_dedup',
    label: 'Near-duplicates',
    detail: 'Older of any two tasks with nearly identical descriptions',
    slow: true
  },
  {
    id: 'llm_relevance',
    label: 'AI relevance check',
    detail: 'LLM judges whether each task is still actionable',
    slow: true
  },
  {
    id: 'conversation_context',
    label: 'Conversation context',
    detail: 'Uses the source conversation title/summary to judge staleness',
    slow: true
  }
]

const DEFAULT_STRATEGIES: CleanupStrategy[] = ['stale_age', 'overdue', 'vague']

const STRATEGY_LABEL: Record<string, string> = {
  stale_age: 'Stale',
  overdue: 'Overdue',
  vague: 'Vague',
  semantic_dedup: 'Duplicate',
  llm_relevance: 'AI-flagged',
  conversation_context: 'Context-stale'
}

function apiDetail(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

type Props = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function TaskCleanupModal({ open, onOpenChange }: Props): React.JSX.Element {
  const [phase, setPhase] = useState<Phase>('config')
  const [selected, setSelected] = useState<Set<CleanupStrategy>>(new Set(DEFAULT_STRATEGIES))
  const [preview, setPreview] = useState<CleanupPreviewResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Candidate IDs the user has unchecked in the review list — kept out of deletion.
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set())

  const toggleCandidate = (id: string): void => {
    setExcludedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleStrategy = (s: CleanupStrategy): void => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(s)) next.delete(s)
      else next.add(s)
      return next
    })
  }

  const hasSlow = [...selected].some((s) => STRATEGIES.find((x) => x.id === s)?.slow)

  const analyze = async (): Promise<void> => {
    if (selected.size === 0) return
    setPhase('loading')
    setError(null)
    try {
      const result = await taskCleanupPreview({
        strategies: [...selected],
        age_days: 90,
        overdue_days: 30
      })
      setPreview(result)
      setExcludedIds(new Set())
      setPhase('preview')
    } catch (e) {
      setError(apiDetail(e))
      setPhase('config')
    }
  }

  const execute = async (): Promise<void> => {
    if (!preview) return
    setPhase('deleting')
    try {
      const result = await taskCleanupExecute(preview.session_id, [...excludedIds])
      const n = result.deleted_count
      toast(`Deleted ${n.toLocaleString()} task${n === 1 ? '' : 's'}`, { tone: 'success' })
      void window.omi.tasksReconcile()
      resetAndClose()
    } catch (e) {
      const status = (e as { response?: { status?: number } }).response?.status
      if (status === 410) {
        toast('Session expired — please analyze again', { tone: 'warn' })
        setPhase('config')
        setPreview(null)
        setExcludedIds(new Set())
      } else {
        toast('Delete failed', { tone: 'error', body: apiDetail(e) })
        setPhase('preview')
      }
    }
  }

  const resetAndClose = (): void => {
    onOpenChange(false)
    // Defer reset so the closing animation doesn't flash config state.
    setTimeout(() => {
      setPhase('config')
      setPreview(null)
      setError(null)
      setExcludedIds(new Set())
    }, 300)
  }

  const isDeleting = phase === 'deleting'
  const remainingCount = preview ? preview.total_candidates - excludedIds.size : 0

  const footer =
    phase === 'config' ? (
      <>
        <button onClick={resetAndClose} className="btn-ghost">
          Cancel
        </button>
        <button
          onClick={analyze}
          disabled={selected.size === 0}
          className="btn-primary px-4 py-2 disabled:opacity-40"
        >
          Analyze
        </button>
      </>
    ) : phase === 'preview' && preview ? (
      <>
        <button
          onClick={() => {
            setPhase('config')
            setPreview(null)
            setExcludedIds(new Set())
          }}
          className="btn-ghost"
        >
          Back
        </button>
        <button
          onClick={execute}
          disabled={remainingCount === 0}
          className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-40"
        >
          Delete {remainingCount.toLocaleString()} task
          {remainingCount === 1 ? '' : 's'}
        </button>
      </>
    ) : phase === 'deleting' ? (
      <span className="flex items-center gap-2 text-sm text-white/50">
        <Loader2 className="h-4 w-4 animate-spin" />
        Deleting…
      </span>
    ) : null

  return (
    <Modal
      open={open}
      onOpenChange={(v) => {
        if (isDeleting) return
        if (!v) resetAndClose()
        else onOpenChange(true)
      }}
      title="Clean up tasks"
      dismissible={!isDeleting}
      size="md"
      footer={footer}
    >
      {/* ── Config ─────────────────────────────────────────────── */}
      {phase === 'config' && (
        <div className="space-y-4">
          <p className="text-white/60">
            Choose which strategies to run. Fast ones finish in seconds; slow ones use AI and may
            take 1–3 minutes on large accounts.
          </p>

          <div className="space-y-1">
            {STRATEGIES.map((s) => (
              <label
                key={s.id}
                className="flex cursor-pointer items-start gap-3 rounded-lg px-2 py-2 hover:bg-white/5"
              >
                <input
                  type="checkbox"
                  checked={selected.has(s.id)}
                  onChange={() => toggleStrategy(s.id)}
                  className="mt-0.5 accent-[color:var(--accent)]"
                />
                <div className="min-w-0">
                  <span className="text-sm text-white/90">{s.label}</span>
                  {s.slow && (
                    <span className="ml-2 rounded bg-amber-400/20 px-1.5 py-0.5 text-xs text-amber-300">
                      slow
                    </span>
                  )}
                  <p className="text-xs text-white/45">{s.detail}</p>
                </div>
              </label>
            ))}
          </div>

          {hasSlow && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-400/10 px-3 py-2 text-xs text-amber-300">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              AI strategies process tasks in batches — expect 1–3 minutes for accounts with
              thousands of tasks.
            </div>
          )}

          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              {error}
            </div>
          )}
        </div>
      )}

      {/* ── Loading ─────────────────────────────────────────────── */}
      {phase === 'loading' && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="h-8 w-8 animate-spin text-white/40" />
          <div className="text-center">
            <p className="text-white/80">Analyzing your tasks…</p>
            {hasSlow && (
              <p className="mt-1 text-xs text-white/40">AI strategies may take a minute or two</p>
            )}
          </div>
        </div>
      )}

      {/* ── Preview ─────────────────────────────────────────────── */}
      {phase === 'preview' && preview && (
        <div className="space-y-4">
          {preview.total_candidates > 0 ? (
            <p className="text-white/80">
              Found{' '}
              <span className="font-semibold text-white">
                {preview.total_candidates.toLocaleString()}
              </span>{' '}
              task{preview.total_candidates === 1 ? '' : 's'} matching your criteria. Review the
              list below and uncheck anything you want to keep.
            </p>
          ) : (
            <p className="text-white/60">
              Nothing to clean up — your tasks look good with the selected strategies.
            </p>
          )}

          {/* Breakdown */}
          {Object.values(preview.breakdown).some((n) => n > 0) && (
            <div className="glass-subtle rounded-lg px-4 py-3 text-sm">
              {Object.entries(preview.breakdown)
                .filter(([, n]) => n > 0)
                .map(([strategy, count]) => (
                  <div key={strategy} className="flex items-center justify-between py-0.5">
                    <span className="text-white/55">{STRATEGY_LABEL[strategy] ?? strategy}</span>
                    <span className="tabular-nums text-white/90">{count.toLocaleString()}</span>
                  </div>
                ))}
            </div>
          )}

          {/* Review candidates — uncheck any task to keep it */}
          {preview.candidate_meta.length > 0 && (
            <div>
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-xs font-medium uppercase tracking-wide text-white/35">
                  Review ({remainingCount.toLocaleString()} of{' '}
                  {preview.candidate_meta.length.toLocaleString()} selected)
                </p>
                <div className="flex gap-2 text-xs text-white/45">
                  <button onClick={() => setExcludedIds(new Set())} className="hover:text-white/80">
                    Select all
                  </button>
                  <span className="text-white/20">·</span>
                  <button
                    onClick={() => setExcludedIds(new Set(preview.candidate_meta.map((c) => c.id)))}
                    className="hover:text-white/80"
                  >
                    Deselect all
                  </button>
                </div>
              </div>
              <ul className="glass-subtle max-h-64 space-y-0.5 overflow-y-auto rounded-lg px-4 py-3 text-sm text-white/55">
                {preview.candidate_meta.map((item) => (
                  <li key={item.id} className="flex items-baseline gap-2">
                    <input
                      type="checkbox"
                      checked={!excludedIds.has(item.id)}
                      onChange={() => toggleCandidate(item.id)}
                      className="mt-0.5 shrink-0 accent-[color:var(--accent)]"
                    />
                    <span className="shrink-0 rounded bg-white/10 px-1 py-px text-xs text-white/35">
                      {STRATEGY_LABEL[item.strategy] ?? item.strategy}
                    </span>
                    <span
                      className={`truncate ${excludedIds.has(item.id) ? 'text-white/30 line-through' : ''}`}
                    >
                      {item.description}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="text-xs text-white/30">
            Deletion is permanent. Session expires in {Math.round(preview.expires_in_seconds / 60)}{' '}
            min — confirm before then.
          </p>
        </div>
      )}

      {/* ── Deleting ─────────────────────────────────────────────── */}
      {phase === 'deleting' && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Loader2 className="h-8 w-8 animate-spin text-white/40" />
          <p className="text-white/80">Deleting tasks…</p>
        </div>
      )}
    </Modal>
  )
}
