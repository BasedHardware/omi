import { Zap } from 'lucide-react'
import { setPreferences } from '../../lib/preferences'
import { PermissionStep } from './PermissionStep'

type AutomationPermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
  onSkip?: () => void
}

export function AutomationPermissionStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue,
  onSkip
}: AutomationPermissionStepProps): React.JSX.Element {
  // Automation has no OS permission prompt — granting it is a local opt-in that
  // records consent. useChat's action-planner pre-step gates on this preference
  // (alongside the OMI_AUTOMATION env kill-switch), so flipping it on here is what
  // actually lets Omi take real UI actions in your apps.
  const enableAutomation = async (): Promise<void> => {
    setPreferences({ automationConsentedAt: Date.now() })
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="PERMISSION"
      title="Let Omi act when asked"
      subtitle="Automation lets Omi take actions for you"
      icon={<Zap className="h-5 w-5 text-white/60" />}
      cardLabel="Automation"
      statusText={{
        idle: 'Not enabled yet',
        waiting: 'Enabling',
        granted: 'Enabled'
      }}
      buttonLabel={{
        idle: 'Automation',
        waiting: 'Enabling',
        granted: 'Enabled'
      }}
      onActivate={enableAutomation}
      onContinue={onContinue}
      onSkip={onSkip}
    />
  )
}
