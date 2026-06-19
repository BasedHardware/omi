import { useEffect, useState } from 'react'
import { Bell, Lightbulb, Mic } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { getPreferences, onPreferencesChange, setPreferences } from '../../../lib/preferences'
import type { InsightSettings } from '../../../../../shared/types'

const INSIGHT_INTERVALS = [15, 20, 30, 60]

export function NotificationsTab(): React.JSX.Element {
  const [insight, setInsight] = useState<InsightSettings | null>(null)
  const [notifRecording, setNotifRecording] = useState<boolean>(
    () => getPreferences().notifyOnRecordingSaved ?? true
  )

  useEffect(() => {
    void window.omi.insightGetSettings().then(setInsight)
    return onPreferencesChange((p) => setNotifRecording(p.notifyOnRecordingSaved ?? true))
  }, [])

  const patchInsight = async (patch: Partial<InsightSettings>): Promise<void> => {
    const next = await window.omi.insightSetSettings(patch)
    setInsight(next)
  }

  return (
    <>
      {/* Insight notifications (moved from Rewind tab) */}
      <SettingRow
        icon={Lightbulb}
        dot={insight?.enabled ? 'on' : 'off'}
        title="Proactive insights"
        subtitle="Periodically reviews recent screen activity and surfaces one useful insight. Requires Rewind screen capture to be enabled."
        keywords="insight notification toast gemini suggestion"
        control={
          <Toggle
            on={!!insight?.enabled}
            onChange={(on) => void patchInsight({ enabled: on })}
            disabled={!insight}
            label="Proactive insights"
          />
        }
      >
        {insight && (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              Check every
              <select
                value={INSIGHT_INTERVALS.includes(insight.intervalMin) ? insight.intervalMin : 15}
                onChange={(e) => void patchInsight({ intervalMin: Number(e.target.value) })}
                className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
              >
                {INSIGHT_INTERVALS.map((m) => (
                  <option key={m} value={m} className="bg-neutral-900">
                    {m} minutes
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              Notification style
              <select
                value={insight.notificationStyle}
                onChange={(e) =>
                  void patchInsight({ notificationStyle: e.target.value as 'omi' | 'native' })
                }
                className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
              >
                <option value="omi" className="bg-neutral-900">
                  Omi notification
                </option>
                <option value="native" className="bg-neutral-900">
                  Windows notification
                </option>
              </select>
            </label>
            <button onClick={() => window.omi.insightTest()} className="btn-ghost self-start">
              Send a test notification
            </button>
            <textarea
              rows={2}
              placeholder="Privacy denylist — one keyword per line (e.g. therapy, salary)"
              defaultValue={insight.denylist.join('\n')}
              onBlur={(e) =>
                void patchInsight({
                  denylist: e.target.value
                    .split('\n')
                    .map((s) => s.trim())
                    .filter(Boolean)
                })
              }
              className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
            />
          </div>
        )}
      </SettingRow>

      {/* Recording-saved notification */}
      <SettingRow
        icon={Mic}
        dot={notifRecording ? 'on' : 'off'}
        title="Recording saved"
        subtitle="Show a Windows notification when a recording session finishes and the conversation is saved."
        keywords="recording saved notification mic conversation done"
        control={
          <Toggle
            on={notifRecording}
            onChange={(on) => {
              setNotifRecording(on)
              setPreferences({ notifyOnRecordingSaved: on })
            }}
            label="Recording saved"
          />
        }
      />

      {/* Frequency note */}
      <SettingRow
        icon={Bell}
        title="Notification frequency"
        subtitle="Insight notifications are throttled to avoid interrupting focus — adjust the interval above. Recording notifications are always shown once per session."
        keywords="frequency throttle rate limit"
      />
    </>
  )
}
