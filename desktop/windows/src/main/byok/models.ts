import type { AvailableModel, ByokChatProvider, ModelListResult } from '../../shared/types'
import { BYOK_CHAT_PROVIDERS, loadByokKey } from './store'

type FetchLike = typeof fetch
type JsonRecord = Record<string, unknown>

export type ByokModelsOptions = {
  fetchImpl?: FetchLike
  now?: () => number
  timeoutMs?: number
}

type ProviderModel = {
  model: string
  label: string
}

const PROVIDER_LABELS: Record<'omi' | ByokChatProvider, string> = {
  omi: 'Omi',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  openrouter: 'OpenRouter'
}

const STATIC_MODELS: Record<ByokChatProvider, ProviderModel[]> = {
  openai: [
    { model: 'gpt-4o-mini', label: 'GPT-4o mini' },
    { model: 'gpt-4o', label: 'GPT-4o' },
    { model: 'gpt-4.1-mini', label: 'GPT-4.1 mini' }
  ],
  anthropic: [
    { model: 'claude-3-5-sonnet-latest', label: 'Claude 3.5 Sonnet' },
    { model: 'claude-3-5-haiku-latest', label: 'Claude 3.5 Haiku' }
  ],
  gemini: [
    { model: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    { model: 'gemini-1.5-pro', label: 'Gemini 1.5 Pro' }
  ],
  openrouter: [
    { model: 'openrouter/auto', label: 'Auto router' },
    { model: 'anthropic/claude-3.5-sonnet', label: 'Claude 3.5 Sonnet' },
    { model: 'openai/gpt-4o-mini', label: 'GPT-4o mini' }
  ]
}

const HOSTED_MODEL: AvailableModel = {
  id: 'omi:omi-sonnet',
  provider: 'omi',
  providerLabel: PROVIDER_LABELS.omi,
  model: 'omi-sonnet',
  label: 'Omi Sonnet',
  configured: true,
  source: 'hosted'
}

const MODEL_FETCH_TIMEOUT_MS = 10_000

function available(provider: ByokChatProvider, model: ProviderModel): AvailableModel {
  return {
    id: `${provider}:${model.model}`,
    provider,
    providerLabel: PROVIDER_LABELS[provider],
    model: model.model,
    label: model.label,
    configured: true,
    source: 'byok'
  }
}

function parseDataArray(raw: unknown): JsonRecord[] {
  if (!raw || typeof raw !== 'object') return []
  const data = (raw as { data?: unknown }).data
  return Array.isArray(data)
    ? data.filter((item): item is JsonRecord => !!item && typeof item === 'object')
    : []
}

function labelFrom(item: JsonRecord, fallback: string): string {
  const name = item.name
  return typeof name === 'string' && name.trim() ? name.trim() : fallback
}

async function fetchWithTimeout(
  fetchImpl: FetchLike,
  url: string,
  init: RequestInit,
  timeoutMs: number
): Promise<Response> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), Math.max(1, timeoutMs))
  try {
    return await fetchImpl(url, { ...init, signal: controller.signal })
  } finally {
    clearTimeout(timeout)
  }
}

async function fetchOpenAiModels(
  fetchImpl: FetchLike,
  key: string,
  timeoutMs: number
): Promise<ProviderModel[]> {
  const response = await fetchWithTimeout(
    fetchImpl,
    'https://api.openai.com/v1/models',
    {
      headers: { authorization: `Bearer ${key}` }
    },
    timeoutMs
  )
  if (!response.ok) throw new Error(`OpenAI models failed with HTTP ${response.status}`)
  const items = parseDataArray(await response.json())
  return items
    .map((item) => String(item.id ?? ''))
    .filter((id) => /^(gpt-|o\d)/.test(id))
    .slice(0, 80)
    .map((model) => ({ model, label: model }))
}

async function fetchAnthropicModels(
  fetchImpl: FetchLike,
  key: string,
  timeoutMs: number
): Promise<ProviderModel[]> {
  const response = await fetchWithTimeout(
    fetchImpl,
    'https://api.anthropic.com/v1/models',
    {
      headers: { 'anthropic-version': '2023-06-01', 'x-api-key': key }
    },
    timeoutMs
  )
  if (!response.ok) throw new Error(`Anthropic models failed with HTTP ${response.status}`)
  const items = parseDataArray(await response.json())
  return items
    .map((item) => {
      const model = String(item.id ?? '')
      return model ? { model, label: labelFrom(item, model) } : null
    })
    .filter((item): item is ProviderModel => !!item)
}

async function fetchGeminiModels(
  fetchImpl: FetchLike,
  key: string,
  timeoutMs: number
): Promise<ProviderModel[]> {
  const response = await fetchWithTimeout(
    fetchImpl,
    'https://generativelanguage.googleapis.com/v1beta/models',
    {
      headers: { 'x-goog-api-key': key }
    },
    timeoutMs
  )
  if (!response.ok) throw new Error(`Gemini models failed with HTTP ${response.status}`)
  const raw = (await response.json()) as { models?: unknown }
  const models = Array.isArray(raw.models) ? raw.models : []
  return models
    .filter((item): item is JsonRecord => !!item && typeof item === 'object')
    .filter((item) => {
      const methods = item.supportedGenerationMethods
      return Array.isArray(methods) && methods.includes('generateContent')
    })
    .map((item) => {
      const name = String(item.name ?? '').replace(/^models\//, '')
      return name ? { model: name, label: labelFrom(item, name) } : null
    })
    .filter((item): item is ProviderModel => !!item)
}

async function fetchOpenRouterModels(
  fetchImpl: FetchLike,
  key: string,
  timeoutMs: number
): Promise<ProviderModel[]> {
  const response = await fetchWithTimeout(
    fetchImpl,
    'https://openrouter.ai/api/v1/models?output_modalities=text&sort=most-popular',
    { headers: { authorization: `Bearer ${key}` } },
    timeoutMs
  )
  if (!response.ok) throw new Error(`OpenRouter models failed with HTTP ${response.status}`)
  const items = parseDataArray(await response.json())
  return items
    .map((item) => {
      const model = String(item.id ?? '')
      return model ? { model, label: labelFrom(item, model) } : null
    })
    .filter((item): item is ProviderModel => !!item)
    .slice(0, 200)
}

async function fetchProviderModels(
  provider: ByokChatProvider,
  fetchImpl: FetchLike,
  key: string,
  timeoutMs: number
): Promise<ProviderModel[]> {
  switch (provider) {
    case 'openai':
      return fetchOpenAiModels(fetchImpl, key, timeoutMs)
    case 'anthropic':
      return fetchAnthropicModels(fetchImpl, key, timeoutMs)
    case 'gemini':
      return fetchGeminiModels(fetchImpl, key, timeoutMs)
    case 'openrouter':
      return fetchOpenRouterModels(fetchImpl, key, timeoutMs)
  }
}

function dedupe(models: ProviderModel[]): ProviderModel[] {
  const seen = new Set<string>()
  const result: ProviderModel[] = []
  for (const model of models) {
    if (!model.model || seen.has(model.model)) continue
    seen.add(model.model)
    result.push(model)
  }
  return result
}

export async function listAvailableByokModels(
  options: ByokModelsOptions = {}
): Promise<ModelListResult> {
  const fetchImpl = options.fetchImpl ?? fetch
  const timeoutMs = options.timeoutMs ?? MODEL_FETCH_TIMEOUT_MS
  const models: AvailableModel[] = [HOSTED_MODEL]

  const fetchedModels = await Promise.all(
    BYOK_CHAT_PROVIDERS.map(async (provider) => {
      const key = loadByokKey(provider)
      if (!key) return [] as AvailableModel[]
      let providerModels = STATIC_MODELS[provider]
      try {
        const fetched = await fetchProviderModels(provider, fetchImpl, key, timeoutMs)
        if (fetched.length > 0) providerModels = fetched
      } catch {
        providerModels = STATIC_MODELS[provider]
      }
      return dedupe(providerModels).map((model) => available(provider, model))
    })
  )
  models.push(...fetchedModels.flat())

  return {
    models,
    fetchedAt: (options.now ?? Date.now)()
  }
}
