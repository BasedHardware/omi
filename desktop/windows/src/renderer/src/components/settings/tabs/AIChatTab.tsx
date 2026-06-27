import { BotMessageSquare, Cpu, MessagesSquare, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import type {
  AvailableModel,
  ClaudeAcpStatus,
  ModelListResult,
  ModelPurpose
} from '../../../../../shared/types'
import { getPreferences, setPreferences } from '../../../lib/preferences'
import { toast } from '../../../lib/toast'
import { SettingRow } from '../SettingRow'

const MODEL_PURPOSES: { id: ModelPurpose; label: string }[] = [
  { id: 'chat', label: 'Chat' },
  { id: 'agent', label: 'Agent tasks' },
  { id: 'memory', label: 'Memory extraction' }
]

function claudeStatusText(status: ClaudeAcpStatus | null): string {
  if (!status) return 'Not checked'
  if (status.configured) return `Available via ${status.command}`
  return status.reason ?? 'Not available'
}

function modelLabel(model: AvailableModel): string {
  return `${model.providerLabel} · ${model.label}`
}

function currentModelLabel(models: AvailableModel[], modelId: string | undefined): string {
  if (!modelId) return 'Omi Sonnet'
  const model = models.find((candidate) => candidate.id === modelId)
  return model ? modelLabel(model) : 'Saved model unavailable'
}

export function AIChatTab(): React.JSX.Element {
  const [chatHistoryMode, setChatHistoryMode] = useState(getPreferences().chatHistoryMode)
  const [chatRuntimeMode, setChatRuntimeMode] = useState(getPreferences().chatRuntimeMode)
  const [modelPurpose, setModelPurpose] = useState<ModelPurpose>(
    () => getPreferences().modelPurpose ?? 'chat'
  )
  const [defaultModelByPurpose, setDefaultModelByPurpose] = useState<
    Partial<Record<ModelPurpose, string>>
  >(() => getPreferences().defaultModelByPurpose ?? {})
  const [modelList, setModelList] = useState<ModelListResult | null>(null)
  const [modelsBusy, setModelsBusy] = useState(false)
  const [claudeStatus, setClaudeStatus] = useState<ClaudeAcpStatus | null>(null)
  const [claudeBusy, setClaudeBusy] = useState(false)

  const selectedModelId = defaultModelByPurpose[modelPurpose]
  const models = modelList?.models ?? []
  const selectableModels = models.filter((model) => model.id !== 'omi:omi-sonnet')
  const selectedModelLabel = useMemo(
    () => currentModelLabel(models, selectedModelId),
    [models, selectedModelId]
  )

  const refreshModels = async (): Promise<void> => {
    setModelsBusy(true)
    try {
      setModelList(await window.omi.byokListModels())
    } catch (e) {
      toast('Could not load models', { tone: 'error', body: (e as Error).message })
    } finally {
      setModelsBusy(false)
    }
  }

  useEffect(() => {
    void refreshModels()
  }, [])

  const saveModelPurpose = (next: ModelPurpose): void => {
    setModelPurpose(next)
    setPreferences({ modelPurpose: next })
  }

  const saveDefaultModel = (modelId: string): void => {
    const current = getPreferences().defaultModelByPurpose ?? {}
    const next = { ...current }
    if (modelId) {
      next[modelPurpose] = modelId
    } else {
      delete next[modelPurpose]
    }
    setDefaultModelByPurpose(next)
    setPreferences({ defaultModelByPurpose: next })
    toast('Default model saved', { tone: 'success' })
  }

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
            ? 'Use native Pi/Omi, then BYOK if configured, then hosted Omi chat.'
            : chatRuntimeMode === 'claude-acp'
              ? 'Use the local Claude account runtime on this Windows machine.'
              : chatRuntimeMode === 'pi'
                ? 'Use the native Pi/Omi agent runtime.'
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
        title="Default model"
        subtitle={`${MODEL_PURPOSES.find((purpose) => purpose.id === modelPurpose)?.label}: ${selectedModelLabel}`}
        keywords="ai chat model purpose default selected dropdown openrouter byok provider"
        control={
          <button
            type="button"
            disabled={modelsBusy}
            onClick={() => void refreshModels()}
            className="btn-ghost inline-flex min-h-9 items-center gap-1.5 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${modelsBusy ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <select
            value={modelPurpose}
            onChange={(e) => saveModelPurpose(e.target.value as ModelPurpose)}
            className="glass-subtle min-w-0 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            {MODEL_PURPOSES.map((purpose) => (
              <option key={purpose.id} value={purpose.id} className="bg-neutral-900">
                {purpose.label}
              </option>
            ))}
          </select>
          <select
            value={selectedModelId ?? ''}
            onChange={(e) => saveDefaultModel(e.target.value)}
            className="glass-subtle min-w-0 rounded-lg px-4 py-3 text-sm text-text-secondary focus:outline-none"
          >
            <option value="" className="bg-neutral-900">
              Omi Sonnet
            </option>
            {selectedModelId && !models.some((model) => model.id === selectedModelId) && (
              <option value={selectedModelId} className="bg-neutral-900">
                Saved model unavailable
              </option>
            )}
            {selectableModels.map((model) => (
              <option key={model.id} value={model.id} className="bg-neutral-900">
                {modelLabel(model)}
              </option>
            ))}
          </select>
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
