import { useEffect, useState } from 'react'
import { Activity, Eye, Lightbulb, Target } from 'lucide-react'
import type { InsightRecord, InsightSettings } from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { StatusTile } from '../StatusTile'
import { Toggle } from '../Toggle'

export function FocusInsightsTab(): React.JSX.Element {
  const [focusEnabled, setFocusEnabled] = useState<boolean>(!!getPreferences().focusModeEnabled)
  const [focusLabel, setFocusLabel] = useState<string>(getPreferences().focusModeLabel ?? '')
  const [insightSettings, setInsightSettings] = useState<InsightSettings | null>(null)
  const [recent, setRecent] = useState<InsightRecord[]>([])

  useEffect(() => {
    void window.omi.insightGetSettings().then(setInsightSettings)
    void window.omi.insightRecent(5).then(setRecent)
  }, [])

  const toggleFocus = (enabled: boolean): void => {
    setFocusEnabled(enabled)
    setPreferences({ focusModeEnabled: enabled })
  }

  const saveFocusLabel = (label: string): void => {
    setFocusLabel(label)
    setPreferences({ focusModeLabel: label.trim() || undefined })
  }

  const patchInsight = async (patch: Partial<InsightSettings>): Promise<void> => {
    setInsightSettings(await window.omi.insightSetSettings(patch))
  }

  return (
    <>
      <SettingRow
        icon={Target}
        dot={focusEnabled ? 'on' : 'off'}
        title="Focus mode"
        subtitle="Track the current focus state in the Windows shell without adding a separate macOS-style page."
        keywords="focus mode status insights proactive shell decision"
        control={<Toggle on={focusEnabled} onChange={toggleFocus} label="Focus mode" />}
      >
        <input
          value={focusLabel}
          onChange={(event) => saveFocusLabel(event.target.value)}
          placeholder="What are you focusing on?"
          className="w-full rounded-lg border border-white/[0.08] bg-black/20 px-3 py-2 text-sm text-white placeholder:text-white/35 focus:border-white/25 focus:outline-none"
        />
      </SettingRow>

      <SettingRow
        icon={Lightbulb}
        dot={insightSettings?.enabled ? 'on' : 'off'}
        title="Proactive insights"
        subtitle="Insights remain powered by Rewind screen activity and can surface as Omi or Windows notifications."
        keywords="insights proactive focus history rewind notifications"
        control={
          <Toggle
            on={!!insightSettings?.enabled}
            onChange={(enabled) => void patchInsight({ enabled })}
            disabled={!insightSettings}
            label="Proactive insights"
          />
        }
      >
        <div className="grid gap-2 sm:grid-cols-3">
          <StatusTile
            label="Delivery"
            value={insightSettings?.notificationStyle === 'native' ? 'Windows' : 'Omi'}
            tone="neutral"
          />
          <StatusTile
            label="Cadence"
            value={insightSettings ? `${insightSettings.intervalMin} min` : 'Checking'}
            tone="neutral"
          />
          <StatusTile
            label="Last run"
            value={
              insightSettings?.lastRunAt
                ? new Date(insightSettings.lastRunAt).toLocaleString()
                : 'Not run yet'
            }
            tone={insightSettings?.lastRunAt ? 'good' : 'neutral'}
          />
        </div>
      </SettingRow>

      <SettingRow
        icon={Activity}
        title="Insight history"
        subtitle="Recent proactive insights generated on this PC."
        keywords="insight history status focus assistant"
      >
        {recent.length > 0 ? (
          <ul className="space-y-2">
            {recent.map((item) => (
              <li key={item.id} className="rounded-lg border border-white/[0.08] bg-black/15 p-3">
                <div className="text-sm font-semibold text-white/85">{item.headline}</div>
                <div className="mt-1 text-xs leading-relaxed text-white/55">{item.advice}</div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-white/45">No insights recorded yet.</div>
        )}
      </SettingRow>

      <SettingRow
        icon={Eye}
        title="Where this lives"
        subtitle="Windows keeps Focus and Insights inside Settings/Rewind instead of adding more top-level navigation."
        keywords="decision redesign parity focus insights navigation"
      />
    </>
  )
}
