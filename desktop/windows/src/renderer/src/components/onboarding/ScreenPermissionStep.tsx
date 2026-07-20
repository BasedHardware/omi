import { Monitor } from 'lucide-react'
import { PermissionStep } from './PermissionStep'
import { rewind } from '../../lib/native'
import { toast } from '../../lib/toast'

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
  const requestAccess = async (): Promise<boolean> => {
    try {
      const capability = await rewind.requestCapturePermission()
      if (!capability.supported) {
        alert(capability.reason)
        return false
      }
      const current = await rewind.getSettings()
      if (!current.captureEnabled) {
        await rewind.setSettings({ ...current, captureEnabled: true })
      }
      return true
    } catch (error) {
      toast('Could not request Screen Recording permission', {
        tone: 'error',
        body: (error as Error).message
      })
      return false
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
        waiting: 'Waiting for permission',
        granted: 'Granted'
      }}
      buttonLabel={{
        idle: 'Grant access',
        waiting: 'Waiting for permission',
        granted: 'Granted'
      }}
      onActivate={requestAccess}
      onContinue={onContinue}
      onSkip={onSkip}
    />
  )
}
