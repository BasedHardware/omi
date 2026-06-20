import { useEffect, useState } from 'react'
import { MessagesSquare, ZoomIn, LogIn, Pin, Bell } from 'lucide-react'
import { getPreferences, setPreferences, onPreferencesChange } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [fontScale, setFontScale] = useState(getPreferences().fontScale ?? 1.0)
  const [launchAtStartup, setLaunchAtStartup] = useState<boolean>(false)
  const [alwaysOnTop, setAlwaysOnTop] = useState<boolean>(false)
  const [notifSounds, setNotifSounds] = useState<boolean>(getPreferences().notificationSounds ?? true)

  useEffect(() => onPreferencesChange((p) => {
    setFontScale(p.fontScale ?? 1.0)
    setNotifSounds(p.notificationSounds ?? true)
  }), [])

  useEffect(() => {
    void window.omi.getLoginItem?.().then((v) => setLaunchAtStartup(v ?? false))
    void window.omi.getAlwaysOnTop?.().then((v) => setAlwaysOnTop(v ?? false))
  }, [])

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

      <SettingRow
        icon={LogIn}
        dot={launchAtStartup ? 'on' : 'off'}
        title="Launch at startup"
        subtitle="Start Omi automatically when you log in to Windows so it's always ready in the system tray."
        keywords="startup login launch boot autostart windows"
        control={
          <Toggle
            on={launchAtStartup}
            onChange={async (on) => {
              setLaunchAtStartup(on)
              await window.omi.setLoginItem?.(on)
            }}
            label="Launch at startup"
          />
        }
      />

      <SettingRow
        icon={Pin}
        dot={alwaysOnTop ? 'on' : 'off'}
        title="Always on top"
        subtitle="Keep the Omi window floating above all other apps — useful when referencing Omi while working in another application."
        keywords="always on top float window pin foreground"
        control={
          <Toggle
            on={alwaysOnTop}
            onChange={async (on) => {
              setAlwaysOnTop(on)
              await window.omi.setAlwaysOnTop?.(on)
            }}
            label="Always on top"
          />
        }
      />

      <SettingRow
        icon={Bell}
        dot={notifSounds ? 'on' : 'off'}
        title="Notification sounds"
        subtitle="Play a sound when Omi sends a system notification (e.g. insight alerts, recording saved)."
        keywords="notification sound bell audio alert chime"
        control={
          <Toggle
            on={notifSounds}
            onChange={(on) => {
              setNotifSounds(on)
              setPreferences({ notificationSounds: on })
            }}
            label="Notification sounds"
          />
        }
      />

      <SettingRow
        icon={ZoomIn}
        title="Font scale"
        subtitle={`Current: ${Math.round(fontScale * 100)}% · Use Ctrl+= / Ctrl+- to adjust, Ctrl+0 to reset. Range: 85%–125%.`}
        keywords="font size zoom scale text accessibility"
        control={
          fontScale !== 1.0 ? (
            <button
              onClick={() => setPreferences({ fontScale: 1.0 })}
              className="rounded-md bg-white/10 px-3 py-1.5 text-sm text-white/70 hover:bg-white/15 hover:text-white"
            >
              Reset to 100%
            </button>
          ) : (
            <span className="text-sm text-white/30">Default</span>
          )
        }
      />
    </>
  )
}
