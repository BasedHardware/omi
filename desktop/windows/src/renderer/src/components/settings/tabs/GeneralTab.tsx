import { useEffect, useState } from 'react'
import { LayoutDashboard, MessagesSquare, Power, Presentation } from 'lucide-react'
import type { MeetingMode } from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)

  return (
    <>
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
      <LegacyHomeRow />
      <MeetingDetectionRow />
      <LaunchAtLoginRow />
    </>
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
