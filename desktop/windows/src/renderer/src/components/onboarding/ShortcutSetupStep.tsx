import { useEffect, useRef, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { getPreferences, setPreferences } from '../../lib/preferences'
import {
  DEFAULT_OVERLAY_ACCELERATOR,
  acceleratorToTokens,
  eventToAccelerator,
  validateCustomAccelerator
} from '../../lib/overlayShortcut'

type ShortcutSetupStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

/**
 * Onboarding step to set the floating-bar ("Ask a question") summon shortcut.
 * Enables + warms the overlay on mount so the user can press the shortcut and
 * watch the keys light up (and the bar appear). "Custom" records a new combo by
 * suspending the global shortcut and reading raw keydowns.
 */
export function ShortcutSetupStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: ShortcutSetupStepProps): React.JSX.Element {
  const [accel, setAccel] = useState<string>(
    () => getPreferences().overlayShortcut ?? DEFAULT_OVERLAY_ACCELERATOR
  )
  const [recording, setRecording] = useState(false)
  const [lit, setLit] = useState(false)
  const [worked, setWorked] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const litTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Enable + warm the overlay here (not before), apply the current accelerator,
  // and light up the keys whenever the shortcut fires.
  useEffect(() => {
    window.omiOverlay?.setEnabled(true)
    void window.omiOverlay?.setAccelerator(accel)
    const off = window.omiOverlay?.onSummoned(() => {
      setWorked(true)
      setLit(true)
      if (litTimer.current) clearTimeout(litTimer.current)
      litTimer.current = setTimeout(() => setLit(false), 450)
    })
    return () => {
      off?.()
      if (litTimer.current) clearTimeout(litTimer.current)
    }
    // Mount-only: re-applying on every accel change would fight the rebind flow.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // While recording, the global shortcut is suspended so every keydown reaches
  // us. A complete combo (≥1 modifier + key) commits; Esc cancels.
  useEffect(() => {
    if (!recording) return
    const onKeyDown = (e: KeyboardEvent): void => {
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        void window.omiOverlay?.resumeShortcut()
        setRecording(false)
        return
      }
      const next = eventToAccelerator(e)
      if (!next) return // still building the chord (modifier-only / no modifier yet)
      // Reject combos that clash with the OS or are unstable BEFORE claiming them;
      // stay in recording mode so the user can immediately try another.
      const valid = validateCustomAccelerator(next)
      if (!valid.ok) {
        setError(valid.reason)
        return
      }
      void (async () => {
        const ok = await window.omiOverlay?.setAccelerator(next)
        if (ok) {
          setAccel(next)
          setPreferences({ overlayShortcut: next })
          setWorked(false)
          setError(null)
          setRecording(false)
        } else {
          // Another app already owns it (registration failed; main rolled back).
          setError('That shortcut is already in use — try another.')
          setRecording(false)
        }
      })()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [recording])

  const startCustom = (): void => {
    setError(null)
    setWorked(false)
    window.omiOverlay?.suspendShortcut()
    setRecording(true)
  }

  // Leaving the step — via Continue or Skip — always persists the current
  // accelerator (the default if the user never changed it), so the floating bar
  // is guaranteed to have a saved shortcut even when this screen is skipped.
  const leaveWith = (done?: () => void): void => {
    setPreferences({ overlayShortcut: accel })
    done?.()
  }

  const tokens = acceleratorToTokens(accel)

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      title={'Let’s set your “Ask a question” shortcut'}
      subtitle="Press this key combination. Do buttons light up?"
      subtitleClassName="text-white"
      align="center"
      // Continue only appears once the floating bar has actually been summoned
      // (default or custom combo). Skip stays available as an escape hatch and
      // still saves the default shortcut so the bar always has one.
      onContinue={worked ? () => leaveWith(onContinue) : undefined}
      onSkip={onSkip ? () => leaveWith(onSkip) : undefined}
    >
      {/* Keycap test box */}
      <div className="mt-2 flex w-full max-w-[420px] flex-col items-center gap-3 rounded-2xl border border-white/5 bg-white/[0.03] px-6 py-8">
        {recording ? (
          <div className="flex h-[52px] items-center text-sm text-white/60">
            Recording… press your keys{' '}
            <span className="ml-2 text-white/35">(Esc to cancel)</span>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            {tokens.map((t, i) => (
              <kbd
                key={`${t}-${i}`}
                className={
                  'flex h-[52px] min-w-[52px] items-center justify-center rounded-xl px-3 text-sm font-semibold transition-all duration-150 ' +
                  (lit
                    ? 'bg-[color:var(--accent)] text-white shadow-[0_0_24px_4px_rgba(91,2,224,0.55)]'
                    : 'bg-white/[0.08] text-white/85')
                }
              >
                {t}
              </kbd>
            ))}
          </div>
        )}
        <p className={'text-xs ' + (error ? 'text-amber-400' : 'text-white/40')}>
          {/* No success line — a successful test just reveals Continue. The
              non-breaking space when worked keeps the box from shifting height. */}
          {error ?? (worked ? ' ' : 'Press to test')}
        </p>
      </div>

      {/* Choose a different shortcut */}
      <div className="mt-6 flex flex-col items-center gap-2">
        <p className="text-sm leading-relaxed text-white">Choose a different shortcut</p>
        <button
          type="button"
          onClick={startCustom}
          disabled={recording}
          className={
            'rounded-xl border border-white/10 px-5 py-2.5 text-sm font-medium transition-colors ' +
            (recording
              ? 'cursor-not-allowed bg-white/[0.04] text-white/40'
              : 'bg-white/[0.06] text-white/80 hover:bg-white/[0.1]')
          }
        >
          {recording ? 'Recording…' : 'Custom'}
        </button>
      </div>
    </StepScaffold>
  )
}
