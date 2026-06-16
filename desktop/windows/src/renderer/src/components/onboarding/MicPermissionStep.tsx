import { Mic } from 'lucide-react'
import { PermissionStep } from './PermissionStep'
import { setPreferences } from '../../lib/preferences'

type MicPermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
  onSkip?: () => void
}

export function MicPermissionStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue,
  onSkip
}: MicPermissionStepProps): React.JSX.Element {
  // Trigger the real Windows microphone grant. getUserMedia surfaces the OS
  // prompt; we immediately release the device since we only needed the grant.
  const requestAccess = async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
      // Granting the mic opts into always-on listening — continuous recording is on
      // from here (the background host starts streaming once onboarding completes).
      // One step, no separate continuous-recording screen; toggle it off anytime via
      // the sidebar mic switch or Settings.
      setPreferences({ continuousRecording: true })
    } catch (e) {
      const err = e as Error
      const hint =
        err.name === 'NotAllowedError'
          ? '\n\nWindows blocked microphone access. Open Settings → Privacy & security → Microphone and allow this app.'
          : ''
      alert(`Microphone access failed: ${err.message}${hint}`)
    }
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="PERMISSION"
      title="Let Omi use your mic"
      subtitle="This lets Omi transcribe meetings and voice notes"
      icon={<Mic className="h-5 w-5 text-white/60" />}
      cardLabel="Microphone"
      statusText={{
        idle: 'Not granted yet',
        waiting: 'Waiting for Windows',
        granted: 'Granted'
      }}
      buttonLabel={{
        idle: 'Microphone',
        waiting: 'Waiting for Windows',
        granted: 'Granted'
      }}
      onActivate={requestAccess}
      onContinue={onContinue}
      onSkip={onSkip}
    />
  )
}
