import { useEffect, useState } from 'react'
import { BellRing, Brain, CalendarClock, Lightbulb, ListChecks, Send, Target } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { toast } from '../../../lib/toast'
import type {
  WindowsNotificationSettings,
  WindowsNotificationSettingsPatch,
  WindowsNotificationTestResult
} from '../../../../../shared/types'

const INSIGHT_INTERVALS = [15, 20, 30, 60]
const HOURS = Array.from({ length: 24 }, (_value, hour) => hour)

function formatHour(hour: number): string {
  const normalized = ((hour + 11) % 12) + 1
  return `${normalized} ${hour < 12 ? 'AM' : 'PM'}`
}

function resultToast(result: WindowsNotificationTestResult): void {
  if (result.ok) {
    toast('Test notification sent', { tone: 'success' })
  } else {
    toast('Test notification was not sent', { tone: 'warn', body: result.reason })
  }
}

export function NotificationsTab(): React.JSX.Element {
  const [settings, setSettings] = useState<WindowsNotificationSettings | null>(null)
  const [testing, setTesting] = useState(false)

  useEffect(() => {
    void window.omi.notificationsGetSettings().then(setSettings)
  }, [])

  const patchSettings = async (patch: WindowsNotificationSettingsPatch): Promise<void> => {
    setSettings(await window.omi.notificationsSetSettings(patch))
  }

  const sendSystemTest = async (): Promise<void> => {
    if (testing) return
    setTesting(true)
    try {
      resultToast(await window.omi.notificationsTest('system'))
    } finally {
      setTesting(false)
    }
  }

  const sendInsightTest = (): void => {
    window.omi.insightTest()
    toast('Insight test requested', { tone: 'info' })
  }

  return (
    <>
      <h2 className="section-label mb-2">Native alerts</h2>
      <SettingRow
        icon={BellRing}
        dot={settings?.nativeEnabled ? 'on' : 'off'}
        title="Windows system notifications"
        subtitle="Use native Windows notifications for categories that choose system delivery."
        keywords="notifications native windows system action center master toggle test"
        control={
          <Toggle
            on={!!settings?.nativeEnabled}
            onChange={(on) => void patchSettings({ nativeEnabled: on })}
            disabled={!settings}
            label="Windows system notifications"
          />
        }
      >
        <button
          onClick={() => void sendSystemTest()}
          disabled={!settings || testing}
          className="btn-ghost inline-flex items-center gap-2 disabled:opacity-40"
        >
          <Send className="h-4 w-4" />
          {testing ? 'Sending...' : 'Send test'}
        </button>
      </SettingRow>

      <h2 className="section-label mb-2 mt-8">Proactive assistants</h2>
      <SettingRow
        icon={Target}
        dot={settings?.focus.enabled ? 'on' : 'off'}
        title="Focus notifications"
        subtitle="Show a notification when Omi detects a focus change worth surfacing."
        keywords="focus notification alert assistant attention distraction productive"
        control={
          <Toggle
            on={!!settings?.focus.enabled}
            onChange={(on) => void patchSettings({ focus: { enabled: on } })}
            disabled={!settings}
            label="Focus notifications"
          />
        }
      />
      <SettingRow
        icon={ListChecks}
        dot={settings?.tasks.enabled ? 'on' : 'off'}
        title="Task notifications"
        subtitle="Show a notification when Omi extracts a task."
        keywords="task notifications action item todo extracted reminder"
        control={
          <Toggle
            on={!!settings?.tasks.enabled}
            onChange={(on) => void patchSettings({ tasks: { enabled: on } })}
            disabled={!settings}
            label="Task notifications"
          />
        }
      />
      <SettingRow
        icon={Lightbulb}
        dot={settings?.insights.enabled ? 'on' : 'off'}
        title="Insight notifications"
        subtitle="Periodically review recent screen activity and surface one useful insight."
        keywords="insight notification proactive rewind screen activity gemini toast native style frequency"
        control={
          <Toggle
            on={!!settings?.insights.enabled}
            onChange={(on) => void patchSettings({ insights: { enabled: on } })}
            disabled={!settings}
            label="Insight notifications"
          />
        }
      >
        {settings && (
          <div className="space-y-3">
            <label className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
              Check every
              <select
                value={
                  INSIGHT_INTERVALS.includes(settings.insights.intervalMin)
                    ? settings.insights.intervalMin
                    : 15
                }
                onChange={(event) =>
                  void patchSettings({ insights: { intervalMin: Number(event.target.value) } })
                }
                className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
              >
                {INSIGHT_INTERVALS.map((minutes) => (
                  <option key={minutes} value={minutes} className="bg-neutral-900">
                    {minutes} minutes
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
              Notification style
              <select
                value={settings.insights.notificationStyle}
                onChange={(event) =>
                  void patchSettings({
                    insights: { notificationStyle: event.target.value as 'omi' | 'native' }
                  })
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
            <button onClick={sendInsightTest} className="btn-ghost inline-flex items-center gap-2">
              <Send className="h-4 w-4" />
              Send insight test
            </button>
            <textarea
              rows={2}
              placeholder="Denylist - one app/site keyword per line (e.g. therapy, salary)"
              defaultValue={settings.insights.denylist.join('\n')}
              onBlur={(event) =>
                void patchSettings({
                  insights: {
                    denylist: event.target.value
                      .split('\n')
                      .map((value) => value.trim())
                      .filter(Boolean)
                  }
                })
              }
              className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
            />
          </div>
        )}
      </SettingRow>
      <SettingRow
        icon={Brain}
        dot={settings?.memories.enabled ? 'on' : 'off'}
        title="Memory notifications"
        subtitle="Show a notification when Omi extracts a durable memory."
        keywords="memory memories notification extracted durable profile assistant"
        control={
          <Toggle
            on={!!settings?.memories.enabled}
            onChange={(on) => void patchSettings({ memories: { enabled: on } })}
            disabled={!settings}
            label="Memory notifications"
          />
        }
      />

      <h2 className="section-label mb-2 mt-8">Daily summary</h2>
      <SettingRow
        icon={CalendarClock}
        dot={settings?.dailySummary.enabled ? 'on' : 'off'}
        title="Daily summary"
        subtitle="Receive a recap of conversations, activity, and tasks."
        keywords="daily summary recap digest notifications conversations activity tasks time hour"
        control={
          <Toggle
            on={!!settings?.dailySummary.enabled}
            onChange={(on) => void patchSettings({ dailySummary: { enabled: on } })}
            disabled={!settings}
            label="Daily summary"
          />
        }
      >
        {settings && (
          <label className="flex flex-wrap items-center gap-2 text-sm text-text-secondary">
            Summary time
            <select
              value={settings.dailySummary.hour}
              onChange={(event) =>
                void patchSettings({ dailySummary: { hour: Number(event.target.value) } })
              }
              className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
            >
              {HOURS.map((hour) => (
                <option key={hour} value={hour} className="bg-neutral-900">
                  {formatHour(hour)}
                </option>
              ))}
            </select>
          </label>
        )}
      </SettingRow>
    </>
  )
}
