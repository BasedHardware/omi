import { useState } from 'react'
import { MessageSquare, FolderOpen, Bot, Sparkles } from 'lucide-react'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { SettingRow } from '../SettingRow'
import { Toggle } from '../Toggle'

export function AIChatTab(): React.JSX.Element {
  const prefs = getPreferences()
  const [screenContext, setScreenContext] = useState(prefs.chatScreenContext ?? true)
  const [memoryContext, setMemoryContext] = useState(prefs.chatMemoryContext ?? true)
  const [workspaceDir, setWorkspaceDir] = useState(prefs.chatWorkspaceDir ?? '')

  return (
    <>
      <SettingRow
        icon={Bot}
        title="AI model"
        subtitle="Omi uses Claude (Anthropic) for desktop chat — the same model powering the floating bar. Responses draw from your memories, conversations, and current screen context."
        keywords="model claude anthropic ai provider chat"
      >
        <div className="mt-3 flex items-center gap-3 rounded-xl bg-white/[0.04] px-4 py-3">
          <Sparkles className="h-4 w-4 shrink-0 text-purple-400" />
          <div>
            <p className="text-sm font-medium text-text-primary">Claude (via Omi)</p>
            <p className="text-xs text-text-tertiary">Best accuracy for personal context & reasoning</p>
          </div>
          <span className="ml-auto rounded-full bg-purple-500/15 px-2.5 py-0.5 text-xs font-medium text-purple-400">
            Active
          </span>
        </div>
      </SettingRow>

      <SettingRow
        icon={MessageSquare}
        dot={memoryContext ? 'on' : 'off'}
        title="Use memories in chat"
        subtitle="When on, Omi includes your personal memories and past conversations as context for every AI response. Disable for faster, context-free answers."
        keywords="memory context chat ai personalization"
        control={
          <Toggle
            on={memoryContext}
            onChange={(on) => {
              setMemoryContext(on)
              setPreferences({ chatMemoryContext: on })
            }}
            label="Use memories in chat"
          />
        }
      />

      <SettingRow
        icon={MessageSquare}
        dot={screenContext ? 'on' : 'off'}
        title="Use screen context in chat"
        subtitle="Includes the current screen content (via Rewind) as context when you ask questions. Disable to keep chat answers generic."
        keywords="screen context rewind chat current activity"
        control={
          <Toggle
            on={screenContext}
            onChange={(on) => {
              setScreenContext(on)
              setPreferences({ chatScreenContext: on })
            }}
            label="Use screen context in chat"
          />
        }
      />

      <SettingRow
        icon={FolderOpen}
        title="Workspace directory"
        subtitle="When set, Omi includes a file listing of this directory as context for coding and project questions."
        keywords="workspace directory folder project context code"
      >
        <div className="mt-3 flex items-center gap-2">
          <input
            type="text"
            value={workspaceDir}
            onChange={(e) => setWorkspaceDir(e.target.value)}
            onBlur={() => setPreferences({ chatWorkspaceDir: workspaceDir })}
            placeholder="/Users/you/projects/my-app"
            className="flex-1 rounded-lg bg-white/10 px-3 py-2 text-sm text-text-secondary placeholder:text-text-quaternary focus:outline-none"
          />
          <button
            onClick={async () => {
              const dir = await window.omi.pickDirectory?.()
              if (dir) {
                setWorkspaceDir(dir)
                setPreferences({ chatWorkspaceDir: dir })
              }
            }}
            className="shrink-0 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-sm text-text-tertiary hover:bg-white/[0.08] hover:text-text-secondary"
          >
            Browse…
          </button>
        </div>
        {workspaceDir && (
          <button
            onClick={() => {
              setWorkspaceDir('')
              setPreferences({ chatWorkspaceDir: '' })
            }}
            className="mt-2 text-xs text-red-400/70 hover:text-red-400"
          >
            Clear workspace
          </button>
        )}
      </SettingRow>
    </>
  )
}
