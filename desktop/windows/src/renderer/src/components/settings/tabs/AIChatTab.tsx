import {
  BotMessageSquare,
  CheckCircle2,
  Cpu,
  KeyRound,
  MessagesSquare,
  RefreshCw,
  Trash2
} from 'lucide-react'
import { useEffect, useState } from 'react'
import type {
  ByokChatProvider,
  ByokProvider,
  ByokProviderStatus,
  ByokStatus,
  ClaudeAcpStatus
} from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

type ProviderConfig = {
  id: ByokProvider
  label: string
  placeholder: string
  chat: boolean
}

const PROVIDERS: ProviderConfig[] = [
  { id: 'openai', label: 'OpenAI', placeholder: 'sk-...', chat: true },
  { id: 'anthropic', label: 'Anthropic', placeholder: 'sk-ant-...', chat: true },
  { id: 'gemini', label: 'Gemini', placeholder: 'AIza...', chat: true },
  { id: 'deepgram', label: 'Deepgram', placeholder: 'Deepgram API key', chat: false }
]

const EMPTY_DRAFT_KEYS: Record<ByokProvider, string> = {
  openai: '',
  anthropic: '',
  gemini: '',
  deepgram: ''
}

function statusText(status: ByokProviderStatus | undefined): string {
  if (!status?.configured) return 'Not saved'
  if (status.lastValidationOk === true) return `Saved, validated (${status.maskedKey})`
  if (status.lastValidationOk === false) return `Saved, validation failed (${status.maskedKey})`
  return `Saved (${status.maskedKey})`
}

function claudeStatusText(status: ClaudeAcpStatus | null): string {
  if (!status) return 'Not checked'
  if (status.configured) return `Available via ${status.command}`
  return status.reason ?? 'Not available'
}

export function AIChatTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [chatRuntimeMode, setChatRuntimeMode] = useState(getPreferences().chatRuntimeMode)
  const [byokStatus, setByokStatus] = useState<ByokStatus | null>(null)
  const [claudeStatus, setClaudeStatus] = useState<ClaudeAcpStatus | null>(null)
  const [draftKeys, setDraftKeys] = useState<Record<ByokProvider, string>>(EMPTY_DRAFT_KEYS)
  const [byokBusy, setByokBusy] = useState('')
  const [claudeBusy, setClaudeBusy] = useState(false)

  const refreshByokStatus = async (): Promise<void> => {
    try {
      setByokStatus(await window.omi.byokStatus())
    } catch (e) {
      toast('Could not read BYOK settings', { tone: 'error', body: (e as Error).message })
    }
  }

  useEffect(() => {
    let canceled = false
    window.omi
      .byokStatus()
      .then((status) => {
        if (!canceled) setByokStatus(status)
      })
      .catch((e) => {
        if (!canceled) {
          toast('Could not read BYOK settings', { tone: 'error', body: (e as Error).message })
        }
      })
    return () => {
      canceled = true
    }
  }, [])

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

  const saveProvider = async (provider: ByokProvider): Promise<void> => {
    const key = draftKeys[provider].trim()
    if (!key) {
      toast('Paste a key before saving', { tone: 'warn' })
      return
    }
    setByokBusy(`${provider}:save`)
    try {
      setByokStatus(await window.omi.byokSave({ provider, key }))
      setDraftKeys((current) => ({ ...current, [provider]: '' }))
      toast(`${PROVIDERS.find((p) => p.id === provider)?.label ?? provider} key saved`, {
        tone: 'success'
      })
    } catch (e) {
      toast('Could not save key', { tone: 'error', body: (e as Error).message })
    } finally {
      setByokBusy('')
    }
  }

  const testProvider = async (provider: ByokProvider): Promise<void> => {
    const key = draftKeys[provider].trim()
    setByokBusy(`${provider}:test`)
    try {
      const result = await window.omi.byokTest({ provider, key: key || undefined })
      if (!key) await refreshByokStatus()
      if (result.ok) {
        toast(`${PROVIDERS.find((p) => p.id === provider)?.label ?? provider} key validated`, {
          tone: 'success'
        })
      } else {
        toast('Key validation failed', { tone: 'error', body: result.error })
      }
    } catch (e) {
      toast('Key validation failed', { tone: 'error', body: (e as Error).message })
    } finally {
      setByokBusy('')
    }
  }

  const deleteProvider = async (provider: ByokProvider): Promise<void> => {
    setByokBusy(`${provider}:delete`)
    try {
      setByokStatus(await window.omi.byokDelete(provider))
      setDraftKeys((current) => ({ ...current, [provider]: '' }))
      toast(`${PROVIDERS.find((p) => p.id === provider)?.label ?? provider} key removed`, {
        tone: 'success'
      })
    } catch (e) {
      toast('Could not remove key', { tone: 'error', body: (e as Error).message })
    } finally {
      setByokBusy('')
    }
  }

  const selectChatProvider = async (provider: ByokChatProvider | null): Promise<void> => {
    setByokBusy('use')
    try {
      setByokStatus(await window.omi.byokUse({ provider }))
      toast(provider ? 'BYOK chat provider selected' : 'Omi hosted chat selected', {
        tone: 'success'
      })
    } catch (e) {
      toast('Could not change chat provider', { tone: 'error', body: (e as Error).message })
    } finally {
      setByokBusy('')
    }
  }

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
        icon={Cpu}
        title="Chat runtime"
        subtitle={
          chatRuntimeMode === 'auto'
            ? 'Use Pi/Omi when enabled, otherwise your selected BYOK provider, otherwise hosted Omi chat.'
            : chatRuntimeMode === 'claude-acp'
              ? 'Use the local Claude account runtime on this Windows machine.'
              : chatRuntimeMode === 'pi'
                ? 'Use the Pi/Omi tool bridge when this build enables it.'
                : 'Use Omi hosted chat only.'
        }
        keywords="ai chat runtime pi omi claude acp local account hosted provider"
        control={
          <select
            value={chatRuntimeMode}
            onChange={(e) => {
              const v = e.target.value as typeof chatRuntimeMode
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
        {chatRuntimeMode === 'claude-acp' && (
          <div className="flex flex-col gap-3 rounded-md border border-white/[0.08] bg-white/[0.03] p-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-text-primary">Claude account status</div>
              <div className="mt-0.5 text-xs text-text-tertiary">
                {claudeStatusText(claudeStatus)}
              </div>
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
        )}
      </SettingRow>
      <SettingRow
        icon={BotMessageSquare}
        title="Model and provider"
        subtitle={
          byokStatus?.activeChatProvider
            ? `Chat uses your ${PROVIDERS.find((p) => p.id === byokStatus.activeChatProvider)?.label} key.`
            : "Windows chat uses Omi's hosted model path for the main and floating chat surfaces."
        }
        keywords="ai chat model provider llm hosted omi account claude openai gemini anthropic deepgram byok key"
        control={
          <select
            value={byokStatus?.activeChatProvider ?? ''}
            disabled={byokBusy === 'use'}
            onChange={(e) => {
              const provider = e.target.value ? (e.target.value as ByokChatProvider) : null
              void selectChatProvider(provider)
            }}
            className="rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none disabled:opacity-50"
          >
            <option value="" className="bg-neutral-900">
              Omi hosted chat
            </option>
            {PROVIDERS.filter((provider) => provider.chat).map((provider) => (
              <option
                key={provider.id}
                value={provider.id}
                disabled={!byokStatus?.providers[provider.id].configured}
                className="bg-neutral-900"
              >
                {provider.label}
              </option>
            ))}
          </select>
        }
      >
        <div className="space-y-3">
          {PROVIDERS.map((provider) => {
            const status = byokStatus?.providers[provider.id]
            const busyPrefix = `${provider.id}:`
            const busy = byokBusy.startsWith(busyPrefix)
            return (
              <div
                key={provider.id}
                className="grid gap-3 rounded-md border border-white/[0.08] bg-white/[0.03] p-3 lg:grid-cols-[150px_minmax(220px,1fr)_auto]"
              >
                <div className="flex min-w-0 items-center gap-2">
                  <KeyRound className="h-4 w-4 shrink-0 text-white/50" strokeWidth={1.75} />
                  <div className="min-w-0">
                    <div className="text-sm font-semibold text-text-primary">{provider.label}</div>
                    <div className="truncate text-xs text-text-tertiary">{statusText(status)}</div>
                  </div>
                </div>
                <input
                  type="password"
                  autoComplete="off"
                  value={draftKeys[provider.id]}
                  onChange={(e) =>
                    setDraftKeys((current) => ({ ...current, [provider.id]: e.target.value }))
                  }
                  placeholder={provider.placeholder}
                  className="min-h-9 min-w-0 rounded-md border border-white/[0.08] bg-black/20 px-3 text-sm text-white outline-none placeholder:text-white/30 focus:border-[color:var(--accent)]"
                />
                <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                  <button
                    type="button"
                    disabled={busy || !draftKeys[provider.id].trim()}
                    onClick={() => void saveProvider(provider.id)}
                    className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Save
                  </button>
                  <button
                    type="button"
                    disabled={busy || (!draftKeys[provider.id].trim() && !status?.configured)}
                    onClick={() => void testProvider(provider.id)}
                    className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                    Test
                  </button>
                  <button
                    type="button"
                    aria-label={`Remove ${provider.label} key`}
                    disabled={busy || !status?.configured}
                    onClick={() => void deleteProvider(provider.id)}
                    className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
                  >
                    <Trash2 className="h-4 w-4" />
                    Remove
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </SettingRow>
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
