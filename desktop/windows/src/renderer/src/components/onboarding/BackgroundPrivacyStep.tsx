import { useState } from 'react'
import { StepScaffold } from './StepScaffold'
import { getPreferences } from '../../lib/preferences'
import { persistBackgroundConsent } from '../../lib/backgroundConsent'
import { BackgroundConsentControls } from '../consent/BackgroundConsentControls'

type BackgroundPrivacyStepProps = {
  stepIndex: number
  totalSteps: number
  onContinue: () => void
}

/**
 * Onboarding step establishing the background/privacy posture for new users:
 * always-on listening, tray residence, and launch-at-login. New users default to
 * listening ON (Omi's core behavior) and launch-at-login ON; either can be turned
 * off here before continuing. Persists the choices and stamps recordingConsentedAt
 * when the user proceeds with listening enabled.
 */
export function BackgroundPrivacyStep({
  stepIndex,
  totalSteps,
  onContinue
}: BackgroundPrivacyStepProps): React.JSX.Element {
  const [listening, setListening] = useState(() => getPreferences().continuousRecording ?? true)
  const [launchAtLogin, setLaunchAtLogin] = useState(true)

  const handleContinue = (): void => {
    persistBackgroundConsent({ listening, launchAtLogin })
    onContinue()
  }

  return (
    <StepScaffold
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      eyebrow="BACKGROUND & PRIVACY"
      title="How Omi runs on your PC"
      widthClassName="max-w-[440px]"
      onContinue={handleContinue}
    >
      <p className="text-center text-sm leading-relaxed text-white">
        Omi works best as a quiet companion running in the background. You’re in control — change
        any of this now or later in Settings.
      </p>
      <div className="mt-6 w-full">
        <BackgroundConsentControls
          listening={listening}
          onListeningChange={setListening}
          launchAtLogin={launchAtLogin}
          onLaunchAtLoginChange={setLaunchAtLogin}
        />
      </div>
    </StepScaffold>
  )
}
