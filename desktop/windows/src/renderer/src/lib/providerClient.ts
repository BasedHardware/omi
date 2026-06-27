// Direct provider client (BYOK). Talks to the user-selected local/cloud provider
// from shared/providers.ts. Most providers are OpenAI-compatible; Anthropic uses
// its native Messages API, handled as a special case.
import axios from 'axios'
import type { ResolvedTarget } from './modelConfig'

export type ChatMessage = { role: 'system' | 'user' | 'assistant'; content: string }

const TIMEOUT_MS = 60000

function joinUrl(base: string, path: string): string {
  return `${base.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

async function chatOpenAICompatible(
  target: ResolvedTarget,
  messages: ChatMessage[]
): Promise<string> {
  const url = joinUrl(target.baseUrl, 'chat/completions')
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (target.apiKey) headers.Authorization = `Bearer ${target.apiKey}`
  // OpenRouter recommends attribution headers; harmless elsewhere.
  if (target.provider.id === 'openrouter') {
    headers['HTTP-Referer'] = 'https://cortex.apym.io'
    headers['X-Title'] = 'Cortex'
  }
  const res = await axios.post(
    url,
    { model: target.model?.id ?? '', messages, stream: false },
    { headers, timeout: TIMEOUT_MS }
  )
  const data = res.data as { choices?: { message?: { content?: string } }[] }
  return data?.choices?.[0]?.message?.content ?? ''
}

async function chatAnthropic(target: ResolvedTarget, messages: ChatMessage[]): Promise<string> {
  const url = joinUrl(target.baseUrl, 'messages')
  const system = messages.find((m) => m.role === 'system')?.content
  const turns = messages
    .filter((m) => m.role !== 'system')
    .map((m) => ({ role: m.role, content: m.content }))
  const res = await axios.post(
    url,
    { model: target.model?.id ?? '', max_tokens: 4096, system, messages: turns },
    {
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': target.apiKey,
        'anthropic-version': '2023-06-01',
        // Required to call Anthropic directly from a browser/renderer context.
        'anthropic-dangerous-direct-browser-access': 'true'
      },
      timeout: TIMEOUT_MS
    }
  )
  const data = res.data as { content?: { text?: string }[] }
  return (data?.content ?? []).map((c) => c.text ?? '').join('')
}

/** Single-shot completion against the resolved provider target. */
export async function providerChat(
  target: ResolvedTarget,
  messages: ChatMessage[]
): Promise<string> {
  if (target.provider.openAICompatible) return chatOpenAICompatible(target, messages)
  if (target.provider.id === 'anthropic') return chatAnthropic(target, messages)
  // Fallback: assume OpenAI shape.
  return chatOpenAICompatible(target, messages)
}

/** Probe a local provider's /models endpoint to list what the user has available. */
export async function listLocalModels(baseUrl: string): Promise<string[]> {
  try {
    const res = await axios.get(joinUrl(baseUrl, 'models'), { timeout: 4000 })
    const data = res.data as { data?: { id?: string }[] }
    return (data?.data ?? []).map((m) => m.id ?? '').filter(Boolean)
  } catch {
    return []
  }
}
