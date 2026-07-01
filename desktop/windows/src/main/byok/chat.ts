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
  systemPrompt?: string
  timeoutMs?: number
}

const DEFAULT_CHAT_TIMEOUT_MS = 30_000

const BYOK_SYSTEM_PROMPT = [
  'You are Omi on Windows.',
  'Answer conversationally and be concise.',
  'Use any supplied local context only when it helps answer the user.'
].join('\n')

const DEFAULT_MODELS: Record<ByokChatProvider, string> = {
  openai: 'gpt-4o-mini',
  anthropic: 'claude-3-5-sonnet-latest',
  gemini: 'gemini-1.5-flash',
  openrouter: 'openrouter/auto'
}

function normalizeModelOverride(provider: ByokChatProvider, modelId?: string): string | null {
  if (!modelId) return null
  const prefix = `${provider}:`
  if (modelId.startsWith(prefix)) return modelId.slice(prefix.length)
  if (!modelId.includes(':')) return modelId
  console.warn(
    `[byok] ignoring ${provider} model override with mismatched provider prefix: ${modelId}`
  )
  return null
}

function modelFor(provider: ByokChatProvider, modelId?: string): string {
  const override = normalizeModelOverride(provider, modelId)
  if (override) return override

  switch (provider) {
    case 'openai':
      return process.env.OMI_BYOK_OPENAI_MODEL || DEFAULT_MODELS.openai
    case 'anthropic':
      return process.env.OMI_BYOK_ANTHROPIC_MODEL || DEFAULT_MODELS.anthropic
    case 'gemini':
      return process.env.OMI_BYOK_GEMINI_MODEL || DEFAULT_MODELS.gemini
    case 'openrouter':
      return process.env.OMI_BYOK_OPENROUTER_MODEL || DEFAULT_MODELS.openrouter
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

function textFromOpenAiCompatible(raw: JsonRecord): string {
  const choices = raw.choices
  if (!Array.isArray(choices)) return ''
  const message = (choices[0] as { message?: { content?: unknown } } | undefined)?.message
  return typeof message?.content === 'string' ? message.content : ''
}

function responseFromOpenAiCompatible(raw: JsonRecord): Pick<ByokChatResponse, 'text' | 'usage'> {
  return {
    text: textFromOpenAiCompatible(raw),
    usage: usageFromOpenAi(raw.usage as JsonRecord | undefined)
  }
}

export function buildByokChatRequest(
  provider: ByokChatProvider,
  key: string,
  messages: ChatMessage[],
  modelId?: string,
  systemPrompt = BYOK_SYSTEM_PROMPT
): { url: string; init: RequestInit } {
  const model = modelFor(provider, modelId)
  const thread = chatMessages(messages)
  const prompt = systemPrompt.trim()
  const openAiMessages = prompt ? [{ role: 'system', content: prompt }, ...thread] : thread

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
            messages: openAiMessages
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
            ...(prompt ? { system: prompt } : {}),
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
            ...(prompt
              ? {
                  system_instruction: {
                    parts: [{ text: prompt }]
                  }
                }
              : {}),
            contents: thread.map((message) => ({
              role: message.role === 'assistant' ? 'model' : 'user',
              parts: [{ text: message.content }]
            }))
          })
        }
      }
    case 'openrouter':
      return {
        url: 'https://openrouter.ai/api/v1/chat/completions',
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${key}`,
            'HTTP-Referer': 'https://omi.me',
            'X-Title': 'Omi Windows'
          },
          body: JSON.stringify({
            model,
            stream: false,
            messages: openAiMessages
          })
        }
      }
  }
}

function parseByokResponse(
  provider: ByokChatProvider,
  raw: JsonRecord
): Pick<ByokChatResponse, 'text' | 'usage'> {
  switch (provider) {
    case 'openai':
    case 'openrouter':
      return responseFromOpenAiCompatible(raw)
    case 'anthropic':
      return {
        text: textFromContentParts(raw.content),
        usage: usageFromAnthropic(raw.usage as JsonRecord | undefined)
      }
    case 'gemini': {
      const candidates = raw.candidates
      if (!Array.isArray(candidates)) {
        return { text: '', usage: usageFromGemini(raw.usageMetadata as JsonRecord | undefined) }
      }
      const content = (candidates[0] as { content?: { parts?: unknown } } | undefined)?.content
      return {
        text: textFromContentParts(content?.parts),
        usage: usageFromGemini(raw.usageMetadata as JsonRecord | undefined)
      }
    }
  }
}

export async function sendByokChat(
  provider: ByokChatProvider,
  key: string,
  messages: ChatMessage[],
  modelId?: string,
  options: ByokChatOptions = {}
): Promise<ByokChatResponse> {
  const trimmed = key.trim()
  if (!trimmed) throw new Error('BYOK chat key is missing')
  if (chatMessages(messages).length === 0) throw new Error('BYOK chat requires messages')

  const fetchImpl = options.fetchImpl ?? fetch
  const request = buildByokChatRequest(provider, trimmed, messages, modelId, options.systemPrompt)
  const controller = new AbortController()
  const timeout = setTimeout(
    () => controller.abort(),
    Math.max(1, options.timeoutMs ?? DEFAULT_CHAT_TIMEOUT_MS)
  )
  let response: Response
  let raw: JsonRecord
  try {
    response = await fetchImpl(request.url, { ...request.init, signal: controller.signal })
    if (!response.ok) {
      throw new Error(`BYOK chat request failed with HTTP ${response.status}`)
    }
    raw = (await response.json()) as JsonRecord
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      throw new Error('BYOK chat request timed out')
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }

  const parsed = parseByokResponse(provider, raw)
  return {
    provider,
    text: parsed.text,
    usage: parsed.usage || emptyUsage()
  }
}
