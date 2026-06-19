import { useEffect, useState } from 'react'
import { MessagesSquare, ZoomIn } from 'lucide-react'
import { getPreferences, setPreferences, onPreferencesChange } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [fontScale, setFontScale] = useState(getPreferences().fontScale ?? 1.0)
  useEffect(() => onPreferencesChange((p) => setFontScale(p.fontScale ?? 1.0)), [])

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
