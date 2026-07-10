import { useEffect, useState } from 'react'
import { MessagesSquare, Power, Keyboard, Download } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'
import {
  acceleratorToTokens,
  eventToAccelerator,
  validateCustomAccelerator
} from '../../../lib/overlayShortcut'

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
      <LaunchAtLoginRow />
      <RecordHotkeyRow />
      <UpdateReadyRow />
    </>
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
  const [recording, setRecording] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void window.omi?.getRecordHotkey?.().then((h) => {
      if (!h) return
      setAccel(h.accelerator)
      setRegistered(h.registered)
    })
  }, [])

  // While recording, capture raw keydowns. A complete, valid combo commits via
  // setRecordHotkey; Esc cancels.
  useEffect(() => {
    if (!recording) return
    const onKeyDown = (e: KeyboardEvent): void => {
      e.preventDefault()
      e.stopPropagation()
      if (e.key === 'Escape') {
        setRecording(false)
        return
      }
      const next = eventToAccelerator(e)
      if (!next) return // still building the chord
      const valid = validateCustomAccelerator(next)
      if (!valid.ok) {
        setError(valid.reason)
        return
      }
      void (async () => {
        const res = await window.omi?.setRecordHotkey?.(next)
        if (res?.ok) {
          setAccel(next)
          setRegistered(res.registered)
          setError(null)
          setRecording(false)
        } else {
          setError('That shortcut is already in use — try another.')
          setRecording(false)
        }
      })()
    }
    window.addEventListener('keydown', onKeyDown, true)
    return () => window.removeEventListener('keydown', onKeyDown, true)
  }, [recording])

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
          {recording ? (
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
            onClick={() => {
              setError(null)
              setRecording(true)
            }}
            disabled={recording}
            className="ml-1 rounded-md border border-white/15 px-3 py-1.5 text-xs text-white transition-colors hover:bg-white/10 disabled:opacity-40"
          >
            {recording ? 'Recording…' : 'Rebind'}
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
