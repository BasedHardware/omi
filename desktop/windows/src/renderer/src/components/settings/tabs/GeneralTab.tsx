import { useEffect, useState } from 'react'
import { MessagesSquare, Power, Keyboard, Download, Presentation } from 'lucide-react'
import type { MeetingMode } from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import { acceleratorToTokens } from '../../../lib/overlayShortcut'
import { useChordRecorder } from '../../../hooks/useChordRecorder'

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
      <MeetingDetectionRow />
      <LaunchAtLoginRow />
      <RecordHotkeyRow />
      <UpdateReadyRow />
    </>
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

// Shows the current global record hotkey and lets the user rebind it. Capture
// reuses the overlay-shortcut helpers (validation + accelerator building). When
// main reports the accelerator isn't registered (another app holds it), a warning
// is shown.
function RecordHotkeyRow(): React.JSX.Element {
  const [accel, setAccel] = useState<string | null>(null)
  const [registered, setRegistered] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void window.omi?.getRecordHotkey?.().then((h) => {
      if (!h) return
      setAccel(h.accelerator)
      setRegistered(h.registered)
    })
  }, [])

  // suspend/resume release ALL global chords while recording — otherwise pressing
  // the CURRENT chord (Ctrl+Space / Shift+Space) fires the shortcut and navigates
  // away instead of being captured.
  const recorder = useChordRecorder({
    suspend: () => window.omi?.suspendShortcutCapture?.(),
    resume: () => window.omi?.resumeShortcutCapture?.(),
    commit: async (next) => {
      const res = await window.omi?.setRecordHotkey?.(next)
      return { ok: !!res?.ok, registered: !!res?.registered }
    },
    onCommitted: (next, result) => {
      setAccel(next)
      setRegistered(result.registered)
    },
    onError: setError
  })

  const tokens = accel ? acceleratorToTokens(accel) : []

  return (
    <SettingRow
      icon={Keyboard}
      title="Record hotkey"
      subtitle="Global shortcut to start and stop recording."
      keywords="hotkey shortcut record accelerator keybinding rebind"
      note={
        (error || !registered) && (
          <p className="text-xs text-amber-300">
            {error ?? 'This shortcut is held by another app — pick a different one.'}
          </p>
        )
      }
      control={
        <div className="flex items-center gap-2">
          {recorder.recording ? (
            <span className="text-xs text-white/50">Press keys… (Esc to cancel)</span>
          ) : (
            <div className="flex items-center gap-1">
              {tokens.length > 0 ? (
                tokens.map((t, i) => (
                  <kbd
                    key={`${t}-${i}`}
                    className="flex h-7 min-w-7 items-center justify-center rounded-md bg-white/[0.08] px-2 text-xs font-semibold text-white/85"
                  >
                    {t}
                  </kbd>
                ))
              ) : (
                <span className="text-xs text-white/40">Not set</span>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={() => recorder.start()}
            disabled={recorder.recording}
            className="ml-1 rounded-md border border-white/15 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/10 disabled:opacity-40"
          >
            {recorder.recording ? 'Recording…' : 'Rebind'}
          </button>
        </div>
      }
    />
  )
}

// Appears only after electron-updater has staged an update. Restarting quits the
// app, which installs the pending update.
function UpdateReadyRow(): React.JSX.Element | null {
  const [version, setVersion] = useState<string | null>(null)

  useEffect(() => {
    // The one-shot update:ready event almost always fires while this row is
    // unmounted (background download) — query the staged update on mount too.
    void window.omi?.getPendingUpdate?.().then((p) => {
      if (p?.version) setVersion(p.version)
    })
    return window.omi?.onUpdateReady?.((info) => setVersion(info.version))
  }, [])

  if (!version) return null

  return (
    <SettingRow
      icon={Download}
      title="Update ready"
      subtitle={`Version ${version} is ready. Restart Omi to apply it.`}
      keywords="update upgrade restart version release"
      control={
        <button
          type="button"
          onClick={() => window.omi?.quitApp?.()}
          className="rounded-md bg-white px-3 py-1.5 text-xs font-medium text-black transition-opacity hover:opacity-90"
        >
          Restart to update
        </button>
      }
    />
  )
}
