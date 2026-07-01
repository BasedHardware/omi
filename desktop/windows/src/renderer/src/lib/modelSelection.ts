import type { ByokChatProvider, ChatMessage, ModelPurpose } from '../../../shared/types'
import { getPreferences } from './preferences'

type PurposeCompletionArgs = {
  messages: ChatMessage[]
  systemPrompt?: string
  timeoutMs?: number
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

export async function tryByokCompletion(
  purpose: ModelPurpose,
  args: PurposeCompletionArgs
): Promise<string | null> {
  const modelId = selectedModelForPurpose(purpose)
  const provider = byokProviderFromModelId(modelId)
  if (!provider || !modelId) return null

  const status = await window.omi.byokStatus().catch(() => null)
  if (!status?.providers[provider]?.configured) return null

  try {
    const result = await window.omi.byokChatSend({
      messages: args.messages,
      modelId,
      systemPrompt: args.systemPrompt,
      timeoutMs: args.timeoutMs
    })
    return result.text
  } catch {
    return null
  }
}
