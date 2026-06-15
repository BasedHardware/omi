import { useState } from 'react'
import { MessagesSquare } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)

  return (
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
  )
}
