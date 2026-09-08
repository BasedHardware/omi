import { useCallback, useEffect, useRef, useState } from 'react'
import { StepScaffold } from './StepScaffold'

export type PermissionStatus = 'idle' | 'waiting' | 'granted' | 'denied'

/** How the step arrived at 'granted'. Only a CLICK — the user asking for the
 *  permission right here — auto-advances. A grant we merely *detected* (already
 *  allowed before the step opened, or flipped on in Windows Settings while the step
 *  sat idle) renders a confirmed state and waits for Continue: onboarding must never
 *  flash past a step the user never interacted with. */
type GrantRoute = 'click' | 'detected'

/** Mac parity (OnboardingPermissionStepView.swift): after the user's own grant lands,
 *  pause briefly on the confirmation, then advance. */
const AUTO_ADVANCE_MS = 350
/** Mac parity: the permission state is re-read on a 1s timer while the step is idle. */
const POLL_INTERVAL_MS = 1000

type PermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  eyebrow: string
  title: string
  subtitle?: string
  /** Icon shown inside the status card (e.g. a lucide glyph). */
  icon: React.ReactNode
  /** Label for the row inside the status card, e.g. "Microphone". */
  cardLabel: string
  statusText: Record<PermissionStatus, string>
  buttonLabel: Record<PermissionStatus, string>
  /**
   * Ask for the permission / perform the opt-in. **Resolving means granted;
   * throwing means denied** — the step never claims "Granted" for a rejected
   * request (the thrown error's message is surfaced in-UI).
   */
  onActivate: () => Promise<void>
  /**
   * Read the CURRENT state of whatever this step controls, without prompting. Polled
   * every second **while the step is idle** (and re-read on window focus, so granting
   * it in Windows Settings and coming back is picked up).
   *
   * A `true` read only ever CONFIRMS — it renders the granted state and shows Continue.
   * It never auto-advances, never overturns an explicit denial, and never preempts an
   * in-flight request. Steps whose state is not readable simply omit it.
   */
  checkGranted?: () => Promise<boolean>
  /**
   * The user has affirmatively TAKEN this permission — fired once, either when their
   * click-driven grant lands, or when they press Continue on a state we detected as
   * already-granted. Never fired for a bare detection, and never on Skip: side effects
   * (e.g. opting into always-on recording) must not ride on a grant the user never made.
   */
  onGranted?: () => void
  /** Shown under the status card while denied — how to recover (OS-specific). */
  deniedHint?: string
  /** Optional denied-state button, e.g. "Open Windows Settings". */
  recoveryLabel?: string
  onRecover?: () => void
  /** Advance to the next step. Automatic only after a click-driven grant. */
  onContinue: () => void
  /** Step back. Permission steps are as backtrackable as any other step. */
  onBack?: () => void
  /** Skip this permission without granting it (small text button up top). */
  onSkip?: () => void
}

/**
 * Shared onboarding "permission" step: an icon status card plus an action button
 * that runs `onActivate`. Outcomes are explicit — granted (click → auto-advance after
 * 350ms; detected → Continue) or denied (reason + recovery affordance, retry or skip).
 *
 * The denial is final until the user acts again: polling stops, and nothing can rescue
 * a denied step back into "Granted" behind their back.
 */
export function PermissionStep({
  stepIndex,
  totalSteps,
  aside,
  eyebrow,
  title,
  subtitle,
  icon,
  cardLabel,
  statusText,
  buttonLabel,
  onActivate,
  checkGranted,
  onGranted,
  deniedHint,
  recoveryLabel,
  onRecover,
  onContinue,
  onBack,
  onSkip
}: PermissionStepProps): React.JSX.Element {
  const [status, setStatus] = useState<PermissionStatus>('idle')
  const [grantRoute, setGrantRoute] = useState<GrantRoute | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Latest callbacks, so the poll effect never re-subscribes on every render
  // (steps pass these inline, so their identity changes every time). Written in an
  // effect — never during render — and declared before the poll effect so the ref
  // is current by the time the poll's first check runs.
  const cbs = useRef({ onContinue, onGranted, checkGranted })
  useEffect(() => {
    cbs.current = { onContinue, onGranted, checkGranted }
  })
  // The transition guards below run from async callbacks, so they need the status as
  // of *now*, not as of the render that closed over them.
  const statusRef = useRef<PermissionStatus>('idle')
  const setPermissionStatus = useCallback((next: PermissionStatus): void => {
    statusRef.current = next
    setStatus(next)
  }, [])
  // The auto-advance is a timer, and the user can leave (Skip, Back) before it fires.
  // Held so unmount can cancel it — an orphaned timer used to call onContinue() *after*
  // the step had already advanced, skipping the following step entirely.
  const advanceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(
    () => () => {
      if (advanceTimer.current) clearTimeout(advanceTimer.current)
    },
    []
  )
  // onGranted's side effects are once-only, whichever route the user took to accept.
  const acceptedGrant = useRef(false)
  const acceptGrant = useCallback((): void => {
    if (acceptedGrant.current) return
    acceptedGrant.current = true
    cbs.current.onGranted?.()
  }, [])

  const markGranted = useCallback(
    (route: GrantRoute): void => {
      const prev = statusRef.current
      if (prev === 'granted') return
      // A detected grant may only ever speak from a standing start: it must not
      // overturn an explicit denial, nor beat an in-flight request whose rejection
      // has yet to land.
      if (route === 'detected' && prev !== 'idle') return

      setPermissionStatus('granted')
      setGrantRoute(route)
      setError(null)
      if (route !== 'click') return
      // The user asked for this permission and got it — carry them onward.
      acceptGrant()
      advanceTimer.current = setTimeout(() => cbs.current.onContinue(), AUTO_ADVANCE_MS)
    },
    [acceptGrant, setPermissionStatus]
  )

  const handleActivate = async (): Promise<void> => {
    setPermissionStatus('waiting')
    setError(null)
    try {
      await onActivate()
    } catch (e) {
      // Denied/blocked/failed — do NOT advance, do NOT claim granted.
      setPermissionStatus('denied')
      setError(e instanceof Error ? e.message : String(e))
      return
    }
    markGranted('click')
  }

  // Continue off a detected grant: this press IS the user accepting the permission,
  // so the grant side effects fire here rather than on the bare detection.
  const handleContinue = (): void => {
    acceptGrant()
    cbs.current.onContinue()
  }

  // Poll the real state (Mac's 1s Timer) and re-check on refocus (Mac's scenePhase ==
  // .active). Runs ONLY while idle: once the user has asked ('waiting') or been refused
  // ('denied'), their action owns the outcome — a background poll must not rewrite it.
  const pollable = Boolean(checkGranted)
  const idle = status === 'idle'
  useEffect(() => {
    if (!pollable || !idle) return
    let cancelled = false
    const check = (): void => {
      void cbs.current.checkGranted!()
        .then((granted) => {
          if (!cancelled && granted) markGranted('detected')
        })
        .catch(() => {
          /* unreadable permission state — keep polling, never assume granted */
        })
    }
    check()
    const id = setInterval(check, POLL_INTERVAL_MS)
    window.addEventListener('focus', check)
    document.addEventListener('visibilitychange', check)
    return () => {
      cancelled = true
      clearInterval(id)
      window.removeEventListener('focus', check)
      document.removeEventListener('visibilitychange', check)
    }
  }, [pollable, idle, markGranted])

  const denied = status === 'denied'
  const granted = status === 'granted'
  const busy = status === 'waiting' || granted
  // Skip is meaningless mid-auto-advance (and used to race it), but stays available on
  // a detected grant — that is the user's only way to say "no" to something already on.
  const skippable = onSkip && grantRoute !== 'click'

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      eyebrow={eyebrow}
      title={title}
      subtitle={subtitle}
      align="left"
      aside={aside}
      onSkip={skippable ? onSkip : undefined}
    >
      <div className="flex w-full items-center justify-between rounded-xl bg-white/[0.06] px-5 py-4">
        <div className="flex items-center gap-3">
          {icon}
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium text-white/90">{cardLabel}</span>
            <span
              className={
                'text-xs ' +
                (granted ? 'text-green-400' : denied ? 'text-amber-400' : 'text-white/40')
              }
            >
              {statusText[status]}
            </span>
          </div>
        </div>
      </div>

      {denied && (deniedHint || error) && (
        <p className="mt-3 text-xs leading-relaxed text-amber-400/90">{deniedHint ?? error}</p>
      )}

      <div className="mt-8 flex items-center gap-3">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="rounded-xl bg-white/10 px-5 py-3 text-sm font-medium text-white/80 transition-colors hover:bg-white/[0.16]"
          >
            Back
          </button>
        )}
        <button
          type="button"
          onClick={() => void handleActivate()}
          disabled={busy}
          className={
            'rounded-xl px-8 py-3 text-sm font-medium transition-all ' +
            (status === 'waiting'
              ? 'cursor-not-allowed bg-white/20 text-white/50'
              : granted
                ? 'cursor-default bg-green-500/20 text-green-400'
                : 'bg-white text-black hover:opacity-90')
          }
        >
          {buttonLabel[status]}
        </button>
        {/* A detected grant is confirmed, not consented — the user still drives. */}
        {granted && grantRoute === 'detected' && (
          <button
            type="button"
            onClick={handleContinue}
            className="rounded-xl bg-white px-8 py-3 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Continue
          </button>
        )}
        {denied && recoveryLabel && onRecover && (
          <button
            type="button"
            onClick={onRecover}
            className="rounded-xl bg-white/10 px-5 py-3 text-sm font-medium text-white/80 transition-colors hover:bg-white/[0.16]"
          >
            {recoveryLabel}
          </button>
        )}
      </div>
    </StepScaffold>
  )
}
