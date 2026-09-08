import { useEffect, useRef, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { getPreferences } from '../../lib/preferences'
import { DEFAULT_OVERLAY_ACCELERATOR, acceleratorToTokens } from '../../lib/overlayShortcut'

type VoiceIntroStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

/** How long the step waits, with nothing at all coming back, before it unlocks
 *  Continue anyway. A detector that can fail silently must never be the only way
 *  forward — a user who did the right thing and got nothing still gets out. */
export const VOICE_STEP_FALLBACK_MS = 20_000
/** After the hotkey is heard but no capture follows, the gesture was almost
 *  certainly a TAP (which summons the bar but records nothing). Nudge them to
 *  hold. Long enough that a real hold + transcription doesn't trip it. */
export const VOICE_STEP_NUDGE_MS = 8_000

/**
 * Onboarding step that teaches talking to the bar.
 *
 * The ONLY gesture that records is HOLDING the summon chord: main's summon
 * gesture (main/bar/gesture.ts) classifies a press under 350ms as a 'tap', which
 * peeks the pill and records nothing, and only a 'hold' drives push-to-talk. So
 * this step tells the user to HOLD, and reveals Continue when a real capture
 * completes (`overlay:voiceCaptured`, emitted by the bar's PTT machine at the end
 * of every hold — even a silent or failed one, because the gesture is what we're
 * teaching).
 *
 * Two things it must NOT do, both of which shipped and stranded users on this
 * screen with no Continue button:
 *   - Tell the user to "press" the shortcut. A tap can never satisfy the gate.
 *   - Branch on `overlay:visibility.active`. The peek/PTT pill is deliberately
 *     non-focusable, so `active` is only ever true for the EXPANDED bar; the
 *     hold-Space copy behind it was dead code, and Space typed into this window
 *     anyway.
 *
 * Escape hatches, because voice can genuinely fail: a mic Windows is blocking, a
 * capture that errors, or a detector that simply never fires all unlock Continue
 * with an explanation.
 */
export function VoiceIntroStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: VoiceIntroStepProps): React.JSX.Element {
  const [captured, setCaptured] = useState(false)
  // The hotkey reached main at least once (fires for a tap AND a hold).
  const [summoned, setSummoned] = useState(false)
  const [nudge, setNudge] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const [micBlocked, setMicBlocked] = useState(false)
  const [waited, setWaited] = useState(false)
  const nudgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const hotkeyTokens = acceleratorToTokens(
    getPreferences().overlayShortcut ?? DEFAULT_OVERLAY_ACCELERATOR
  )

  useEffect(() => {
    // The bar should already be enabled/warm from the shortcut step; ensure it.
    window.omiOverlay?.setEnabled(true)
    const offVoice = window.omiOverlay?.onVoiceCaptured(() => {
      setCaptured(true)
      setNudge(false)
      setFailure(null)
    })
    const offFail = window.omiOverlay?.onVoiceFailed((message) => setFailure(message || null))
    const offSummon = window.omiOverlay?.onSummoned(() => {
      setSummoned(true)
      // A tap summons the bar and records nothing. If no capture lands soon after
      // the hotkey fires, say so — silence here is what made the step feel broken.
      if (nudgeTimer.current) clearTimeout(nudgeTimer.current)
      nudgeTimer.current = setTimeout(() => setNudge(true), VOICE_STEP_NUDGE_MS)
    })
    const fallback = setTimeout(() => setWaited(true), VOICE_STEP_FALLBACK_MS)
    return () => {
      offVoice?.()
      offFail?.()
      offSummon?.()
      clearTimeout(fallback)
      if (nudgeTimer.current) clearTimeout(nudgeTimer.current)
    }
  }, [])

  // Windows can be blocking the mic outright (the real consent state, read from
  // the Capability Access Manager — never Chromium's, which lies). Voice cannot
  // work at all in that case, so say it plainly and let the user move on.
  useEffect(() => {
    let alive = true
    void (async () => {
      try {
        const state = await window.omi?.getMicPermissionState?.()
        if (alive) setMicBlocked(state === 'denied')
      } catch {
        // Unreadable consent state — stay quiet and let the capture path speak.
      }
    })()
    return () => {
      alive = false
    }
  }, [])

  // Continue is a real gate — but never a dead end. It opens on a capture, and
  // also on any state where we know voice can't (or didn't) work: a blocked mic,
  // a failed capture, or nothing at all after VOICE_STEP_FALLBACK_MS.
  const stuck = micBlocked || !!failure || waited
  const canContinue = captured || stuck

  const problem = micBlocked
    ? 'Windows is blocking Omi’s microphone, so voice can’t work yet. You can fix this later in Settings → Privacy.'
    : failure

  const subtitle = captured
    ? 'That’s it — Omi heard you.'
    : `Hold ${hotkeyTokens.join(' + ')}, ask a question, then let go.`

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      title="Talk to Omi"
      subtitle={subtitle}
      subtitleClassName="text-white"
      align="center"
      onContinue={canContinue ? onContinue : undefined}
      onSkip={onSkip}
    >
      <div className="mt-2 flex w-full max-w-[420px] flex-col items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.03] px-6 py-9">
        <div className="flex items-center gap-2">
          <span className="mr-1 text-sm font-medium text-white/50">Hold</span>
          {hotkeyTokens.map((t, i) => (
            <kbd
              key={`${t}-${i}`}
              className={
                'flex h-[52px] min-w-[52px] items-center justify-center rounded-xl px-3 text-sm font-semibold transition-colors ' +
                (captured
                  ? 'bg-white text-black'
                  : summoned
                    ? 'bg-white/20 text-white'
                    : 'bg-white/[0.08] text-white/85')
              }
            >
              {t}
            </kbd>
          ))}
        </div>
        <p className="text-sm text-white/55">
          Try asking: <span className="text-white/80">“What’s on my screen?”</span>
        </p>
      </div>

      {/* One line of state, in priority order: what broke → why nothing happened
          → the way out. Never an empty screen with a missing button. */}
      {problem ? (
        <p className="mt-4 max-w-[420px] text-sm text-amber-400">{problem}</p>
      ) : nudge && !captured ? (
        <p className="mt-4 max-w-[420px] text-sm text-white/55">
          Keep the keys held down while you speak — a quick press just opens Omi. Let go when you’re
          done.
        </p>
      ) : waited && !captured ? (
        <p className="mt-4 max-w-[420px] text-sm text-white/55">
          Can’t get it to work? Continue — you can try this any time from the bar.
        </p>
      ) : null}
    </StepScaffold>
  )
}
