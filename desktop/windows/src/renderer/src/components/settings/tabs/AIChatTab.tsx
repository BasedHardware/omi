import { BotMessageSquare, Cpu, MessagesSquare } from 'lucide-react'
import { useState } from 'react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'

export function AIChatTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)

  return (
    <>
      <SettingRow
        icon={MessagesSquare}
        title="Chat history"
        subtitle="Use one ongoing conversation shared with the floating bar, or start a fresh conversation each launch."
        keywords="ai chat conversation thread floating bar history infinite"
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
              One ongoing conversation
            </option>
            <option value="per-launch" className="bg-neutral-900">
              New conversation each launch
            </option>
          </select>
        }
      />
      <SettingRow
        icon={BotMessageSquare}
        title="Model and provider"
        subtitle="Windows chat uses Omi's hosted model path for the main and floating chat surfaces."
        keywords="ai chat model provider llm hosted omi account claude openai gemini"
      />
      <SettingRow
        icon={Cpu}
        title="Action planning"
        subtitle={
          window.omi.automationEnabled
            ? 'Desktop action planning is available when Let Omi take actions is enabled in Privacy.'
            : 'Desktop action planning is disabled in this build.'
        }
        keywords="ai chat agent action planning automation take actions settings"
      />
    </>
  )
}
