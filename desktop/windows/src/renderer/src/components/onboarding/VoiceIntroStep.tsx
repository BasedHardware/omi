import { useEffect, useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { getPreferences } from '../../lib/preferences'
import { DEFAULT_OVERLAY_ACCELERATOR, acceleratorToTokens } from '../../lib/overlayShortcut'

type VoiceIntroStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
  onSkip?: () => void
}

/**
 * Onboarding step that teaches talking to the floating bar. It watches the
 * overlay's open/focused state: while the bar is closed it tells the user to
 * press their chosen hotkey; once the bar is active it asks them to hold Space
 * and speak. Continue appears only after a real push-to-talk capture completes.
 */
export function VoiceIntroStep({
  stepIndex,
  totalSteps,
  onContinue,
  onSkip
}: VoiceIntroStepProps): React.JSX.Element {
  const [active, setActive] = useState(false)
  const [captured, setCaptured] = useState(false)

  const hotkeyTokens = acceleratorToTokens(
    getPreferences().overlayShortcut ?? DEFAULT_OVERLAY_ACCELERATOR
  )

  useEffect(() => {
    // The bar should already be enabled/warm from the shortcut step; ensure it.
    window.omiOverlay?.setEnabled(true)
    const offVis = window.omiOverlay?.onVisibilityChange((s) => setActive(s.active))
    const offVoice = window.omiOverlay?.onVoiceCaptured(() => setCaptured(true))
    return () => {
      offVis?.()
      offVoice?.()
    }
  }, [])

  const subtitle = active
    ? 'Hold the Space key and speak.'
    : 'Press your shortcut to open Omi.'

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      title="Talk to Omi"
      subtitle={subtitle}
      subtitleClassName="text-white"
      align="center"
      // Continue appears only once a hold-Space capture has actually happened.
      onContinue={captured ? onContinue : undefined}
      onSkip={onSkip}
    >
      <div className="mt-2 flex w-full max-w-[420px] flex-col items-center gap-4 rounded-2xl border border-white/5 bg-white/[0.03] px-6 py-9">
        {active ? (
          // Bar is open + focused → hold-Space prompt.
          <>
            <kbd className="flex h-[56px] min-w-[150px] items-center justify-center rounded-xl bg-white/[0.08] px-6 text-sm font-semibold text-white/85">
              Hold Space
            </kbd>
            <p className="text-sm text-white/55">
              Try asking: <span className="text-white/80">“What’s on my screen?”</span>
            </p>
          </>
        ) : (
          // Bar closed → press the chosen hotkey to open it.
          <div className="flex items-center gap-2">
            {hotkeyTokens.map((t, i) => (
              <kbd
                key={`${t}-${i}`}
                className="flex h-[52px] min-w-[52px] items-center justify-center rounded-xl bg-white/[0.08] px-3 text-sm font-semibold text-white/85"
              >
                {t}
              </kbd>
            ))}
          </div>
        )}
      </div>
    </StepScaffold>
  )
}
