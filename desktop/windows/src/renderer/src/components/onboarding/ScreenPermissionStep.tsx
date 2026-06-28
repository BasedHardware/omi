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
  // Placeholder grant: the real Windows permission request will be wired when the
  // screen engine is built. Until then we simulate the OS round-trip, then turn on
  // Rewind screen capture so granting "Screen Recording" actually starts the local
  // screen timeline (the Settings "Capture my screen" toggle). Best-effort — a
  // failure here must never block onboarding.
  const requestAccess = async (): Promise<void> => {
    await new Promise((resolve) => setTimeout(resolve, 1500))
    try {
      const current = await window.omi.rewindGetSettings()
      if (!current.captureEnabled) {
        await window.omi.rewindSetSettings({ ...current, captureEnabled: true })
      }
    } catch {
      /* leave capture off; the user can enable it from Settings */
    }
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="PERMISSION"
      title="Let Omi read your screen"
      icon={<Monitor className="h-5 w-5 text-white/60" />}
      cardLabel="Screen Recording"
      statusText={{
        idle: 'Not granted yet',
        waiting: 'Waiting for Windows',
        granted: 'Granted'
      }}
      buttonLabel={{
        idle: 'Grant access',
        waiting: 'Waiting for Windows',
        granted: 'Granted'
      }}
      onActivate={requestAccess}
      onContinue={onContinue}
      onSkip={onSkip}
    />
  )
}
