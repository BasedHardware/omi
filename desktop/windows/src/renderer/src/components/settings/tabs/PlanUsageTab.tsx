import { useEffect, useState } from 'react'
import { Activity, CreditCard } from 'lucide-react'
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

export function PlanUsageTab(): React.JSX.Element {
  const [usage, setUsage] = useState<UsageSettings | null>(null)

  useEffect(() => {
    window.omi
      .usageGetSettings()
      .then(setUsage)
      .catch(() => setUsage(null))
  }, [])

  const saveUsage = async (next: UsageSettings): Promise<void> => {
    setUsage(await window.omi.usageSetSettings(next))
  }

  return (
    <>
      <SettingRow
        icon={CreditCard}
        title="Omi account plan"
        subtitle="Desktop chat and transcription access use the plan attached to your signed-in Omi account."
        keywords="plan usage subscription billing account quota credits upgrade checkout"
      />
      <SettingRow
        icon={Activity}
        dot={usage?.enabled ? 'on' : 'off'}
        title="App-usage tracking"
        subtitle="Records which apps you actively use (app name only, never window titles) locally to improve memory ranking."
        keywords="usage foreground app tracking plan usage privacy"
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
    </>
  )
}
