import { useState } from 'react'
import { MessagesSquare, Mic } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import {
  getMonologurSettings,
  saveMonologurSettings,
  startMonologur,
  stopMonologur
} from '../../../lib/monologurEngine'

export function GeneralTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [monologurEnabled, setMonologurEnabled] = useState(() => getMonologurSettings().enabled)
  const [ttsProvider, setTtsProvider] = useState<'web' | 'deepgram'>(() => getMonologurSettings().ttsProvider)

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
        icon={Mic}
        title="Monologur"
        subtitle="Always-listening AI assistant that provides real-time guidance and suggestions via text-to-speech based on your ongoing conversations."
        keywords="monologur always listening tts speech proactive"
        control={
          <div className="flex items-center gap-2">
            <select
              value={ttsProvider}
              onChange={(e) => {
                const v = e.target.value as 'web' | 'deepgram'
                setTtsProvider(v)
                saveMonologurSettings({ ttsProvider: v })
              }}
              className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
            >
              <option value="web" className="bg-neutral-900">
                Web TTS
              </option>
              <option value="deepgram" className="bg-neutral-900">
                Deepgram Aura
              </option>
            </select>
            <button
              onClick={() => {
                const newValue = !monologurEnabled
                setMonologurEnabled(newValue)
                saveMonologurSettings({ enabled: newValue })
                if (newValue) {
                  startMonologur()
                } else {
                  stopMonologur()
                }
              }}
              className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                monologurEnabled
                  ? 'bg-green-500/20 text-green-400 hover:bg-green-500/30'
                  : 'bg-white/10 text-white/60 hover:bg-white/20'
              }`}
            >
              {monologurEnabled ? 'Enabled' : 'Disabled'}
            </button>
          </div>
        }
      />
    </>
  )
}
