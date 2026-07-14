import { Monitor } from 'lucide-react'
import { PermissionStep } from './PermissionStep'

type ScreenPermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
  onSkip?: () => void
}

export function ScreenPermissionStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue,
  onSkip
}: ScreenPermissionStepProps): React.JSX.Element {
  // Windows has NO OS consent prompt for desktop capture (unlike macOS Screen
  // Recording), so this is an honest opt-in, not a permission request: it turns
  // on Omi's local screen timeline (the Settings "Capture my screen" toggle).
  // No fake OS round-trip. If the write fails we say so and let the user retry or
  // skip; we never claim it's on when it isn't.
  const enableCapture = async (): Promise<void> => {
    try {
      const current = await window.omi.rewindGetSettings()
      if (!current.captureEnabled) {
        await window.omi.rewindSetSettings({ ...current, captureEnabled: true })
      }
    } catch {
      throw new Error(
        "Couldn't turn on screen capture. You can enable it any time in Settings → Rewind."
      )
    }
  }

  // Rewind capture defaults to ON (rewindSettings.ts DEFAULTS), so by the time this step
  // renders the screen is very likely ALREADY being captured. The step used to hard-code
  // an "Off" card with a "Turn on" button that did nothing, and Skip walked past it —
  // leaving capture running while the user believed they had declined. Read the real
  // setting instead, and make Skip mean what it says.
  const isCaptureOn = async (): Promise<boolean> =>
    (await window.omi.rewindGetSettings()).captureEnabled

  // Skip on this step is an explicit "no": turn capture off. Best-effort — a failed
  // write must not trap the user on the step, but it must not silently pass as consent
  // either, so the failure is surfaced and the step still advances.
  const declineCapture = (advance: () => void): void => {
    void (async () => {
      try {
        const current = await window.omi.rewindGetSettings()
        if (current.captureEnabled) {
          await window.omi.rewindSetSettings({ ...current, captureEnabled: false })
        }
      } catch (e) {
        console.warn('[onboarding] failed to disable screen capture on skip:', e)
      }
      advance()
    })()
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="SCREEN"
      title="Let Omi read your screen"
      subtitle="Omi keeps a private, local timeline of what's on your screen. It stays on this device, and you can turn it off any time in Settings."
      icon={<Monitor className="h-5 w-5 text-white/60" />}
      cardLabel="Screen capture"
      statusText={{
        idle: 'Off',
        waiting: 'Turning on',
        granted: 'On',
        denied: "Couldn't turn on"
      }}
      buttonLabel={{
        idle: 'Turn on',
        waiting: 'Turning on',
        granted: 'On',
        denied: 'Try again'
      }}
      onActivate={enableCapture}
      checkGranted={isCaptureOn}
      onContinue={onContinue}
      onSkip={onSkip ? () => declineCapture(onSkip) : undefined}
    />
  )
}
