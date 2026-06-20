import type {
  ByokChatProvider,
  ByokChatResponse,
  ChatMessage,
  PiChatUsage
} from '../../shared/types'

type FetchLike = typeof fetch
type JsonRecord = Record<string, unknown>

export type ByokChatOptions = {
  fetchImpl?: FetchLike
}

const BYOK_SYSTEM_PROMPT = [
  'You are Omi on Windows.',
  'Answer conversationally and be concise.',
  'Use any supplied local context only when it helps answer the user.'
].join('\n')

const DEFAULT_MODELS: Record<ByokChatProvider, string> = {
  openai: 'gpt-4o-mini',
  anthropic: 'claude-3-5-sonnet-latest',
  gemini: 'gemini-1.5-flash'
}

function modelFor(provider: ByokChatProvider): string {
  switch (provider) {
    case 'openai':
      return process.env.OMI_BYOK_OPENAI_MODEL || DEFAULT_MODELS.openai
    case 'anthropic':
      return process.env.OMI_BYOK_ANTHROPIC_MODEL || DEFAULT_MODELS.anthropic
    case 'gemini':
      return process.env.OMI_BYOK_GEMINI_MODEL || DEFAULT_MODELS.gemini
  }
}

function chatMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .map((message) => ({ role: message.role, content: message.content }))
}

function emptyUsage(): PiChatUsage {
  return { promptTokens: 0, completionTokens: 0, totalTokens: 0 }
}

function usageFromOpenAi(raw: JsonRecord | undefined): PiChatUsage {
  return {
    promptTokens: Number(raw?.prompt_tokens ?? 0),
    completionTokens: Number(raw?.completion_tokens ?? 0),
    totalTokens: Number(raw?.total_tokens ?? 0)
  }
}

function usageFromAnthropic(raw: JsonRecord | undefined): PiChatUsage {
  const promptTokens = Number(raw?.input_tokens ?? 0)
  const completionTokens = Number(raw?.output_tokens ?? 0)
  return {
    promptTokens,
    completionTokens,
    totalTokens: promptTokens + completionTokens
  }
}

function usageFromGemini(raw: JsonRecord | undefined): PiChatUsage {
  return {
    promptTokens: Number(raw?.promptTokenCount ?? 0),
    completionTokens: Number(raw?.candidatesTokenCount ?? 0),
    totalTokens: Number(raw?.totalTokenCount ?? 0)
  }
}

function textFromContentParts(parts: unknown): string {
  if (!Array.isArray(parts)) return ''
  return parts
    .map((part) => {
      if (!part || typeof part !== 'object') return ''
      const text = (part as { text?: unknown }).text
      return typeof text === 'string' ? text : ''
    })
    .join('')
}

export function buildByokChatRequest(
  provider: ByokChatProvider,
  key: string,
  messages: ChatMessage[]
): { url: string; init: RequestInit } {
  const model = modelFor(provider)
  const thread = chatMessages(messages)

  switch (provider) {
    case 'openai':
      return {
        url: 'https://api.openai.com/v1/chat/completions',
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${key}`
          },
          body: JSON.stringify({
            model,
            stream: false,
            messages: [{ role: 'system', content: BYOK_SYSTEM_PROMPT }, ...thread]
          })
        }
      }
    case 'anthropic':
      return {
        url: 'https://api.anthropic.com/v1/messages',
        init: {
          method: 'POST',
          headers: {
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
            'x-api-key': key
          },
          body: JSON.stringify({
            model,
            max_tokens: 1024,
            system: BYOK_SYSTEM_PROMPT,
            messages: thread
          })
        }
      }
    case 'gemini':
      return {
        url: `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`,
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'x-goog-api-key': key
          },
          body: JSON.stringify({
            system_instruction: {
              parts: [{ text: BYOK_SYSTEM_PROMPT }]
            },
            contents: thread.map((message) => ({
              role: message.role === 'assistant' ? 'model' : 'user',
              parts: [{ text: message.content }]
            }))
          })
        }
      }
  }
}

function responseText(provider: ByokChatProvider, raw: JsonRecord): string {
  switch (provider) {
    case 'openai': {
      const choices = raw.choices
      if (!Array.isArray(choices)) return ''
      const message = (choices[0] as { message?: { content?: unknown } } | undefined)?.message
      return typeof message?.content === 'string' ? message.content : ''
    }
    case 'anthropic':
      return textFromContentParts(raw.content)
    case 'gemini': {
      const candidates = raw.candidates
      if (!Array.isArray(candidates)) return ''
      const content = (candidates[0] as { content?: { parts?: unknown } } | undefined)?.content
      return textFromContentParts(content?.parts)
    }
  }
}

function responseUsage(provider: ByokChatProvider, raw: JsonRecord): PiChatUsage {
  switch (provider) {
    case 'openai':
      return usageFromOpenAi(raw.usage as JsonRecord | undefined)
    case 'anthropic':
      return usageFromAnthropic(raw.usage as JsonRecord | undefined)
    case 'gemini':
      return usageFromGemini(raw.usageMetadata as JsonRecord | undefined)
  }
}

export async function sendByokChat(
  provider: ByokChatProvider,
  key: string,
  messages: ChatMessage[],
  options: ByokChatOptions = {}
): Promise<ByokChatResponse> {
  const trimmed = key.trim()
  if (!trimmed) throw new Error('BYOK chat key is missing')
  if (chatMessages(messages).length === 0) throw new Error('BYOK chat requires messages')

  const fetchImpl = options.fetchImpl ?? fetch
  const request = buildByokChatRequest(provider, trimmed, messages)
  const response = await fetchImpl(request.url, request.init)
  if (!response.ok) {
    throw new Error(`BYOK chat request failed with HTTP ${response.status}`)
  }

  const raw = (await response.json()) as JsonRecord
  return {
    provider,
    text: responseText(provider, raw),
    usage: responseUsage(provider, raw) || emptyUsage()
  }
}
