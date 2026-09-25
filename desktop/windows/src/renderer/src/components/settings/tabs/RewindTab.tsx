import { useEffect, useState } from 'react'
import {
  Monitor,
  Clock,
  CalendarClock,
  Ban,
  Brain,
  Lightbulb,
  X,
  Mic,
  Trash2,
  Target,
  ScanText
} from 'lucide-react'
import { runScreenSynthesisOnce } from '../../../lib/screenSynthesis'
import { runRetentionSweep } from '../../../lib/retentionSweep'
import { BUILT_IN_EXCLUDED_APPS } from '../../../../../shared/rewindExclusions'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import type {
  RewindSettings,
  RewindCaptureQuality,
  ScreenSynthState,
  InsightSettings,
  AssistantSettingsView
} from '../../../../../shared/types'

// Preset cadences offered for proactive insights (minutes). Each run is a Gemini
// call via Omi's proxy, so longer intervals mean less backend cost.
const INSIGHT_INTERVALS = [15, 20, 30, 60]

export function RewindTab(): React.JSX.Element {
  const [rewind, setRewind] = useState<RewindSettings | null>(null)
  const [screenSynth, setScreenSynth] = useState<ScreenSynthState | null>(null)
  const [insight, setInsight] = useState<InsightSettings | null>(null)
  // Insight's OTHER gate. `InsightAssistant.isEnabled()` (main/assistants/insight)
  // also requires a notification to be deliverable — master on AND frequency above
  // Off — because Insight has no glow, so a run that can't notify is pure wasted
  // spend. Frequency ships at 0 (Off), so out of the box this row reads "on" while
  // the pipeline never runs. Read the same flags here to say so.
  const [assistants, setAssistants] = useState<AssistantSettingsView | null>(null)
  // "Automatically suggest goals" (Wave C). null until the main-process value loads.
  const [goalAutoGen, setGoalAutoGen] = useState<boolean | null>(null)
  const [newExcluded, setNewExcluded] = useState('')
  const [continuousRec, setContinuousRec] = useState<boolean>(
    () => !!getPreferences().continuousRecording
  )
  const toggleContinuous = (): void => {
    const next = !continuousRec
    setContinuousRec(next)
    setPreferences({ continuousRecording: next })
  }
  const [retention, setRetention] = useState<'off' | 'dry-run' | 'live'>(
    () => getPreferences().retentionMode ?? 'dry-run'
  )
  const changeRetention = (mode: 'off' | 'dry-run' | 'live'): void => {
    setRetention(mode)
    setPreferences({ retentionMode: mode })
    // Preview is a one-shot the user just asked for, so run it here — the 30-minute
    // background timer only runs 'live' passes now. Pressing Preview is what makes
    // the "logs what it would delete" subtitle true, instead of it happening 48x a
    // day whether or not anyone is looking.
    if (mode === 'dry-run') void runRetentionSweep('manual')
  }

  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
    void window.omi.screenSynthGetState().then(setScreenSynth)
    void window.omi.insightGetSettings().then(setInsight)
    void window.omi.goalsGetAutoGeneration().then(setGoalAutoGen)
  }, [])

  // Separate effect: the notifications gate is broadcast (tray checkbox, the
  // Notifications tab, a future backend sync), so this row has to stay in
  // lock-step rather than read once on mount.
  useEffect(() => {
    void window.omi?.assistantsGetSettings?.().then(setAssistants)
    return window.omi?.onAssistantSettingsChanged?.(setAssistants)
  }, [])

  const toggleGoalAutoGen = (on: boolean): void => {
    setGoalAutoGen(on) // optimistic
    void window.omi.goalsSetAutoGeneration(on).then(setGoalAutoGen)
  }

  const saveRewind = (next: RewindSettings): void => {
    setRewind(next) // optimistic
    void window.omi.rewindSetSettings(next).then(setRewind)
  }
  const addExcludedApp = (): void => {
    const name = newExcluded.trim()
    if (!rewind || !name) return
    setNewExcluded('')
    if (rewind.excludedApps.some((a) => a.toLowerCase() === name.toLowerCase())) return
    saveRewind({ ...rewind, excludedApps: [...rewind.excludedApps, name] })
  }
  const removeExcludedApp = (app: string): void => {
    if (!rewind) return
    saveRewind({ ...rewind, excludedApps: rewind.excludedApps.filter((a) => a !== app) })
  }
  const patchScreenSynth = async (patch: Partial<ScreenSynthState>): Promise<void> => {
    setScreenSynth(await window.omi.screenSynthSetState(patch))
  }
  const synthesizeNow = async (): Promise<void> => {
    await runScreenSynthesisOnce()
    setScreenSynth(await window.omi.screenSynthGetState())
  }
  const patchInsight = async (patch: Partial<InsightSettings>): Promise<void> => {
    setInsight(await window.omi.insightSetSettings(patch))
  }

  // Mirrors notify.ts `notificationsActive`: master on AND frequency above Off.
  // Null while the settings are still loading — no claim either way until then.
  const insightsDeliverable =
    assistants === null
      ? null
      : assistants.notificationsEnabled && assistants.notificationFrequency > 0
  const insightsSilenced = !!insight?.enabled && insightsDeliverable === false

  // Snap any legacy / out-of-range interval (e.g. an old 1- or 10-min value) to a
  // valid preset, so the picker (15/20/30/60) and the engine stay in agreement.
  useEffect(() => {
    if (insight && !INSIGHT_INTERVALS.includes(insight.intervalMin)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- intentional load-on-mount / reset-on-dependency-change; not a self-retriggering loop
      void patchInsight({ intervalMin: 15 })
    }
  }, [insight])

  return (
    <>
      <SettingRow
        icon={Mic}
        dot={continuousRec ? 'on' : 'off'}
        title="Continuous recording"
        subtitle="Always-on microphone. Omi turns what you hear into conversations automatically."
        keywords="continuous recording microphone audio always-on"
        control={
          <Toggle on={continuousRec} onChange={toggleContinuous} label="Continuous recording" />
        }
      />
      <SettingRow
        icon={Trash2}
        title="Auto-cleanup"
        subtitle="Remove empty conversations and junk memories. Preview logs what it would delete; switch to Delete to apply."
        keywords="retention cleanup delete conversations memories sweep"
      >
        <div className="flex gap-1">
          {(['off', 'dry-run', 'live'] as const).map((m) => (
            <button
              key={m}
              onClick={() => changeRetention(m)}
              className={
                retention === m
                  ? 'rounded-md bg-white/15 px-2.5 py-1 text-xs text-white'
                  : 'rounded-md px-2.5 py-1 text-xs text-white/50 hover:text-white/80'
              }
            >
              {m === 'off' ? 'Off' : m === 'dry-run' ? 'Preview' : 'Delete'}
            </button>
          ))}
        </div>
      </SettingRow>
      <SettingRow
        icon={Monitor}
        dot={rewind?.captureEnabled ? 'on' : 'off'}
        title="Capture my screen"
        subtitle="A local, searchable timeline stored only on this PC — never uploaded."
        keywords="rewind screen capture record"
        control={
          <Toggle
            on={!!rewind?.captureEnabled}
            onChange={(on) => rewind && saveRewind({ ...rewind, captureEnabled: on })}
            disabled={!rewind}
            label="Capture my screen"
          />
        }
      />
      <SettingRow
        icon={Clock}
        title="Capture interval"
        subtitle="How often a frame is sampled."
        keywords="rewind frequency seconds"
        control={
          <select
            value={rewind?.intervalMs ?? 1000}
            onChange={(e) =>
              rewind && saveRewind({ ...rewind, intervalMs: Number(e.target.value) })
            }
            disabled={!rewind}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none disabled:opacity-40"
          >
            <option value={1000} className="bg-neutral-900">
              Every 1s
            </option>
            <option value={2000} className="bg-neutral-900">
              Every 2s
            </option>
            <option value={5000} className="bg-neutral-900">
              Every 5s
            </option>
            <option value={10000} className="bg-neutral-900">
              Every 10s
            </option>
          </select>
        }
      />
      <SettingRow
        icon={ScanText}
        title="Capture quality"
        subtitle="Higher quality makes small on-screen text readable (better search and OCR), and uses more CPU and disk."
        keywords="rewind resolution quality ocr sharpness readable text"
        control={
          <select
            value={rewind?.captureQuality ?? 'standard'}
            onChange={(e) =>
              rewind &&
              saveRewind({ ...rewind, captureQuality: e.target.value as RewindCaptureQuality })
            }
            disabled={!rewind}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none disabled:opacity-40"
          >
            <option value="standard" className="bg-neutral-900">
              Standard (720p)
            </option>
            <option value="high" className="bg-neutral-900">
              High (1080p)
            </option>
            <option value="max" className="bg-neutral-900">
              Maximum (1440p)
            </option>
          </select>
        }
      />
      <SettingRow
        icon={CalendarClock}
        title="Keep history for"
        subtitle="Older frames are pruned automatically."
        keywords="rewind retention days delete"
        control={
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <input
              type="number"
              min={1}
              value={rewind?.retentionDays ?? 14}
              onChange={(e) => {
                const days = Number(e.target.value)
                if (rewind && Number.isFinite(days) && days >= 1)
                  saveRewind({ ...rewind, retentionDays: days })
              }}
              disabled={!rewind}
              className="w-16 rounded-md bg-white/10 px-2 py-1.5 text-white focus:outline-none disabled:opacity-40"
            />
            days
          </div>
        }
      />
      <SettingRow
        icon={Ban}
        title="Excluded apps"
        subtitle="Rewind never screenshots while one of these apps is in focus. Matched loosely (e.g. “chrome” covers Google Chrome)."
        keywords="rewind exclude block private app capture"
      >
        <div className="space-y-3">
          <div className="flex gap-2">
            <input
              value={newExcluded}
              onChange={(e) => setNewExcluded(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  addExcludedApp()
                }
              }}
              placeholder="App name (e.g. Banking)"
              className="flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
            />
            <button
              onClick={addExcludedApp}
              disabled={!newExcluded.trim()}
              className="btn-ghost disabled:opacity-40"
            >
              Add
            </button>
          </div>
          {/* User additions — removable. */}
          {rewind && rewind.excludedApps.length > 0 && (
            <ul className="flex flex-wrap gap-2">
              {rewind.excludedApps.map((app) => (
                <li
                  key={app}
                  className="flex items-center gap-1.5 rounded-full bg-white/10 py-1 pl-3 pr-1.5 text-sm text-text-secondary"
                >
                  <span className="max-w-[16rem] truncate">{app}</span>
                  <button
                    onClick={() => removeExcludedApp(app)}
                    aria-label={`Remove ${app}`}
                    className="rounded-full p-0.5 text-white/50 transition-colors hover:bg-white/10 hover:text-white"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
          {/* Built-in, always-on exclusions (not removable). */}
          <div className="rounded-lg bg-white/[0.04] px-3 py-2 text-xs leading-relaxed text-text-tertiary">
            <span className="text-text-secondary">Always excluded:</span>{' '}
            {['Omi', ...BUILT_IN_EXCLUDED_APPS].join(' · ')}.
            <span className="mt-1 block">
              Login, password, and private-browsing screens are skipped automatically (by window
              title).
            </span>
          </div>
        </div>
      </SettingRow>

      <SettingRow
        icon={Brain}
        dot={screenSynth?.enabled ? 'on' : 'off'}
        title="Screen activity → memories"
        subtitle="Turns recent on-screen text (from Rewind) into memories. On-device redaction first; skips private/incognito windows. Off by default — writes to your Omi account."
        keywords="synthesis screen memories gemini"
        control={
          <Toggle
            on={!!screenSynth?.enabled}
            onChange={(on) => void patchScreenSynth({ enabled: on })}
            disabled={!screenSynth}
            label="Screen activity to memories"
          />
        }
      >
        {screenSynth && (
          <div className="space-y-2">
            <textarea
              rows={2}
              placeholder="Denylist — one app/site keyword per line (e.g. therapy, salary)"
              defaultValue={screenSynth.denylist.join('\n')}
              onBlur={(e) =>
                void patchScreenSynth({
                  denylist: e.target.value
                    .split('\n')
                    .map((s) => s.trim())
                    .filter(Boolean)
                })
              }
              className="w-full rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary focus:outline-none"
            />
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-tertiary">
                {screenSynth.lastRunAt
                  ? `Last run ${new Date(screenSynth.lastRunAt).toLocaleString()} — ${screenSynth.lastCount} memories`
                  : 'Not run yet'}
              </span>
              <button onClick={() => void synthesizeNow()} className="btn-ghost">
                Synthesize now
              </button>
            </div>
          </div>
        )}
      </SettingRow>

      <SettingRow
        icon={Lightbulb}
        dot={insight?.enabled ? (insightsSilenced ? 'warn' : 'on') : 'off'}
        title="Proactive insights"
        subtitle="Periodically reviews recent screen activity and surfaces a single useful insight (choose the style below). Requires screen capture, and Notifications turned on with a frequency above Off."
        keywords="notifications toast gemini suggestion frequency off silenced"
        note={
          insightsSilenced ? (
            <span className="text-xs text-amber-400/90">
              Notifications are off, so insights never run — a test notification still shows because
              it bypasses this. Turn Notifications on and raise the frequency above Off in Settings
              → Notifications.
            </span>
          ) : undefined
        }
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
                  void patchInsight({
                    notificationStyle: e.target.value as 'omi' | 'native'
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
            <button onClick={() => window.omi.insightTest()} className="btn-ghost self-start">
              Send a test notification
            </button>
            <textarea
              rows={2}
              placeholder="Denylist — one app/site keyword per line (e.g. therapy, salary)"
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

      <SettingRow
        icon={Target}
        dot={goalAutoGen ? 'on' : 'off'}
        title="Automatically suggest goals"
        subtitle="Occasionally reviews your memories, conversations, and tasks on-device and creates a goal it thinks fits you. Off by default; you can always use Suggest on the Goals page."
        keywords="goals suggest auto generate proactive"
        control={
          <Toggle
            on={!!goalAutoGen}
            onChange={toggleGoalAutoGen}
            disabled={goalAutoGen === null}
            label="Automatically suggest goals"
          />
        }
      />
    </>
  )
}
