import { useState } from 'react'
import { Keyboard } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'

const OVERLAY_SHORTCUT_OPTIONS = [
  { value: 'CommandOrControl+Space', label: 'Ctrl+Space (default)' },
  { value: 'Alt+Space', label: 'Alt+Space' },
  { value: 'CommandOrControl+Shift+Space', label: 'Ctrl+Shift+Space' },
  { value: 'CommandOrControl+G', label: 'Ctrl+G' },
  { value: 'CommandOrControl+Shift+G', label: 'Ctrl+Shift+G' },
  { value: 'F12', label: 'F12' },
  { value: 'Alt+G', label: 'Alt+G' }
]

export function ShortcutsTab(): React.JSX.Element {
  const [shortcut, setShortcut] = useState(
    getPreferences().overlayShortcut ?? 'CommandOrControl+Space'
  )

  const apply = (value: string): void => {
    setShortcut(value)
    setPreferences({ overlayShortcut: value })
    // Push to main process so it takes effect immediately without restart.
    void window.omiOverlay?.setAccelerator(value)
  }

  return (
    <SettingRow
      icon={Keyboard}
      title="Ask Omi shortcut"
      subtitle="Global keyboard shortcut to open the floating Ask Omi bar from anywhere. Takes effect immediately — no restart needed."
      keywords="shortcut hotkey keyboard overlay ask omi floating bar global"
      control={
        <select
          value={shortcut}
          onChange={(e) => apply(e.target.value)}
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
  )
}
