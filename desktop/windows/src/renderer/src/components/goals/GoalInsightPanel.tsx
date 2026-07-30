import { useCallback, useEffect, useRef, useState } from 'react'
import { Lightbulb, RefreshCw, Loader2, AlertTriangle, X } from 'lucide-react'
import { omiApi } from '../../lib/apiClient'
import { Modal } from '../ui/Modal'
import { goalEmoji } from '../../lib/goalEmoji'
import { progressLabel, progressPct } from '../../lib/goalVisuals'
import type { GoalResponse as Goal } from '../../lib/omiApi.generated'

// Per-goal "Goal Insight" sheet, ported from the macOS `GoalInsightSheet`
// (frozen v0.12.72) but wired to the RICHER backend endpoint rather than Mac's
// thinner local `getGoalInsight`. `GET /v1/goals/{goal_id}/advice` runs hybrid
// retrieval (vector + recent conversations + chat + memories) server-side and
// returns `{ advice }` — strictly better than the local memories+conversations
// heuristic, and needs zero client work beyond this call.
//
// INV-UI-1: Mac's progress ring + primary button are purple; both are rendered
// neutral white here. No purple anywhere.

function apiError(e: unknown): string {
  return (
    (e as { response?: { data?: { detail?: string } } }).response?.data?.detail ??
    (e as Error).message
  )
}

type Status = 'loading' | 'loaded' | 'error'
type ErrorKind = 'generic' | 'ratelimit' | 'notfound'

// Small neutral progress ring (Mac renders this in purple; white here per
// INV-UI-1). Purely decorative — the numeric label carries the real value.
function ProgressRing({ pct }: { pct: number }): React.JSX.Element {
  const r = 15
  const c = 2 * Math.PI * r
  const offset = c * (1 - Math.max(0, Math.min(100, pct)) / 100)
  return (
    <svg viewBox="0 0 36 36" className="h-9 w-9 shrink-0 -rotate-90" aria-hidden="true">
      <circle cx="18" cy="18" r={r} fill="none" stroke="rgba(255,255,255,0.12)" strokeWidth="3" />
      <circle
        cx="18"
        cy="18"
        r={r}
        fill="none"
        stroke="rgba(255,255,255,0.75)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeDasharray={c}
        strokeDashoffset={offset}
        className="transition-all duration-500"
      />
    </svg>
  )
}

export function GoalInsightPanel({
  goal,
  onClose
}: {
  goal: Goal
  onClose: () => void
}): React.JSX.Element {
  const [status, setStatus] = useState<Status>('loading')
  const [advice, setAdvice] = useState('')
  const [errorKind, setErrorKind] = useState<ErrorKind>('generic')
  const [errorText, setErrorText] = useState('')
  // Briefly disables Refresh after a 429 so a rapid retry can't re-trip the
  // rate limit the instant the message appears.
  const [cooldown, setCooldown] = useState(false)

  // Guards double-fire: a rapid Refresh (or a mount race) can't stack requests.
  const inFlight = useRef(false)
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const fetchAdvice = useCallback(async (): Promise<void> => {
    if (inFlight.current) return
    inFlight.current = true
    try {
      // Same axios client the rest of Goals uses — auth + the 429/503 backoff
      // interceptor come for free. A 429 that still surfaces here has already
      // exhausted the interceptor's retries, so it's a real rate-limit.
      const res = await omiApi.get(`/v1/goals/${goal.id}/advice`)
      setAdvice(String(res.data?.advice ?? '').trim())
      setStatus('loaded')
    } catch (e) {
      const code = (e as { response?: { status?: number } }).response?.status
      if (code === 404) {
        setErrorKind('notfound')
        setErrorText('This goal no longer exists. It may have been deleted.')
      } else if (code === 429) {
        setErrorKind('ratelimit')
        setErrorText("You're asking for insights a little fast. Try again in a moment.")
        setCooldown(true)
        clearTimeout(cooldownTimer.current)
        cooldownTimer.current = setTimeout(() => setCooldown(false), 4000)
      } else {
        setErrorKind('generic')
        setErrorText(apiError(e))
      }
      setStatus('error')
    } finally {
      inFlight.current = false
    }
  }, [goal.id])

  // Button-driven refetch: flip to the loading view first (allowed here — an
  // event handler, not an effect), then fetch. The mount effect skips this
  // because the initial state is already 'loading'.
  const refresh = useCallback((): void => {
    if (inFlight.current) return
    setStatus('loading')
    void fetchAdvice()
  }, [fetchAdvice])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount / reload-on-goal-change (inFlight-guarded); not a self-retriggering loop
    void fetchAdvice()
    return () => clearTimeout(cooldownTimer.current)
  }, [fetchAdvice])

  const notFound = status === 'error' && errorKind === 'notfound'
  const refreshDisabled = status === 'loading' || cooldown

  return (
    <Modal open onOpenChange={(o) => !o && onClose()} size="md">
      {/* Header: lightbulb tile + title + dismiss */}
      <div className="flex items-center gap-3">
        <div className="glass-subtle flex h-8 w-8 shrink-0 items-center justify-center rounded-xl">
          <Lightbulb className="h-4 w-4 text-white/80" />
        </div>
        <h2 className="flex-1 text-base font-semibold text-white">Goal Insight</h2>
        <button
          onClick={onClose}
          className="shrink-0 rounded-md p-1 text-white/40 transition-colors hover:bg-white/5 hover:text-white/80"
          title="Close"
          aria-label="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Goal-info row: emoji + title + progress ring/label */}
      <div className="mt-4 flex items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <div
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/10 text-[18px] leading-none"
          aria-hidden="true"
        >
          {goalEmoji(goal.title)}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-white/90">{goal.title}</p>
          <p className="mt-0.5 text-xs text-white/45">
            {progressLabel(goal)} · {progressPct(goal)}%
          </p>
        </div>
        <ProgressRing pct={progressPct(goal)} />
      </div>

      {/* Body: loading / error / loaded */}
      <div className="mt-4 min-h-[96px]">
        {status === 'loading' && (
          <div className="flex flex-col items-center justify-center gap-3 py-6 text-white/55">
            <Loader2 className="h-5 w-5 animate-spin" />
            <p className="text-sm">Getting personalized insight…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <AlertTriangle className="h-6 w-6 text-amber-400/80" />
            <p className="max-w-xs text-sm text-white/60">{errorText}</p>
            {!notFound && (
              <button
                onClick={refresh}
                disabled={refreshDisabled}
                className="btn-ghost px-3 py-1.5 text-xs disabled:opacity-40"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Retry
              </button>
            )}
          </div>
        )}

        {status === 'loaded' && (
          <div className="animate-fade-in">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-white/40">
              This week&apos;s action
            </p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-white/85">
              {advice || 'No insight yet. Add a few more conversations and check back.'}
            </p>
          </div>
        )}
      </div>

      {/* Footer: Refresh (ghost) + Done (primary). Refresh is hidden once the
          goal is gone — there's nothing left to fetch. */}
      <div className="mt-6 flex items-center justify-end gap-2">
        {!notFound && (
          <button
            onClick={refresh}
            disabled={refreshDisabled}
            className="btn-ghost px-4 py-2 disabled:opacity-40"
            title="Get a fresh insight"
          >
            <RefreshCw className={`h-4 w-4 ${status === 'loading' ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        )}
        <button onClick={onClose} className="btn-primary px-4 py-2">
          Done
        </button>
      </div>
    </Modal>
  )
}
