import type { ByokChatProvider, ByokStatus, ChatMessage, ModelPurpose } from '../../../shared/types'
import { getPreferences } from './preferences'

type PurposeCompletionArgs = {
  messages: ChatMessage[]
  systemPrompt?: string
  timeoutMs?: number
}

const PROVIDER_LABELS: Record<ByokChatProvider, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  openrouter: 'OpenRouter'
}

export class ByokCompletionError extends Error {
  constructor(
    readonly provider: ByokChatProvider,
    readonly purpose: ModelPurpose,
    message: string
  ) {
    super(message)
    this.name = 'ByokCompletionError'
  }
}

export function byokProviderFromModelId(modelId: string | undefined): ByokChatProvider | null {
  const provider = modelId?.split(':', 1)[0]
  return provider === 'openai' ||
    provider === 'anthropic' ||
    provider === 'gemini' ||
    provider === 'openrouter'
    ? provider
    : null
}

export function selectedModelForPurpose(purpose: ModelPurpose): string | undefined {
  const modelId = getPreferences().defaultModelByPurpose?.[purpose]
  return typeof modelId === 'string' && modelId.trim() ? modelId.trim() : undefined
}

export function hostedModelForPurpose(purpose: ModelPurpose, fallback: string): string {
  const modelId = selectedModelForPurpose(purpose)
  return modelId?.startsWith('omi:') ? modelId.slice('omi:'.length) || fallback : fallback
}

export function byokProviderLabel(provider: ByokChatProvider): string {
  return PROVIDER_LABELS[provider]
}

export function resolveByokChatSelection(
  chatModelId: string | undefined,
  status: ByokStatus | null | undefined
): { useByok: boolean; modelId?: string } {
  const selectedProvider = byokProviderFromModelId(chatModelId)
  const activeProvider = status?.activeChatProvider ?? null
  const selectedProviderConfigured = selectedProvider
    ? status?.providers[selectedProvider]?.configured === true
    : false
  const activeProviderConfigured = activeProvider
    ? status?.providers[activeProvider]?.configured === true
    : false
  const explicitModelSelected = typeof chatModelId === 'string' && chatModelId.trim().length > 0

  if (selectedProvider) {
    return selectedProviderConfigured ? { useByok: true, modelId: chatModelId } : { useByok: false }
  }
  if (explicitModelSelected) return { useByok: false }
  return activeProviderConfigured ? { useByok: true } : { useByok: false }
}

export async function tryByokCompletion(
  purpose: ModelPurpose,
  args: PurposeCompletionArgs
): Promise<string | null> {
  const modelId = selectedModelForPurpose(purpose)
  const provider = byokProviderFromModelId(modelId)
  if (!provider || !modelId) return null

  try {
    const status = await window.omi.byokStatus()
    if (!resolveByokChatSelection(modelId, status).useByok) {
      throw new ByokCompletionError(
        provider,
        purpose,
        `${byokProviderLabel(provider)} BYOK is selected for ${purpose}, but that provider is not configured.`
      )
    }

    const result = await window.omi.byokChatSend({
      messages: args.messages,
      modelId,
      systemPrompt: args.systemPrompt,
      timeoutMs: args.timeoutMs
    })
    return result.text
  } catch (error) {
    if (error instanceof ByokCompletionError) throw error
    throw new ByokCompletionError(
      provider,
      purpose,
      `${byokProviderLabel(provider)} BYOK request failed for ${purpose}: ${
        error instanceof Error ? error.message : String(error)
      }`
    )
  }
}
