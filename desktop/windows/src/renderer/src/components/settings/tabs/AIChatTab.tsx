import { Cpu, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import type { ClaudeAcpStatus } from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

type ChatRuntimeMode = 'auto' | 'omi-hosted' | 'pi' | 'claude-acp'

function claudeStatusText(status: ClaudeAcpStatus | null): string {
  if (!status) return 'Not checked'
  if (status.configured) return `Available via ${status.command}`
  return status.reason ?? 'Not available'
}

function runtimeSubtitle(chatRuntimeMode: ChatRuntimeMode): string {
  if (chatRuntimeMode === 'claude-acp') {
    return 'Use the local Claude account runtime on this Windows machine.'
  }
  if (chatRuntimeMode === 'pi') return 'Use the native Pi/Omi agent runtime.'
  if (chatRuntimeMode === 'omi-hosted') return 'Use Omi hosted chat only.'
  return 'Use native Pi/Omi when available, otherwise fall back to hosted Omi chat.'
}

export function AIChatTab(): React.JSX.Element {
  const [chatRuntimeMode, setChatRuntimeMode] = useState<ChatRuntimeMode>(
    () => getPreferences().chatRuntimeMode
  )
  const [claudeStatus, setClaudeStatus] = useState<ClaudeAcpStatus | null>(null)
  const [claudeBusy, setClaudeBusy] = useState(false)

  const refreshClaudeStatus = async (): Promise<void> => {
    setClaudeBusy(true)
    try {
      const status = await window.omi.claudeAcpStatus()
      setClaudeStatus(status)
      toast(status.configured ? 'Claude account runtime available' : 'Claude account unavailable', {
        tone: status.configured ? 'success' : 'warn',
        body: status.reason
      })
    } catch (e) {
      toast('Could not check Claude account', { tone: 'error', body: (e as Error).message })
    } finally {
      setClaudeBusy(false)
    }
  }

  return (
    <SettingRow
      icon={Cpu}
      title="Chat runtime"
      subtitle={runtimeSubtitle(chatRuntimeMode)}
      keywords="ai chat runtime pi omi claude acp local account hosted provider"
      control={
        <select
          value={chatRuntimeMode}
          onChange={(e) => {
            const v = e.target.value as ChatRuntimeMode
            setChatRuntimeMode(v)
            setPreferences({ chatRuntimeMode: v })
          }}
          className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none"
        >
          <option value="auto" className="bg-neutral-900">
            Auto
          </option>
          <option value="omi-hosted" className="bg-neutral-900">
            Omi hosted
          </option>
          <option value="pi" className="bg-neutral-900">
            Pi/Omi
          </option>
          <option value="claude-acp" className="bg-neutral-900">
            Claude account
          </option>
        </select>
      }
    >
      <div className="grid gap-3 rounded-md border border-white/[0.08] bg-white/[0.03] p-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-text-primary">Claude account status</div>
          <div className="mt-0.5 text-xs text-text-tertiary">{claudeStatusText(claudeStatus)}</div>
        </div>
        <button
          type="button"
          disabled={claudeBusy}
          onClick={() => void refreshClaudeStatus()}
          className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${claudeBusy ? 'animate-spin' : ''}`} />
          Check
        </button>
      </div>
      <div className="mt-3 rounded-md border border-white/[0.08] bg-white/[0.03] px-3 py-2 text-xs text-text-tertiary">
        Pi/Omi routing is {window.omi.piChatEnabled ? 'enabled' : 'disabled'} in this build. Claude
        routing uses the local Claude command configured on this Windows account.
      </div>
    </SettingRow>
  )
}
