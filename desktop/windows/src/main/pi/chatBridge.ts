import type { LocalAgentRuntimeContext, LocalAgentToolDefinition } from '../localAgent/tools'
import { errorResponseBody, listLocalAgentTools, runLocalAgentTool } from '../localAgent/tools'
import type { ChatMessage, PiChatResponse, PiChatToolCall, PiChatUsage } from '../../shared/types'

const DEFAULT_DESKTOP_API_BASE = 'https://desktop-backend-hhibjajaja-uc.a.run.app'
const PI_CHAT_MODEL = 'omi-sonnet'
const MAX_TOOL_ROUNDS = 6

const PI_CHAT_SYSTEM_PROMPT = [
  'You are Omi on Windows.',
  'Answer conversationally and use the provided local Windows tools when they help.',
  'Local tools can inspect local Omi status, screen history, screenshots, read-only SQL, daily recaps, and best-effort local task tables.',
  'Do not claim that unavailable or rejected tool actions succeeded.'
].join('\n')

const PI_CHAT_TOOL_NAMES = new Set([
  'get_local_status',
  'execute_sql',
  'search_screen_history',
  'semantic_search',
  'get_screenshot',
  'get_daily_recap',
  'search_tasks'
])

type JsonRecord = Record<string, unknown>

type OpenAiChatMessage = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content?: string | null
  tool_calls?: OpenAiToolCall[]
  tool_call_id?: string
}

type OpenAiTool = {
  type: 'function'
  function: {
    name: string
    description?: string
    parameters?: JsonRecord
  }
}

type OpenAiToolCall = {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string
  }
}

type OpenAiUsage = {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
}

type OpenAiChatCompletion = {
  choices?: {
    message?: {
      role?: string
      content?: string | null
      tool_calls?: OpenAiToolCall[]
    }
    finish_reason?: string | null
  }[]
  usage?: OpenAiUsage
}

type FetchLike = typeof fetch

export type PiChatBridgeOptions = {
  fetchImpl?: FetchLike
  desktopApiBaseUrl?: string
  toolDefinitions?: () => LocalAgentToolDefinition[]
  runTool?: typeof runLocalAgentTool
  runtimeContext?: LocalAgentRuntimeContext
}

export type PiChatSendRequest = {
  token: string
  messages: ChatMessage[]
}

export function isPiChatEnabled(): boolean {
  return process.env.OMI_WINDOWS_PI_CHAT === '1' || process.env.OMI_PI_CHAT === '1'
}

function desktopApiBaseUrl(): string {
  return (
    process.env.OMI_DESKTOP_API_URL ||
    process.env.VITE_OMI_DESKTOP_API_BASE ||
    DEFAULT_DESKTOP_API_BASE
  )
}

export function chatCompletionsUrl(baseUrl = desktopApiBaseUrl()): string {
  return `${baseUrl.replace(/\/+$/, '')}/v2/chat/completions`
}

function usageFrom(raw?: OpenAiUsage): PiChatUsage {
  return {
    promptTokens: raw?.prompt_tokens ?? 0,
    completionTokens: raw?.completion_tokens ?? 0,
    totalTokens: raw?.total_tokens ?? 0
  }
}

function addUsage(a: PiChatUsage, b: PiChatUsage): PiChatUsage {
  return {
    promptTokens: a.promptTokens + b.promptTokens,
    completionTokens: a.completionTokens + b.completionTokens,
    totalTokens: a.totalTokens + b.totalTokens
  }
}

function messagesForPi(messages: ChatMessage[]): OpenAiChatMessage[] {
  return [
    { role: 'system', content: PI_CHAT_SYSTEM_PROMPT },
    ...messages
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => ({
        role: message.role,
        content: message.content
      }))
  ]
}

function toolsForPi(definitions: LocalAgentToolDefinition[]): OpenAiTool[] {
  return definitions
    .filter((tool) => PI_CHAT_TOOL_NAMES.has(tool.name))
    .map((tool) => ({
      type: 'function',
      function: {
        name: tool.name,
        description: tool.description,
        parameters: tool.inputSchema
      }
    }))
}

export function buildPiChatRequest(messages: ChatMessage[]): JsonRecord {
  return {
    model: PI_CHAT_MODEL,
    stream: false,
    messages: messagesForPi(messages),
    tools: toolsForPi(listLocalAgentTools()),
    tool_choice: 'auto'
  }
}

function parseToolArguments(call: OpenAiToolCall): JsonRecord {
  const raw = call.function.arguments.trim()
  if (!raw) return {}
  const parsed = JSON.parse(raw) as unknown
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('tool arguments must be a JSON object')
  }
  return parsed as JsonRecord
}

function resultToToolContent(value: unknown): string {
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function toolErrorContent(error: unknown): string {
  const { body } = errorResponseBody(error)
  return `Error: ${body.error.code}: ${body.error.message}`
}

function defaultRuntimeContext(): LocalAgentRuntimeContext {
  return {
    localUrl: 'omi://local-agent',
    toolEndpoint: 'omi://local-agent/pi-chat-tool',
    app: {
      name: 'Omi Windows',
      version: '1.0.0',
      appId: 'com.omiwindows.app'
    }
  }
}

async function callChatCompletions(
  request: JsonRecord,
  token: string,
  options: PiChatBridgeOptions
): Promise<OpenAiChatCompletion> {
  const fetchImpl = options.fetchImpl ?? fetch
  const response = await fetchImpl(chatCompletionsUrl(options.desktopApiBaseUrl), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${token}`
    },
    body: JSON.stringify(request)
  })
  if (!response.ok) {
    throw new Error(`Pi/Omi chat request failed with HTTP ${response.status}`)
  }
  return (await response.json()) as OpenAiChatCompletion
}

async function executeToolCall(
  call: OpenAiToolCall,
  options: PiChatBridgeOptions
): Promise<OpenAiChatMessage> {
  const runTool = options.runTool ?? runLocalAgentTool
  const context = options.runtimeContext ?? defaultRuntimeContext()

  let content = ''
  try {
    if (!PI_CHAT_TOOL_NAMES.has(call.function.name)) {
      throw new Error(`Local tool is not available to Pi/Omi chat: ${call.function.name}`)
    }
    const args = parseToolArguments(call)
    const result = await runTool(call.function.name, args, context)
    content = resultToToolContent(result)
  } catch (error) {
    content = toolErrorContent(error)
  }

  return {
    role: 'tool',
    tool_call_id: call.id,
    content
  }
}

export async function sendPiChat(
  request: PiChatSendRequest,
  options: PiChatBridgeOptions = {}
): Promise<PiChatResponse> {
  const token = request.token.trim()
  if (!token) {
    throw new Error('Pi/Omi chat requires a Firebase ID token')
  }

  const toolDefinitions = options.toolDefinitions ?? listLocalAgentTools
  const conversation: OpenAiChatMessage[] = messagesForPi(request.messages)
  const tools = toolsForPi(toolDefinitions())
  const toolCalls: PiChatToolCall[] = []
  let usage: PiChatUsage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 }
  let finalText = ''

  for (let round = 0; round < MAX_TOOL_ROUNDS; round += 1) {
    const body: JsonRecord = {
      model: PI_CHAT_MODEL,
      stream: false,
      messages: conversation,
      tools,
      tool_choice: 'auto'
    }
    const completion = await callChatCompletions(body, token, options)
    usage = addUsage(usage, usageFrom(completion.usage))
    const message = completion.choices?.[0]?.message
    if (!message) throw new Error('Pi/Omi chat returned no message')

    const assistantText = typeof message.content === 'string' ? message.content : ''
    const calls = message.tool_calls ?? []
    if (calls.length === 0) {
      finalText = assistantText
      break
    }

    conversation.push({
      role: 'assistant',
      content: assistantText || null,
      tool_calls: calls
    })

    for (const call of calls) {
      toolCalls.push({ id: call.id, name: call.function.name })
      conversation.push(await executeToolCall(call, options))
    }
  }

  if (!finalText && toolCalls.length > 0) {
    throw new Error('Pi/Omi chat exceeded the local tool-call round limit')
  }

  return {
    text: finalText,
    usage,
    toolCalls
  }
}
