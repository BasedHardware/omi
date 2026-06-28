// User's model/provider selection + BYOK credentials, persisted in localStorage.
//
// Cortex routes its agentic LLM calls either through the bundled Cortex backend
// (default — works out of the box, no setup) or, once the user configures one
// here, directly through a chosen local/cloud provider (see shared/providers.ts).
import { getProvider, type ProviderInfo, type ModelInfo } from '../../../shared/providers'

const KEY = 'cortex-model-config-v1'

export type ModelConfig = {
  /** 'backend' = Cortex proxy (default). 'provider' = use the selected provider below. */
  mode: 'backend' | 'provider'
  /** Selected provider id from shared/providers.ts (when mode === 'provider'). */
  providerId?: string
  /** Selected model id within that provider. */
  modelId?: string
  /** Per-provider API keys (BYOK). Keyed by provider id. Stored locally only. */
  apiKeys: Record<string, string>
  /** Override base URL (for the "custom" provider, or self-hosted endpoints). */
  customBaseUrl?: string
}

const defaults: ModelConfig = { mode: 'backend', apiKeys: {} }

function load(): ModelConfig {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...defaults }
    const parsed = JSON.parse(raw) as Partial<ModelConfig>
    return { ...defaults, ...parsed, apiKeys: { ...(parsed.apiKeys ?? {}) } }
  } catch {
    return { ...defaults }
  }
}

let current: ModelConfig = load()
const listeners = new Set<(c: ModelConfig) => void>()

function persist(): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(current))
  } catch {
    /* quota / privacy mode */
  }
  listeners.forEach((cb) => cb(current))
}

export function getModelConfig(): ModelConfig {
  return current
}

export function setModelConfig(patch: Partial<ModelConfig>): void {
  current = { ...current, ...patch, apiKeys: { ...current.apiKeys, ...(patch.apiKeys ?? {}) } }
  persist()
}

export function setApiKey(providerId: string, key: string): void {
  current = { ...current, apiKeys: { ...current.apiKeys, [providerId]: key } }
  persist()
}

export function getApiKey(providerId: string): string {
  return current.apiKeys[providerId] ?? ''
}

export function onModelConfigChange(cb: (c: ModelConfig) => void): () => void {
  listeners.add(cb)
  return () => listeners.delete(cb)
}

export type ResolvedTarget = {
  provider: ProviderInfo
  model: ModelInfo | undefined
  baseUrl: string
  apiKey: string
}

/**
 * Resolve the active provider target, or null when Cortex should use the default
 * backend (mode === 'backend', nothing configured, or a missing required key).
 */
export function resolveTarget(): ResolvedTarget | null {
  if (current.mode !== 'provider' || !current.providerId) return null
  const provider = getProvider(current.providerId)
  if (!provider) return null
  const baseUrl =
    (provider.id === 'custom' ? current.customBaseUrl : provider.baseUrl)?.trim() || ''
  if (!baseUrl) return null
  const apiKey = getApiKey(provider.id)
  if (provider.requiresApiKey && !apiKey) return null
  const model = provider.models.find((m) => m.id === current.modelId)
  return { provider, model, baseUrl, apiKey }
}
