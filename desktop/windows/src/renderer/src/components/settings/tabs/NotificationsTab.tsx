import { useEffect, useState } from 'react'
import { Bell, Lightbulb, Mic, Target, CalendarClock, BookMarked, Brain, Radio } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { getPreferences, onPreferencesChange, setPreferences } from '../../../lib/preferences'
import type { InsightSettings } from '../../../../../shared/types'

const INSIGHT_INTERVALS = [15, 20, 30, 60]
const FOCUS_INTERVALS: Array<5 | 10 | 15 | 20> = [5, 10, 15, 20]

export function NotificationsTab(): React.JSX.Element {
  const [insight, setInsight] = useState<InsightSettings | null>(null)

  // Per-type notification prefs
  const [notifRecording, setNotifRecording] = useState(() => getPreferences().notifyOnRecordingSaved ?? true)
  const [notifDailySummary, setNotifDailySummary] = useState(() => getPreferences().notifyDailySummary ?? true)
  const [notifTaskDue, setNotifTaskDue] = useState(() => getPreferences().notifyTaskDue ?? true)
  const [notifNewMemory, setNotifNewMemory] = useState(() => getPreferences().notifyNewMemory ?? false)
  const [notifConvStarted, setNotifConvStarted] = useState(() => getPreferences().notifyConversationStarted ?? false)

  // Focus
  const [focusEnabled, setFocusEnabled] = useState(() => getPreferences().focusAnalysisEnabled ?? false)
  const [focusInterval, setFocusInterval] = useState<5 | 10 | 15 | 20>(() => getPreferences().focusAnalysisIntervalMin ?? 10)
  const [focusAlert, setFocusAlert] = useState(() => getPreferences().focusDistractionAlert ?? false)
  const [focusVision, setFocusVision] = useState(() => getPreferences().focusVisionEnabled ?? false)

  useEffect(() => {
    void window.omi.insightGetSettings().then(setInsight)
    return onPreferencesChange((p) => {
      setNotifRecording(p.notifyOnRecordingSaved ?? true)
      setNotifDailySummary(p.notifyDailySummary ?? true)
      setNotifTaskDue(p.notifyTaskDue ?? true)
      setNotifNewMemory(p.notifyNewMemory ?? false)
      setNotifConvStarted(p.notifyConversationStarted ?? false)
      setFocusEnabled(p.focusAnalysisEnabled ?? false)
      setFocusInterval(p.focusAnalysisIntervalMin ?? 10)
      setFocusAlert(p.focusDistractionAlert ?? false)
      setFocusVision(p.focusVisionEnabled ?? false)
    })
  }, [])

  const patchInsight = async (patch: Partial<InsightSettings>): Promise<void> => {
    const next = await window.omi.insightSetSettings(patch)
    setInsight(next)
  }

  return (
    <>
      {/* ── Conversation notifications ───────────────────────────────────── */}
      <SettingRow
        icon={Mic}
        dot={notifRecording ? 'on' : 'off'}
        title="Conversation saved"
        subtitle="Show a notification when a recording session finishes and the conversation is processed."
        keywords="recording saved notification mic conversation done"
        control={
          <Toggle
            on={notifRecording}
            onChange={(on) => { setNotifRecording(on); setPreferences({ notifyOnRecordingSaved: on }) }}
            label="Conversation saved"
          />
        }
      />

      <SettingRow
        icon={Radio}
        dot={notifConvStarted ? 'on' : 'off'}
        title="Conversation started"
        subtitle="Show a notification when Omi detects a new conversation has begun."
        keywords="conversation started live recording notification"
        control={
          <Toggle
            on={notifConvStarted}
            onChange={(on) => { setNotifConvStarted(on); setPreferences({ notifyConversationStarted: on }) }}
            label="Conversation started"
          />
        }
      />

      {/* ── Daily summary ─────────────────────────────────────────────────── */}
      <SettingRow
        icon={CalendarClock}
        dot={notifDailySummary ? 'on' : 'off'}
        title="Daily summary"
        subtitle="Receive a morning digest of yesterday's conversations, open tasks, and key memories."
        keywords="daily summary digest morning recap tasks"
        control={
          <Toggle
            on={notifDailySummary}
            onChange={(on) => { setNotifDailySummary(on); setPreferences({ notifyDailySummary: on }) }}
            label="Daily summary"
          />
        }
      />

      {/* ── Task reminders ────────────────────────────────────────────────── */}
      <SettingRow
        icon={BookMarked}
        dot={notifTaskDue ? 'on' : 'off'}
        title="Task due reminders"
        subtitle="Show a notification when a task's due date is approaching or has passed."
        keywords="task due reminder deadline notification"
        control={
          <Toggle
            on={notifTaskDue}
            onChange={(on) => { setNotifTaskDue(on); setPreferences({ notifyTaskDue: on }) }}
            label="Task reminders"
          />
        }
      />

      {/* ── Memory notifications ──────────────────────────────────────────── */}
      <SettingRow
        icon={Brain}
        dot={notifNewMemory ? 'on' : 'off'}
        title="New memory saved"
        subtitle="Notify when Omi extracts and saves a new memory from a conversation."
        keywords="memory saved notification new fact"
        control={
          <Toggle
            on={notifNewMemory}
            onChange={(on) => { setNotifNewMemory(on); setPreferences({ notifyNewMemory: on }) }}
            label="New memory"
          />
        }
      />

      {/* ── Proactive insights ────────────────────────────────────────────── */}
      <SettingRow
        icon={Lightbulb}
        dot={insight?.enabled ? 'on' : 'off'}
        title="Proactive insights"
        subtitle="Periodically reviews recent screen activity and surfaces one useful insight. Requires Rewind screen capture."
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
                  <option key={m} value={m} className="bg-neutral-900">{m} minutes</option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              Notification style
              <select
                value={insight.notificationStyle}
                onChange={(e) => void patchInsight({ notificationStyle: e.target.value as 'omi' | 'native' })}
                className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
              >
                <option value="omi" className="bg-neutral-900">Omi notification</option>
                <option value="native" className="bg-neutral-900">Windows notification</option>
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
                  denylist: e.target.value.split('\n').map((s) => s.trim()).filter(Boolean)
                })
              }
              className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
            />
          </div>
        )}
      </SettingRow>

      {/* ── Focus analysis alerts ─────────────────────────────────────────── */}
      <SettingRow
        icon={Target}
        dot={focusEnabled ? 'on' : 'off'}
        title="Focus analysis"
        subtitle="Periodically analyzes recent screen activity to classify you as focused, distracted, or neutral."
        keywords="focus distracted alert analysis detection proactive"
        control={
          <Toggle
            on={focusEnabled}
            onChange={(on) => { setFocusEnabled(on); setPreferences({ focusAnalysisEnabled: on }) }}
            label="Focus analysis"
          />
        }
      >
        {focusEnabled && (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm text-text-secondary">
              Check every
              <select
                value={focusInterval}
                onChange={(e) => {
                  const v = Number(e.target.value) as 5 | 10 | 15 | 20
                  setFocusInterval(v)
                  setPreferences({ focusAnalysisIntervalMin: v })
                }}
                className="rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none"
              >
                {FOCUS_INTERVALS.map((m) => (
                  <option key={m} value={m} className="bg-neutral-900">{m} minutes</option>
                ))}
              </select>
            </label>
            <div className="flex items-center justify-between">
              <label className="text-sm text-text-secondary">Alert on sustained distraction</label>
              <Toggle
                on={focusAlert}
                onChange={(on) => { setFocusAlert(on); setPreferences({ focusDistractionAlert: on }) }}
                label="Distraction alert"
              />
            </div>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-sm text-text-secondary">Screenshot vision analysis</p>
                <p className="mt-0.5 text-xs text-text-quaternary">
                  Sends 1–2 sampled Rewind screenshots to Gemini Vision for richer classification.
                </p>
              </div>
              <Toggle
                on={focusVision}
                onChange={(on) => { setFocusVision(on); setPreferences({ focusVisionEnabled: on }) }}
                label="Vision analysis"
              />
            </div>
          </div>
        )}
      </SettingRow>

      {/* ── Frequency note ────────────────────────────────────────────────── */}
      <SettingRow
        icon={Bell}
        title="Notification frequency"
        subtitle="Insight and focus notifications are throttled to avoid interrupting work. Conversation and task notifications fire once per event."
        keywords="frequency throttle rate limit"
      />
    </>
  )
}
