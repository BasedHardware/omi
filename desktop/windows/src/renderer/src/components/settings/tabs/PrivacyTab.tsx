import { useState } from 'react'
import { ShieldCheck, Zap } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

export function PrivacyTab(): React.JSX.Element {
  // Desktop-automation opt-in. The toggle writes the same `automationConsentedAt`
  // preference the onboarding Automation step sets; useChat gates its action
  // planner on it. `OMI_AUTOMATION=0` is a hard build kill-switch (exposed as
  // automationEnabled) — when off, the feature can't run, so the toggle is shown
  // disabled regardless of consent.
  const automationAvailable = window.omi.automationEnabled
  const [autoConsent, setAutoConsent] = useState<boolean>(!!getPreferences().automationConsentedAt)
  const toggleAutomation = (on: boolean): void => {
    setAutoConsent(on)
    setPreferences({ automationConsentedAt: on ? Date.now() : undefined })
  }

  return (
    <>
      <SettingRow
        icon={Zap}
        dot={automationAvailable && autoConsent ? 'on' : 'off'}
        title="Let Omi take actions"
        subtitle={
          !automationAvailable
            ? 'Disabled in this build.'
            : autoConsent
              ? 'Omi can click and type in your apps when you ask — you approve each action first.'
              : 'Turn on to let Omi act in your apps when you ask (you approve each action first).'
        }
        keywords="automation actions desktop control agent take action flaui approve"
        control={
          <Toggle
            on={automationAvailable && autoConsent}
            onChange={toggleAutomation}
            disabled={!automationAvailable}
            label="Let Omi take actions"
          />
        }
      />
      <SettingRow
        icon={ShieldCheck}
        title="On-device by default"
        subtitle="Your screen timeline, file index, and app usage stay on this PC. Only synthesized facts (memories) are sent to your Omi account, and only for features you turn on."
        keywords="privacy local data on-device cloud"
      />
    </>
  )
}
