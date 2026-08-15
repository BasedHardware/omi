import { useCallback, useEffect, useRef, useState } from 'react'
import { Check, ChevronDown, ChevronRight, Sparkles, X } from 'lucide-react'
import {
  acceptSuggestedCandidate,
  loadSuggestedCandidates,
  rejectSuggestedCandidate,
  type SuggestedCandidate
} from '../../lib/suggestedTasks'

// The Suggested rail (mac parity: SuggestedTasksSection). Renders above the task
// buckets, collapsed by default, only when there are pending candidates. Accept
// and Reject are optimistic: the card leaves immediately and is restored at its
// original index if the backend call fails, with mac's exact sync-error copy.

const EXPANDED_KEY = 'omi.suggestedExpanded.v1'

function readExpanded(): boolean {
  try {
    return window.localStorage.getItem(EXPANDED_KEY) === 'true'
  } catch {
    return false
  }
}

export type SuggestedTasksSectionProps = {
  /** A candidate was accepted into the task list — reconcile + re-read. */
  onAccepted: () => void
}

export function SuggestedTasksSection({
  onAccepted
}: SuggestedTasksSectionProps): React.JSX.Element | null {
  const [candidates, setCandidates] = useState<SuggestedCandidate[]>([])
  const [loaded, setLoaded] = useState(false)
  const [expanded, setExpanded] = useState(readExpanded)
  const [error, setError] = useState<string | null>(null)
  const [busyIds, setBusyIds] = useState<Set<string>>(new Set())
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    void loadSuggestedCandidates()
      .then((result) => {
        if (!alive.current) return
        setCandidates(result.candidates)
        setLoaded(true)
      })
      .catch(() => {
        if (!alive.current) return
        setError('Suggested items could not be refreshed.')
        setLoaded(true)
      })
    return () => {
      alive.current = false
    }
  }, [])

  const setExpandedPersisted = (value: boolean): void => {
    setExpanded(value)
    try {
      window.localStorage.setItem(EXPANDED_KEY, String(value))
    } catch {
      // Session-only expansion on quota failure.
    }
  }

  const markBusy = (id: string, on: boolean): void =>
    setBusyIds((s) => {
      const next = new Set(s)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  // Optimistic remove with restore-at-index on failure (mac's doNow/dismiss shape).
  const resolve = useCallback(
    async (
      candidate: SuggestedCandidate,
      op: (c: SuggestedCandidate) => Promise<unknown>,
      onSuccess?: () => void
    ): Promise<void> => {
      const index = candidates.findIndex((c) => c.id === candidate.id)
      if (index === -1) return
      markBusy(candidate.id, true)
      setError(null)
      setCandidates((list) => list.filter((c) => c.id !== candidate.id))
      try {
        await op(candidate)
        onSuccess?.()
      } catch {
        setCandidates((list) => {
          const restored = [...list]
          restored.splice(Math.min(index, restored.length), 0, candidate)
          return restored
        })
        setError('That Suggested action did not sync. Try again.')
      } finally {
        markBusy(candidate.id, false)
      }
    },
    [candidates]
  )

  if (!loaded || (candidates.length === 0 && !error)) return null

  return (
    <section data-testid="suggested-section" className="mx-auto max-w-3xl">
      <button
        data-testid="suggested-toggle"
        onClick={() => setExpandedPersisted(!expanded)}
        className="mb-2 flex items-center gap-2 px-1 text-xs font-semibold uppercase tracking-wide text-white/40 hover:text-white/70"
      >
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" />
        )}
        <Sparkles className="h-3.5 w-3.5" />
        Suggested
        <span className="text-white/25">{candidates.length}</span>
      </button>

      {error && (
        <p data-testid="suggested-error" className="mb-2 px-1 text-xs text-rose-300/80">
          {error}
        </p>
      )}

      {expanded && candidates.length > 0 && (
        <ul className="mb-4 space-y-2">
          {candidates.map((c) => {
            const busy = busyIds.has(c.id)
            return (
              <li key={c.id} className="surface-card flex items-start gap-3 p-4">
                <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-white/30" />
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-relaxed text-white/90">{c.title}</p>
                  {c.detail && (
                    <p className="mt-0.5 truncate text-[11px] text-white/45">{c.detail}</p>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <button
                    data-testid={`suggested-accept-${c.id}`}
                    disabled={busy}
                    onClick={() =>
                      void resolve(c, (cand) => acceptSuggestedCandidate(cand), onAccepted)
                    }
                    className="btn-primary px-3 py-1.5 text-xs disabled:opacity-40"
                  >
                    <Check className="h-3.5 w-3.5" />
                    Accept
                  </button>
                  <button
                    data-testid={`suggested-reject-${c.id}`}
                    disabled={busy}
                    onClick={() => void resolve(c, (cand) => rejectSuggestedCandidate(cand))}
                    className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-40"
                  >
                    <X className="h-3.5 w-3.5" />
                    Reject
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
