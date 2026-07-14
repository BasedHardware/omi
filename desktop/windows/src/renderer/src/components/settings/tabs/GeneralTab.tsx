import { useEffect, useState } from 'react'
import { MessagesSquare, Mic, Monitor, Power, Presentation } from 'lucide-react'
import type { MeetingMode, RewindSettings } from '../../../../../shared/types'
import { getPreferences, onPreferencesChange, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { FontSizeCard } from '../FontSizeCard'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)

  return (
    <>
      {/* macOS General leads with the capture-status cards (spec §3.1). */}
      <ScreenCaptureRow />
      <AudioRecordingRow />
      <SettingRow
        icon={MessagesSquare}
        title="Chat history"
        subtitle="By default, one ongoing conversation (shared with the floating bar) that persists across launches — scroll up in chat to load older messages. Or start a fresh conversation each launch."
        keywords="conversation thread floating bar history infinite"
        control={
          <select
            value={chatHistoryMode}
            onChange={(e) => {
              const v = e.target.value as 'per-launch' | 'infinite'
              setChatHistoryMode(v)
              setPreferences({ chatHistoryMode: v })
            }}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
          >
            <option value="infinite" className="bg-neutral-900">
              One ongoing conversation (default)
            </option>
            <option value="per-launch" className="bg-neutral-900">
              New conversation each launch
            </option>
          </select>
        }
      />
      <MeetingDetectionRow />
      <LaunchAtLoginRow />
      <FontSizeCard />
    </>
  )
}

// Screen Capture status card (macOS General §3.1). Mirrors the Sidebar's "Screen
// recording" toggle: both bind to the persistent Rewind `captureEnabled` setting.
// We subscribe to the `rewind:settings` broadcast so flipping the switch in the
// Sidebar (or another window) live-updates this card without a refetch.
function ScreenCaptureRow(): React.JSX.Element {
  const [rewind, setRewind] = useState<RewindSettings | null>(null)

  useEffect(() => {
    void window.omi?.rewindGetSettings?.().then(setRewind)
    return window.omi?.onRewindSettings?.(setRewind)
  }, [])

  const on = !!rewind?.captureEnabled
  const change = (next: boolean): void => {
    if (!rewind) return
    const updated = { ...rewind, captureEnabled: next }
    setRewind(updated) // optimistic
    void window.omi?.rewindSetSettings?.(updated).then(setRewind)
  }

  return (
    <SettingRow
      icon={Monitor}
      dot={on ? 'on' : 'off'}
      title="Screen Capture"
      subtitle={on ? 'Capturing your screen for Rewind' : 'Screen capture is paused'}
      keywords="screen capture rewind record monitor recording"
      control={
        <Toggle on={on} onChange={change} disabled={rewind === null} label="Screen Capture" />
      }
    />
  )
}

// Audio Recording status card (macOS General §3.1). Bound to the `continuousRecording`
// preference — the same state the Sidebar's "Microphone" toggle drives — and live-syncs
// through the preferences listener when flipped elsewhere.
function AudioRecordingRow(): React.JSX.Element {
  const [on, setOn] = useState<boolean>(() => !!getPreferences().continuousRecording)

  useEffect(() => onPreferencesChange((p) => setOn(!!p.continuousRecording)), [])

  const change = (next: boolean): void => {
    setOn(next) // optimistic; setPreferences notifies subscribers to reconcile
    setPreferences({ continuousRecording: next })
  }

  return (
    <SettingRow
      icon={Mic}
      dot={on ? 'on' : 'off'}
      title="Audio Recording"
      subtitle={on ? 'Recording and transcribing audio' : 'Audio recording is paused'}
      keywords="audio recording microphone transcribe listening voice"
      control={<Toggle on={on} onChange={change} label="Audio Recording" />}
    />
  )
}

// Meeting detection (Phase 5): off / ask (default) / auto. Per-app overrides
// live in the same settings object (userData/app-settings.json → meeting.perApp,
// keyed by pattern id) — editable as JSON; no dedicated UI yet.
function MeetingDetectionRow(): React.JSX.Element {
  const [mode, setMode] = useState<MeetingMode | null>(null)

  useEffect(() => {
    void window.omi?.meetingGetSettings?.().then((s) => setMode(s.mode))
  }, [])

  const change = (next: MeetingMode): void => {
    setMode(next) // optimistic
    void window.omi?.meetingSetSettings?.({ mode: next })
  }

  return (
    <SettingRow
      icon={Presentation}
      dot={mode === 'off' ? 'off' : 'on'}
      title="Meeting detection"
      subtitle="When a meeting app is holding the microphone (Zoom, Teams, Meet, and more), Omi can capture and transcribe it — always with a visible notice, never silently."
      keywords="meeting zoom teams meet webex discord detect auto capture record"
      control={
        <select
          value={mode ?? 'ask'}
          disabled={mode === null}
          onChange={(e) => change(e.target.value as MeetingMode)}
          className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
        >
          <option value="ask" className="bg-neutral-900">
            Ask before capturing (default)
          </option>
          <option value="auto" className="bg-neutral-900">
            Capture automatically
          </option>
          <option value="off" className="bg-neutral-900">
            Off
          </option>
        </select>
      }
    />
  )
}

// Reflects and controls the OS "start Omi when I sign in" setting. Reads the real
// state from main on mount; the toggle writes it through and updates optimistically.
function LaunchAtLoginRow(): React.JSX.Element {
  const [openAtLogin, setOpenAtLogin] = useState<boolean | null>(null)
  // The OS Run entry is only writable in packaged builds (see the main handler);
  // in unpackaged dev the toggle must not pretend it works.
  const [supported, setSupported] = useState(true)

  useEffect(() => {
    void window.omi?.getLoginItemSettings?.().then((s) => {
      setOpenAtLogin(!!s?.openAtLogin)
      setSupported(!!s?.supported)
    })
  }, [])

  const change = (next: boolean): void => {
    setOpenAtLogin(next) // optimistic
    void window.omi?.setLaunchAtLogin?.(next)
  }

  return (
    <SettingRow
      icon={Power}
      dot={openAtLogin ? 'on' : 'off'}
      title="Launch at login"
      subtitle={
        supported
          ? 'Start Omi automatically when you sign in to Windows.'
          : 'Start Omi automatically when you sign in to Windows. Available in installed builds only.'
      }
      keywords="startup autostart launch login boot start"
      control={
        <Toggle
          on={!!openAtLogin}
          onChange={change}
          disabled={openAtLogin === null || !supported}
          label="Launch at login"
        />
      }
    />
  )
}

// Record hotkey and the "update ready" restart affordance moved to their topical
// tabs: Settings → Shortcuts (ShortcutsTab) and Settings → About (AboutTab).
