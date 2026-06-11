import { useEffect, useState } from 'react'
import { Activity, ShieldCheck, Zap } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import type { UsageSettings } from '../../../../../shared/types'

const RETENTION_OPTIONS: ReadonlyArray<{ days: number; label: string }> = [
  { days: 30, label: '30 days' },
  { days: 45, label: '45 days (recommended)' },
  { days: 60, label: '60 days' },
  { days: 90, label: '90 days' },
  { days: 180, label: '180 days' }
]

export function PrivacyTab(): React.JSX.Element {
  const [usage, setUsage] = useState<UsageSettings | null>(null)
  useEffect(() => {
    window.omi.usageGetSettings().then(setUsage).catch(() => setUsage(null))
  }, [])
  const saveUsage = async (next: UsageSettings): Promise<void> => {
    setUsage(await window.omi.usageSetSettings(next))
  }

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
        icon={Activity}
        dot={usage?.enabled ? 'on' : 'off'}
        title="App-usage tracking"
        subtitle="Records which apps you actively use (app name only, never window titles) — locally — to improve memory ranking."
        keywords="usage foreground app tracking privacy"
        control={
          <Toggle
            on={!!usage?.enabled}
            onChange={(on) => usage && void saveUsage({ ...usage, enabled: on })}
            disabled={!usage}
            label="App-usage tracking"
          />
        }
      >
        {usage?.enabled && (
          <label className="flex items-center gap-2 text-sm text-text-secondary">
            <span>Forget apps not used in</span>
            <select
              value={usage.retentionDays}
              onChange={(e) => void saveUsage({ ...usage, retentionDays: Number(e.target.value) })}
              className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white focus:outline-none"
            >
              {RETENTION_OPTIONS.map((o) => (
                <option key={o.days} value={o.days} className="bg-neutral-900">
                  {o.label}
                </option>
              ))}
            </select>
          </label>
        )}
      </SettingRow>
      <SettingRow
        icon={ShieldCheck}
        title="On-device by default"
        subtitle="Your screen timeline, file index, and app usage stay on this PC. Only synthesized facts (memories) are sent to your Omi account, and only for features you turn on."
        keywords="privacy local data on-device cloud"
      />
    </>
  )
}
