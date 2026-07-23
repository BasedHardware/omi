import { useEffect, useState } from 'react'
import {
  LayoutDashboard,
  MessageSquarePlus,
  MessagesSquare,
  Mic,
  Monitor,
  Power,
  Presentation,
  ScanEye,
  Zap
} from 'lucide-react'
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
      <ActionAutomationRow />
      <ScreenAnalysisRow />
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
      <MultiChatRow />
      <LegacyHomeRow />
      <MeetingDetectionRow />
      <LaunchAtLoginRow />
      <FontSizeCard />
    </>
  )
}

function ActionAutomationRow(): React.JSX.Element {
  const automationAvailable = window.omi.automationEnabled
  const [autoConsent, setAutoConsent] = useState<boolean>(!!getPreferences().automationConsentedAt)
  const toggleAutomation = (on: boolean): void => {
    setAutoConsent(on)
    setPreferences({ automationConsentedAt: on ? Date.now() : undefined })
  }

  return (
    <SettingRow
      icon={Zap}
      dot={automationAvailable && autoConsent ? 'on' : 'off'}
      title="Let Omi take actions"
      subtitle={
        !automationAvailable
          ? 'Disabled in this build.'
          : autoConsent
            ? 'Omi can click and type in your apps when you ask.'
            : 'Turn on to let Omi act in your apps when you ask.'
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

// Screen Analysis master (macOS General "Screen Capture" consent, Windows-named
// "Screen Analysis" to avoid colliding with the local-Rewind "Screen Capture" row
// above). This is the single consent gate for the whole proactive screen loop —
// Focus, memory/task extraction, and insights. Today it is only reachable from the
// tray checkbox; this row exposes it in Settings. It reads/writes through the same
// scoped assistant bridge the tray and the Notifications tab use, and subscribes to
// the broadcast so it and the tray checkbox can never disagree.
export function ScreenAnalysisRow(): React.JSX.Element {
  const [on, setOn] = useState<boolean | null>(null)

  useEffect(() => {
    void window.omi?.assistantsGetSettings?.().then((s) => setOn(s.screenAnalysisEnabled))
    return window.omi?.onAssistantSettingsChanged?.((s) => setOn(s.screenAnalysisEnabled))
  }, [])

  const change = (next: boolean): void => {
    setOn(next) // optimistic; the coordinator re-syncs off the settings write
    void window.omi?.assistantsSetSettings?.({ screenAnalysisEnabled: next })
  }

  return (
    <SettingRow
      icon={ScanEye}
      dot={on ? 'on' : 'off'}
      title="Screen Analysis"
      subtitle="Master switch for Omi's proactive screen features — Focus, memory and task extraction, and insights. When off, Omi never analyzes your screen. Separate from Screen Capture above, which only records your local Rewind timeline."
      keywords="screen analysis proactive focus memory task insight vision master consent"
      control={
        <Toggle on={!!on} onChange={change} disabled={on === null} label="Screen Analysis" />
      }
    />
  )
}

// Multi-chat sessions (macOS "Multiple Chat Sessions"). Off = the single Synced
// Chat thread shared with mobile; on = separate desktop chat threads with a
// history switcher. The multi-chat header also requires the pi_mono chat engine
// (a dark flag), so flipping this on under the default legacy engine has no
// visible effect yet — matching Mac, where multi-chat is kernel-backed.
function MultiChatRow(): React.JSX.Element {
  const [on, setOn] = useState(() => getPreferences().multiChatEnabled === true)

  useEffect(() => onPreferencesChange((p) => setOn(p.multiChatEnabled === true)), [])

  const change = (next: boolean): void => {
    setOn(next) // optimistic; setPreferences notifies subscribers to reconcile
    setPreferences({ multiChatEnabled: next })
  }

  return (
    <SettingRow
      icon={MessageSquarePlus}
      title="Multiple Chat Sessions"
      subtitle={on ? 'Create separate chat threads' : 'Single chat synced with the mobile app'}
      keywords="multi chat sessions threads history switcher conversations separate"
      control={<Toggle on={on} onChange={change} label="Multiple Chat Sessions" />}
    />
  )
}

// Escape hatch back to the original Home screen. The Home page subscribes to this
// preference, so the switch takes effect immediately — no restart.
function LegacyHomeRow(): React.JSX.Element {
  const [legacy, setLegacy] = useState(!!getPreferences().useLegacyHomeDesign)

  const change = (next: boolean): void => {
    setLegacy(next)
    setPreferences({ useLegacyHomeDesign: next })
  }

  return (
    <SettingRow
      icon={LayoutDashboard}
      dot={legacy ? 'off' : 'on'}
      title="New Home screen"
      subtitle="The redesigned Home — one stage with your stats, an ask bar, and suggestions. Turn this off to go back to the previous Home."
      keywords="hub home dashboard layout redesign legacy old classic"
      control={
        <Toggle on={!legacy} onChange={(on) => change(!on)} label="Use the new Home screen" />
      }
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
