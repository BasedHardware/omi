import { Zap } from 'lucide-react'
import { getPreferences, setPreferences } from '../../lib/preferences'
import { PermissionStep } from './PermissionStep'

type AutomationPermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
  onBack?: () => void
  onSkip?: () => void
}

export function AutomationPermissionStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue,
  onBack,
  onSkip
}: AutomationPermissionStepProps): React.JSX.Element {
  // Automation has no OS permission prompt (Windows UIA needs no grant) — enabling it
  // is a local opt-in that records consent, so what `checkGranted` reads below is that
  // consent, not an OS state. useChat's action-planner pre-step gates on this preference
  // (alongside the OMI_AUTOMATION env kill-switch), so flipping it on here is what
  // actually lets Omi take real UI actions in your apps.
  const enableAutomation = async (): Promise<void> => {
    setPreferences({ automationConsentedAt: Date.now() })
  }

  // The consent already recorded (a resumed or repeated onboarding). Reading it keeps the
  // card honest — "Enabled", not "Not enabled yet" — and, because a detected state never
  // auto-advances, the user still confirms with Continue rather than watching the step
  // flash by.
  const isConsented = async (): Promise<boolean> =>
    typeof getPreferences().automationConsentedAt === 'number'

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
        granted: 'Enabled',
        denied: "Couldn't enable"
      }}
      buttonLabel={{
        idle: 'Enable',
        waiting: 'Enabling',
        granted: 'Enabled',
        denied: 'Try again'
      }}
      onActivate={enableAutomation}
      checkGranted={isConsented}
      onContinue={onContinue}
      onBack={onBack}
      onSkip={onSkip}
    />
  )
}
