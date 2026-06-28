import { useEffect, useState } from 'react'
import { Cpu, Server, Cloud, KeyRound, Globe } from 'lucide-react'
import { SettingRow } from '../SettingRow'
import {
  getModelConfig,
  setModelConfig,
  setApiKey,
  getApiKey,
  type ModelConfig
} from '../../../lib/modelConfig'
import { providersByRegion, getProvider, type ProviderInfo } from '../../../../../shared/providers'

const selectCls =
  'rounded-md bg-white/10 px-2 py-1.5 text-sm text-white focus:outline-none min-w-[14rem]'
const optCls = 'bg-neutral-900'

function ProviderSelect(props: {
  value: string | undefined
  onChange: (id: string) => void
}): React.JSX.Element {
  return (
    <select
      className={selectCls}
      value={props.value ?? ''}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="" className={optCls}>
        Choose a provider…
      </option>
      {providersByRegion().map((group) => (
        <optgroup key={group.region} label={group.label} className={optCls}>
          {group.providers.map((p) => (
            <option key={p.id} value={p.id} className={optCls}>
              {p.name}
            </option>
          ))}
        </optgroup>
      ))}
    </select>
  )
}

function ModelSelect(props: {
  provider: ProviderInfo
  value: string | undefined
  onChange: (id: string) => void
}): React.JSX.Element {
  const { provider } = props
  return (
    <select
      className={selectCls}
      value={props.value ?? ''}
      onChange={(e) => props.onChange(e.target.value)}
    >
      <option value="" className={optCls}>
        {provider.dynamicModels ? 'Pick or type a model…' : 'Choose a model…'}
      </option>
      {provider.models.map((m) => (
        <option key={m.id} value={m.id} className={optCls}>
          {m.label}
          {m.note ? ` — ${m.note}` : ''}
        </option>
      ))}
    </select>
  )
}

export function ModelsTab(): React.JSX.Element {
  const [cfg, setCfg] = useState<ModelConfig>(getModelConfig())
  const provider = cfg.providerId ? getProvider(cfg.providerId) : undefined

  // Keep local UI state in sync with persisted config.
  useEffect(() => setCfg(getModelConfig()), [])

  const update = (patch: Partial<ModelConfig>): void => {
    setModelConfig(patch)
    setCfg(getModelConfig())
  }

  return (
    <>
      <SettingRow
        icon={Cpu}
        title="AI engine"
        subtitle="Cortex can use the built-in cloud engine (no setup), or run against your own local model or a cloud provider with your own API key."
        keywords="model provider llm engine local cloud byok ollama lm studio"
        control={
          <select
            className={selectCls}
            value={cfg.mode}
            onChange={(e) => update({ mode: e.target.value as ModelConfig['mode'] })}
          >
            <option value="backend" className={optCls}>
              Built-in cloud engine (default)
            </option>
            <option value="provider" className={optCls}>
              Choose my own provider
            </option>
          </select>
        }
      />

      {cfg.mode === 'provider' && (
        <>
          <SettingRow
            icon={provider?.mode === 'local' ? Server : Cloud}
            title="Provider"
            subtitle="Local providers run privately on your machine. Cloud providers are grouped by region so you control where your data is processed."
            keywords="region north america europe china global ollama lmstudio openai anthropic mistral qwen glm kimi deepseek"
            control={
              <ProviderSelect
                value={cfg.providerId}
                onChange={(providerId) => update({ providerId, modelId: undefined })}
              />
            }
          />

          {provider && (
            <SettingRow
              icon={Cpu}
              title="Model"
              subtitle={provider.note ?? `Models offered by ${provider.name}.`}
              dot={cfg.modelId ? 'on' : 'off'}
              keywords="model variant flagship vision reasoning"
              control={
                <ModelSelect
                  provider={provider}
                  value={cfg.modelId}
                  onChange={(modelId) => update({ modelId })}
                />
              }
            >
              {provider.dynamicModels && (
                <input
                  className="input-field mt-2"
                  placeholder="…or type an exact model id (e.g. a model you pulled locally)"
                  defaultValue={cfg.modelId ?? ''}
                  onBlur={(e) => update({ modelId: e.target.value.trim() || undefined })}
                />
              )}
            </SettingRow>
          )}

          {provider?.id === 'custom' && (
            <SettingRow
              icon={Globe}
              title="Base URL"
              subtitle="Any OpenAI-compatible endpoint, e.g. http://localhost:8000/v1"
              keywords="custom endpoint base url self-hosted"
            >
              <input
                className="input-field mt-2"
                placeholder="https://your-endpoint/v1"
                defaultValue={cfg.customBaseUrl ?? ''}
                onBlur={(e) => update({ customBaseUrl: e.target.value.trim() || undefined })}
              />
            </SettingRow>
          )}

          {provider && provider.requiresApiKey && (
            <SettingRow
              icon={KeyRound}
              title="API key"
              subtitle={`Your ${provider.name} key. Stored locally on this device only.`}
              dot={getApiKey(provider.id) ? 'on' : 'warn'}
              keywords="api key secret token byok credentials"
            >
              <input
                type="password"
                className="input-field mt-2"
                placeholder={`Paste your ${provider.name} API key`}
                defaultValue={getApiKey(provider.id)}
                onBlur={(e) => {
                  setApiKey(provider.id, e.target.value.trim())
                  setCfg(getModelConfig())
                }}
              />
              {provider.docsUrl && (
                <a
                  href={provider.docsUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block text-xs text-[color:var(--accent)] hover:underline"
                >
                  Get a key / view models →
                </a>
              )}
            </SettingRow>
          )}
        </>
      )}
    </>
  )
}
