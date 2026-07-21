import { CheckCircle2, KeyRound, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type {
  AvailableModel,
  ByokChatProvider,
  ByokProvider,
  ByokProviderStatus,
  ByokStatus,
  ModelPurpose
} from '../../../../../shared/types'
import { byokProviderFromModelId } from '../../../lib/modelSelection'
import { getPreferences, onPreferencesChange, setPreferences } from '../../../lib/preferences'
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
  { id: 'openrouter', label: 'OpenRouter', placeholder: 'sk-or-...', chat: true },
  { id: 'deepgram', label: 'Deepgram', placeholder: 'Deepgram API key', chat: false },
  { id: 'elevenlabs', label: 'ElevenLabs', placeholder: 'sk_...', chat: false }
]

const EMPTY_DRAFT_KEYS: Record<ByokProvider, string> = {
  openai: '',
  anthropic: '',
  gemini: '',
  openrouter: '',
  deepgram: '',
  elevenlabs: ''
}

const MODEL_PURPOSES: {
  id: ModelPurpose
  label: string
  defaultLabel: string
  description: string
  includeHosted: boolean
}[] = [
  {
    id: 'chat',
    label: 'Chat',
    defaultLabel: 'Provider default',
    description: 'Main window and floating chat replies.',
    includeHosted: true
  },
  {
    id: 'agent',
    label: 'Agent',
    defaultLabel: 'Omi agent default',
    description: 'Action planning and tool-use decisions.',
    includeHosted: false
  },
  {
    id: 'memory',
    label: 'Memory',
    defaultLabel: 'Omi synthesis default',
    description: 'Memory import, integrations, graph, and title synthesis.',
    includeHosted: false
  }
]

function providerLabel(provider: ByokProvider | null | undefined): string {
  return PROVIDERS.find((p) => p.id === provider)?.label ?? provider ?? 'Omi'
}

function statusText(status: ByokProviderStatus | undefined): string {
  if (!status?.configured) return 'Not saved'
  if (status.lastValidationOk === true) return `Saved, validated (${status.maskedKey})`
  if (status.lastValidationOk === false) return `Saved, validation failed (${status.maskedKey})`
  return `Saved (${status.maskedKey})`
}

type ByokBusyKey = `${ByokProvider}:${'save' | 'test' | 'delete'}` | 'use'

export function ByokTab({ active }: { active: boolean }): React.JSX.Element {
  const [byokStatus, setByokStatus] = useState<ByokStatus | null>(null)
  const [draftKeys, setDraftKeys] = useState<Record<ByokProvider, string>>(EMPTY_DRAFT_KEYS)
  const [byokBusy, setByokBusy] = useState<Set<ByokBusyKey>>(() => new Set())
  const [models, setModels] = useState<AvailableModel[]>([])
  const [modelsBusy, setModelsBusy] = useState(false)
  const [selectedModels, setSelectedModels] = useState(getPreferences().defaultModelByPurpose ?? {})
  const [loaded, setLoaded] = useState(false)

  const beginBusy = (key: ByokBusyKey): void => {
    setByokBusy((current) => new Set(current).add(key))
  }

  const endBusy = (key: ByokBusyKey): void => {
    setByokBusy((current) => {
      const next = new Set(current)
      next.delete(key)
      return next
    })
  }

  const isBusy = (key: ByokBusyKey): boolean => byokBusy.has(key)

  const isProviderBusy = (provider: ByokProvider): boolean =>
    isBusy(`${provider}:save`) || isBusy(`${provider}:test`) || isBusy(`${provider}:delete`)

  const refreshByokStatus = async (): Promise<void> => {
    try {
      setByokStatus(await window.omi.byokStatus())
    } catch (e) {
      toast('Could not read BYOK settings', { tone: 'error', body: (e as Error).message })
    }
  }

  const refreshByokModels = async (): Promise<void> => {
    setModelsBusy(true)
    try {
      const result = await window.omi.byokListModels()
      setModels(result.models)
    } catch (e) {
      toast('Could not load BYOK models', { tone: 'error', body: (e as Error).message })
    } finally {
      setModelsBusy(false)
    }
  }

  useEffect(() => {
    return onPreferencesChange((prefs) => {
      setSelectedModels(prefs.defaultModelByPurpose ?? {})
    })
  }, [])

  useEffect(() => {
    if (!active || loaded) return
    setLoaded(true)
    void refreshByokStatus()
    void refreshByokModels()
  }, [active, loaded])

  const configuredModels = useMemo(
    () => models.filter((model) => model.provider === 'omi' || model.configured),
    [models]
  )

  const modelsForPurpose = (purpose: (typeof MODEL_PURPOSES)[number]): AvailableModel[] =>
    configuredModels.filter((model) => purpose.includeHosted || model.provider !== 'omi')

  const modelSelectValue = (purpose: (typeof MODEL_PURPOSES)[number]): string => {
    const modelId = selectedModels[purpose.id] ?? ''
    return modelsForPurpose(purpose).some((model) => model.id === modelId) ? modelId : ''
  }

  const saveProvider = async (provider: ByokProvider): Promise<void> => {
    const key = draftKeys[provider].trim()
    if (!key) {
      toast('Paste a key before saving', { tone: 'warn' })
      return
    }
    const busyKey = `${provider}:save` as const
    beginBusy(busyKey)
    try {
      setByokStatus(await window.omi.byokSave({ provider, key }))
      setDraftKeys((current) => ({ ...current, [provider]: '' }))
      void refreshByokModels()
      toast(`${providerLabel(provider)} key saved`, { tone: 'success' })
    } catch (e) {
      toast('Could not save key', { tone: 'error', body: (e as Error).message })
    } finally {
      endBusy(busyKey)
    }
  }

  const testProvider = async (provider: ByokProvider): Promise<void> => {
    const key = draftKeys[provider].trim()
    const busyKey = `${provider}:test` as const
    beginBusy(busyKey)
    try {
      const result = await window.omi.byokTest({ provider, key: key || undefined })
      if (!key) await refreshByokStatus()
      if (result.ok) {
        toast(`${providerLabel(provider)} key validated`, { tone: 'success' })
      } else {
        toast('Key validation failed', { tone: 'error', body: result.error })
      }
    } catch (e) {
      toast('Key validation failed', { tone: 'error', body: (e as Error).message })
    } finally {
      endBusy(busyKey)
    }
  }

  const deleteProvider = async (provider: ByokProvider): Promise<void> => {
    const busyKey = `${provider}:delete` as const
    beginBusy(busyKey)
    try {
      setByokStatus(await window.omi.byokDelete(provider))
      setDraftKeys((current) => ({ ...current, [provider]: '' }))
      const current = getPreferences().defaultModelByPurpose ?? {}
      setPreferences({
        defaultModelByPurpose: Object.fromEntries(
          Object.entries(current).map(([purpose, modelId]) => [
            purpose,
            byokProviderFromModelId(modelId) === provider ? undefined : modelId
          ])
        )
      })
      void refreshByokModels()
      toast(`${providerLabel(provider)} key removed`, { tone: 'success' })
    } catch (e) {
      toast('Could not remove key', { tone: 'error', body: (e as Error).message })
    } finally {
      endBusy(busyKey)
    }
  }

  const selectChatProvider = async (provider: ByokChatProvider | null): Promise<void> => {
    beginBusy('use')
    try {
      setByokStatus(await window.omi.byokUse({ provider }))
      toast(provider ? 'BYOK chat provider selected' : 'Omi hosted chat selected', {
        tone: 'success'
      })
    } catch (e) {
      toast('Could not change chat provider', { tone: 'error', body: (e as Error).message })
    } finally {
      endBusy('use')
    }
  }

  const selectModel = (purpose: ModelPurpose, modelId: string): void => {
    setPreferences({
      defaultModelByPurpose: {
        ...getPreferences().defaultModelByPurpose,
        [purpose]: modelId || undefined
      }
    })
    toast(modelId ? 'Model selected' : 'Default model selected', {
      tone: 'success'
    })
  }

  return (
    <>
      <SettingRow
        icon={KeyRound}
        title="Default BYOK chat provider"
        subtitle={
          byokStatus?.activeChatProvider
            ? `Chat uses your ${providerLabel(byokStatus.activeChatProvider)} key when BYOK is active.`
            : "Chat uses Omi's hosted model unless a BYOK provider is selected."
        }
        keywords="byok key provider model openrouter openai anthropic gemini api"
        control={
          <select
            value={byokStatus?.activeChatProvider ?? ''}
            disabled={isBusy('use')}
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
      />
      <SettingRow
        icon={KeyRound}
        title="Models by use"
        subtitle="Choose separate models for chat, agent planning, and memory synthesis."
        keywords="byok model picker openai anthropic gemini openrouter chat agent memory model"
      >
        <div className="space-y-3">
          {MODEL_PURPOSES.map((purpose) => {
            const purposeModels = modelsForPurpose(purpose)
            return (
              <div
                key={purpose.id}
                className="grid gap-2 rounded-md border border-white/[0.08] bg-white/[0.03] p-3 md:grid-cols-[130px_minmax(220px,1fr)]"
              >
                <div className="min-w-0">
                  <div className="text-sm font-semibold text-text-primary">{purpose.label}</div>
                  <div className="text-xs text-text-tertiary">{purpose.description}</div>
                </div>
                <select
                  value={modelSelectValue(purpose)}
                  disabled={modelsBusy || purposeModels.length === 0}
                  onChange={(e) => selectModel(purpose.id, e.target.value)}
                  className="min-h-9 min-w-0 rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none disabled:opacity-50"
                >
                  <option value="" className="bg-neutral-900">
                    {modelsBusy ? 'Loading models...' : purpose.defaultLabel}
                  </option>
                  {purposeModels.map((model) => (
                    <option key={model.id} value={model.id} className="bg-neutral-900">
                      {model.providerLabel} · {model.label}
                    </option>
                  ))}
                </select>
              </div>
            )
          })}
        </div>
      </SettingRow>
      <SettingRow
        icon={KeyRound}
        title="Provider keys"
        subtitle="Keys are stored with Windows secure storage and are never sent to Omi billing endpoints."
        keywords="byok api key openai anthropic gemini openrouter deepgram elevenlabs tts stt"
      >
        <div className="space-y-3">
          {PROVIDERS.map((provider) => {
            const status = byokStatus?.providers[provider.id]
            const busy = isProviderBusy(provider.id)
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
    </>
  )
}
