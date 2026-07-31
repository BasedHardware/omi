import { useState, useEffect } from 'react'
import { MessagesSquare, Languages } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [signLanguageEnabled, setSignLanguageEnabled] = useState(false)

  useEffect(() => {
    window.omi
      ?.signLanguageGetEnabled()
      .then(setSignLanguageEnabled)
      .catch(() => {})
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
        icon={Languages}
        title="Sign-language translation"
        subtitle="Transcribe spoken text into sign-language poses via the sign.mt service. Disabled by default — all transcript text is sent to an external API, which requires explicit consent."
        keywords="sign language translation sign.mt consent privacy"
        control={
          <button
            onClick={async () => {
              const next = !signLanguageEnabled
              setSignLanguageEnabled(next)
              await window.omi?.signLanguageSetEnabled(next)
            }}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              signLanguageEnabled
                ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                : 'bg-white/10 text-white/60 hover:bg-white/20'
            }`}
          >
            {signLanguageEnabled ? 'Enabled' : 'Disabled'}
          </button>
        }
      />
    </>
  )
}
