import { useState } from 'react'
import { Keyboard, Mic2, Volume2, Lock } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

const OVERLAY_SHORTCUT_OPTIONS = [
  { value: 'CommandOrControl+Space', label: 'Ctrl+Space (default)' },
  { value: 'Alt+Space', label: 'Alt+Space' },
  { value: 'CommandOrControl+Shift+Space', label: 'Ctrl+Shift+Space' },
  { value: 'CommandOrControl+G', label: 'Ctrl+G' },
  { value: 'CommandOrControl+Shift+G', label: 'Ctrl+Shift+G' },
  { value: 'F12', label: 'F12' },
  { value: 'Alt+G', label: 'Alt+G' }
]

const PTT_SHORTCUT_OPTIONS = [
  { value: 'CommandOrControl+Shift+Space', label: 'Ctrl+Shift+Space (default)' },
  { value: 'Alt+Shift+Space', label: 'Alt+Shift+Space' },
  { value: 'CommandOrControl+Shift+M', label: 'Ctrl+Shift+M' },
  { value: 'F10', label: 'F10' },
  { value: 'Alt+F10', label: 'Alt+F10' },
]

export function ShortcutsTab(): React.JSX.Element {
  const prefs = getPreferences()
  const [shortcut, setShortcut] = useState(prefs.overlayShortcut ?? 'CommandOrControl+Space')
  const [pttEnabled, setPttEnabled] = useState(prefs.pttEnabled ?? false)
  const [pttShortcut, setPttShortcut] = useState(prefs.pttShortcut ?? 'CommandOrControl+Shift+Space')
  const [pttSounds, setPttSounds] = useState(prefs.pttSounds ?? true)
  const [pttLockedMode, setPttLockedMode] = useState(prefs.pttLockedMode ?? false)

  const applyOverlay = (value: string): void => {
    setShortcut(value)
    setPreferences({ overlayShortcut: value })
    void window.omiOverlay?.setAccelerator(value)
  }

  return (
    <>
      {/* Ask Omi shortcut */}
      <SettingRow
        icon={Keyboard}
        title="Ask Omi shortcut"
        subtitle="Global keyboard shortcut to open the floating Ask Omi bar from anywhere. Takes effect immediately — no restart needed."
        keywords="shortcut hotkey keyboard overlay ask omi floating bar global"
        control={
          <select
            value={shortcut}
            onChange={(e) => applyOverlay(e.target.value)}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
          >
            {OVERLAY_SHORTCUT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value} className="bg-neutral-900">
                {o.label}
              </option>
            ))}
            {!OVERLAY_SHORTCUT_OPTIONS.some((o) => o.value === shortcut) && (
              <option value={shortcut} className="bg-neutral-900">
                {shortcut}
              </option>
            )}
          </select>
        }
      />

      {/* Push to Talk — enabled toggle */}
      <SettingRow
        icon={Mic2}
        dot={pttEnabled ? 'on' : 'off'}
        title="Push to Talk"
        subtitle="Hold the shortcut to speak, release to send your voice question to Omi. When enabled, assign a shortcut below."
        keywords="push to talk ptt voice shortcut mic hold"
        control={
          <Toggle
            on={pttEnabled}
            onChange={(on) => {
              setPttEnabled(on)
              setPreferences({ pttEnabled: on })
            }}
            label="Push to Talk"
          />
        }
      />

      {/* PTT shortcut — only when PTT is enabled */}
      {pttEnabled && (
        <>
          <SettingRow
            icon={Keyboard}
            title="Push to Talk shortcut"
            subtitle="Hold this key to start listening. Release to send the captured audio to Omi."
            keywords="ptt shortcut hold key"
            control={
              <select
                value={pttShortcut}
                onChange={(e) => {
                  setPttShortcut(e.target.value)
                  setPreferences({ pttShortcut: e.target.value })
                }}
                className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
              >
                {PTT_SHORTCUT_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value} className="bg-neutral-900">
                    {o.label}
                  </option>
                ))}
              </select>
            }
          />

          <SettingRow
            icon={Lock}
            dot={pttLockedMode ? 'on' : 'off'}
            title="Double-tap for Locked Mode"
            subtitle="Double-tap the push-to-talk key to keep listening hands-free. Tap again to send."
            keywords="ptt locked mode double tap hands free"
            control={
              <Toggle
                on={pttLockedMode}
                onChange={(on) => {
                  setPttLockedMode(on)
                  setPreferences({ pttLockedMode: on })
                }}
                label="Double-tap locked mode"
              />
            }
          />

          <SettingRow
            icon={Volume2}
            dot={pttSounds ? 'on' : 'off'}
            title="Push-to-Talk sounds"
            subtitle="Play audio feedback when starting and ending voice input."
            keywords="ptt sounds audio feedback click beep"
            control={
              <Toggle
                on={pttSounds}
                onChange={(on) => {
                  setPttSounds(on)
                  setPreferences({ pttSounds: on })
                }}
                label="Push-to-Talk sounds"
              />
            }
          />
        </>
      )}
    </>
  )
}
