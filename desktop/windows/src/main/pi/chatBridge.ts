import {
  Agent,
  type AgentEvent,
  type AgentMessage,
  type AgentTool,
  type AgentToolResult
} from '@earendil-works/pi-agent-core/base'
import {
  createAssistantMessageEventStream,
  Type,
  type AssistantMessage,
  type AssistantMessageEventStream,
  type Context,
  type Message,
  type Model,
  type TextContent,
  type ToolCall,
  type ToolResultMessage,
  type Usage
} from '@earendil-works/pi-ai/base'
import type { TSchema } from '@earendil-works/pi-ai/base'
import { byokChatModelFor } from '../byok/chat'
import type { LocalAgentRuntimeContext, LocalAgentToolDefinition } from '../localAgent/tools'
import { listLocalAgentTools, runLocalAgentTool } from '../localAgent/tools'
import type {
  ByokChatProvider,
  ChatMessage,
  PiChatResponse,
  PiChatToolCall,
  PiChatUsage
} from '../../shared/types'
import { loadSkillPromptSections } from '../skills/loader'
import { addObservabilityBreadcrumb, captureMainException } from '../observability'

const DEFAULT_DESKTOP_API_BASE = 'https://desktop-backend-hhibjajaja-uc.a.run.app'
const PI_MODEL_ID = 'omi-sonnet'
const PI_MODEL_NAME = 'Omi Sonnet'
const OMI_PI_API = 'omi-chat-completions'
const OMI_PI_PROVIDER = 'omi'
const BYOK_PI_API = 'byok-chat-completions'
const MAX_TOOL_RESULT_CHARS = 24_000

const EMPTY_USAGE: Usage = {
  input: 0,
  output: 0,
  cacheRead: 0,
  cacheWrite: 0,
  totalTokens: 0,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
}

const BASE_SYSTEM_PROMPT = [
  'You are Omi on Windows.',
  'You are running through Pi native agent core inside the Electron main process.',
  'Answer conversationally and use the provided local Windows tools when they help.',
  'Local tools can inspect local Omi status, screen history, screenshots, read-only SQL, daily recaps, and best-effort local task tables.',
  'Do not claim that unavailable or rejected tool actions succeeded.'
].join('\n')

const NATIVE_PI_TOOL_NAMES = new Set([
  'get_local_status',
  'execute_sql',
  'search_screen_history',
  'semantic_search',
  'get_screenshot',
  'get_daily_recap',
  'search_tasks'
])

type JsonRecord = Record<string, unknown>
type FetchLike = typeof fetch
type ActiveByokChatKey = { provider: ByokChatProvider; key: string } | null
type LoadActiveByokChatKey = () => ActiveByokChatKey | Promise<ActiveByokChatKey>

type PiModelRoute =
  | {
      kind: 'omi'
      api: typeof OMI_PI_API
      provider: typeof OMI_PI_PROVIDER
      model: typeof PI_MODEL_ID
      name: typeof PI_MODEL_NAME
      baseUrl: string
    }
  | {
      kind: 'byok'
      api: typeof BYOK_PI_API
      provider: ByokChatProvider
      key: string
      model: string
      name: string
      baseUrl: string
    }

type OpenAiChatMessage = {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content?: string | null
  tool_calls?: OpenAiToolCall[]
  tool_call_id?: string
  name?: string
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

export type PiChatBridgeOptions = {
  fetchImpl?: FetchLike
  desktopApiBaseUrl?: string
  toolDefinitions?: () => LocalAgentToolDefinition[]
  runTool?: typeof runLocalAgentTool
  runtimeContext?: LocalAgentRuntimeContext
  loadSkillSections?: typeof loadSkillPromptSections
  loadActiveByokChatKey?: LoadActiveByokChatKey
}

export type PiChatSendRequest = {
  token: string
  messages: ChatMessage[]
  skillIds?: string[]
  modelId?: string
}

export function isPiChatEnabled(): boolean {
  return process.env.OMI_WINDOWS_PI_CHAT !== '0' && process.env.OMI_PI_CHAT !== '0'
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

async function defaultLoadActiveByokChatKey(): Promise<ActiveByokChatKey> {
  const store = await import('../byok/store')
  return store.loadActiveByokChatKey()
}

function omiRoute(baseUrl = desktopApiBaseUrl()): PiModelRoute {
  return {
    kind: 'omi',
    api: OMI_PI_API,
    provider: OMI_PI_PROVIDER,
    model: PI_MODEL_ID,
    name: PI_MODEL_NAME,
    baseUrl: chatCompletionsUrl(baseUrl)
  }
}

async function resolvePiModelRoute(
  request: PiChatSendRequest,
  options: PiChatBridgeOptions
): Promise<PiModelRoute> {
  const loadActiveByok = options.loadActiveByokChatKey ?? defaultLoadActiveByokChatKey
  let active: ActiveByokChatKey
  try {
    active = await loadActiveByok()
  } catch (error) {
    addObservabilityBreadcrumb(
      'native_pi.byok_route_unavailable',
      { error: error instanceof Error ? error.message : String(error) },
      { category: 'native_pi' }
    )
    return omiRoute(options.desktopApiBaseUrl)
  }

  if (!active) return omiRoute(options.desktopApiBaseUrl)

  const model = byokChatModelFor(active.provider, request.modelId)
  return {
    kind: 'byok',
    api: BYOK_PI_API,
    provider: active.provider,
    key: active.key,
    model,
    name: `${active.provider}:${model}`,
    baseUrl: byokRouteUrl(active.provider, model)
  }
}

function byokRouteUrl(provider: ByokChatProvider, model: string): string {
  switch (provider) {
    case 'openai':
      return 'https://api.openai.com/v1/chat/completions'
    case 'anthropic':
      return 'https://api.anthropic.com/v1/messages'
    case 'gemini':
      return `https://generativelanguage.googleapis.com/v1beta/models/${encodeURIComponent(model)}:generateContent`
    case 'openrouter':
      return 'https://openrouter.ai/api/v1/chat/completions'
  }
}

function piModelForRoute(route: PiModelRoute): Model<string> {
  return {
    id: route.model,
    name: route.name,
    api: route.api,
    provider: route.provider,
    baseUrl: route.baseUrl,
    reasoning: false,
    input: ['text'],
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
    contextWindow: 200_000,
    maxTokens: 8192
  }
}

function usageFrom(raw?: OpenAiUsage): Usage {
  return {
    input: raw?.prompt_tokens ?? 0,
    output: raw?.completion_tokens ?? 0,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: raw?.total_tokens ?? (raw?.prompt_tokens ?? 0) + (raw?.completion_tokens ?? 0),
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
  }
}

function addResponseUsage(a: PiChatUsage, b: PiChatUsage): PiChatUsage {
  return {
    promptTokens: a.promptTokens + b.promptTokens,
    completionTokens: a.completionTokens + b.completionTokens,
    totalTokens: a.totalTokens + b.totalTokens
  }
}

function textBlocksToString(content: readonly { type: string }[]): string {
  return content
    .map((block) => {
      if (block.type === 'text' && 'text' in block) return String(block.text)
      return ''
    })
    .filter(Boolean)
    .join('\n')
}

function messageText(message: AgentMessage | ToolResultMessage): string {
  if (message.role === 'user') {
    if (typeof message.content === 'string') return message.content
    return textBlocksToString(message.content)
  }
  if (message.role === 'assistant') {
    return textBlocksToString(message.content)
  }
  if (message.role === 'toolResult' && 'content' in message) {
    return textBlocksToString(message.content)
  }
  return ''
}

function toolCallsFromAssistant(message: AgentMessage): OpenAiToolCall[] {
  if (message.role !== 'assistant' || !('content' in message)) return []
  return message.content
    .filter((block): block is ToolCall => block.type === 'toolCall')
    .map((block) => ({
      id: block.id,
      type: 'function',
      function: {
        name: block.name,
        arguments: JSON.stringify(block.arguments ?? {})
      }
    }))
}

function openAiMessagesForContext(context: Context): OpenAiChatMessage[] {
  const messages: OpenAiChatMessage[] = []
  if (context.systemPrompt?.trim()) {
    messages.push({ role: 'system', content: context.systemPrompt.trim() })
  }
  for (const message of context.messages) {
    if (message.role === 'user') {
      messages.push({ role: 'user', content: messageText(message) })
      continue
    }
    if (message.role === 'assistant') {
      const toolCalls = toolCallsFromAssistant(message)
      messages.push({
        role: 'assistant',
        content: messageText(message) || null,
        ...(toolCalls.length > 0 ? { tool_calls: toolCalls } : {})
      })
      continue
    }
    messages.push({
      role: 'tool',
      tool_call_id: message.toolCallId,
      name: message.toolName,
      content: messageText(message)
    })
  }
  return messages
}

function openAiToolsForContext(context: Context): OpenAiTool[] {
  return (context.tools ?? []).map((tool) => ({
    type: 'function',
    function: {
      name: tool.name,
      description: tool.description,
      parameters: tool.parameters as unknown as JsonRecord
    }
  }))
}

export function buildPiChatRequest(messages: ChatMessage[]): JsonRecord {
  const context: Context = {
    systemPrompt: BASE_SYSTEM_PROMPT,
    messages: messages.map(chatMessageToAgentMessage),
    tools: nativePiTools()
  }
  return buildOmiChatCompletionBody(context)
}

function buildOpenAiChatCompletionBody(context: Context, model = PI_MODEL_ID): JsonRecord {
  const tools = openAiToolsForContext(context)
  return {
    model,
    stream: false,
    messages: openAiMessagesForContext(context),
    ...(tools.length > 0 ? { tools, tool_choice: 'auto' } : {})
  }
}

function buildOmiChatCompletionBody(context: Context): JsonRecord {
  return buildOpenAiChatCompletionBody(context, PI_MODEL_ID)
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

function stopReason(
  finishReason?: string | null,
  hasToolCalls = false
): AssistantMessage['stopReason'] {
  if (hasToolCalls || finishReason === 'tool_calls') return 'toolUse'
  if (finishReason === 'length') return 'length'
  return 'stop'
}

function routeError(route: PiModelRoute, status: number): Error {
  return new Error(
    route.kind === 'omi'
      ? `Omi Pi provider request failed with HTTP ${status}`
      : `BYOK ${route.provider} Pi provider request failed with HTTP ${status}`
  )
}

function assistantMetadata(
  route: PiModelRoute
): Pick<AssistantMessage, 'api' | 'provider' | 'model'> {
  return {
    api: route.api,
    provider: route.provider,
    model: route.model
  }
}

function assistantMessageFromOpenAiCompletion(
  route: PiModelRoute,
  completion: OpenAiChatCompletion
): AssistantMessage {
  const choice = completion.choices?.[0]
  const message = choice?.message
  if (!message) throw new Error('Pi provider returned no message')

  const toolCalls = message.tool_calls ?? []
  const content: AssistantMessage['content'] = []
  if (typeof message.content === 'string' && message.content.length > 0) {
    content.push({ type: 'text', text: message.content })
  }
  for (const call of toolCalls) {
    content.push({
      type: 'toolCall',
      id: call.id,
      name: call.function.name,
      arguments: parseToolArguments(call)
    })
  }

  return {
    role: 'assistant',
    content,
    ...assistantMetadata(route),
    usage: usageFrom(completion.usage),
    stopReason: stopReason(choice.finish_reason, toolCalls.length > 0),
    timestamp: Date.now()
  }
}

function anthropicToolsForContext(context: Context): JsonRecord[] {
  return (context.tools ?? []).map((tool) => ({
    name: tool.name,
    description: tool.description,
    input_schema: tool.parameters as unknown as JsonRecord
  }))
}

function anthropicMessagesForContext(context: Context): JsonRecord[] {
  return context.messages.map((message) => {
    if (message.role === 'user') {
      return { role: 'user', content: messageText(message) }
    }
    if (message.role === 'assistant') {
      const content: JsonRecord[] = []
      const text = messageText(message)
      if (text) content.push({ type: 'text', text })
      for (const call of toolCallsFromAssistant(message)) {
        content.push({
          type: 'tool_use',
          id: call.id,
          name: call.function.name,
          input: parseToolArguments(call)
        })
      }
      return {
        role: 'assistant',
        content: content.length > 0 ? content : [{ type: 'text', text: '' }]
      }
    }
    return {
      role: 'user',
      content: [
        {
          type: 'tool_result',
          tool_use_id: message.toolCallId,
          content: messageText(message)
        }
      ]
    }
  })
}

function buildAnthropicBody(context: Context, model: string): JsonRecord {
  const tools = anthropicToolsForContext(context)
  return {
    model,
    max_tokens: 1024,
    system: context.systemPrompt,
    messages: anthropicMessagesForContext(context),
    ...(tools.length > 0 ? { tools, tool_choice: { type: 'auto' } } : {})
  }
}

function usageFromAnthropic(raw: JsonRecord | undefined): Usage {
  const input = Number(raw?.input_tokens ?? 0)
  const output = Number(raw?.output_tokens ?? 0)
  return {
    input,
    output,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: input + output,
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
  }
}

function assistantMessageFromAnthropic(route: PiModelRoute, raw: JsonRecord): AssistantMessage {
  const rawContent = Array.isArray(raw.content) ? raw.content : []
  const content: AssistantMessage['content'] = []
  for (const block of rawContent) {
    if (!block || typeof block !== 'object') continue
    const record = block as JsonRecord
    if (record.type === 'text' && typeof record.text === 'string') {
      content.push({ type: 'text', text: record.text })
      continue
    }
    if (
      record.type === 'tool_use' &&
      typeof record.id === 'string' &&
      typeof record.name === 'string'
    ) {
      const input = record.input
      content.push({
        type: 'toolCall',
        id: record.id,
        name: record.name,
        arguments: input && typeof input === 'object' && !Array.isArray(input) ? input : {}
      })
    }
  }
  const hasToolCalls = content.some((block) => block.type === 'toolCall')
  return {
    role: 'assistant',
    content,
    ...assistantMetadata(route),
    usage: usageFromAnthropic(raw.usage as JsonRecord | undefined),
    stopReason: hasToolCalls || raw.stop_reason === 'tool_use' ? 'toolUse' : 'stop',
    timestamp: Date.now()
  }
}

function geminiToolsForContext(context: Context): JsonRecord[] {
  const declarations = (context.tools ?? []).map((tool) => ({
    name: tool.name,
    description: tool.description,
    parameters: tool.parameters as unknown as JsonRecord
  }))
  return declarations.length > 0 ? [{ function_declarations: declarations }] : []
}

function geminiPartsForAssistant(message: AgentMessage): JsonRecord[] {
  const parts: JsonRecord[] = []
  const text = messageText(message)
  if (text) parts.push({ text })
  for (const call of toolCallsFromAssistant(message)) {
    parts.push({
      functionCall: {
        name: call.function.name,
        args: parseToolArguments(call)
      }
    })
  }
  return parts.length > 0 ? parts : [{ text: '' }]
}

function geminiContentsForContext(context: Context): JsonRecord[] {
  return context.messages.map((message) => {
    if (message.role === 'user') {
      return { role: 'user', parts: [{ text: messageText(message) }] }
    }
    if (message.role === 'assistant') {
      return { role: 'model', parts: geminiPartsForAssistant(message) }
    }
    return {
      role: 'user',
      parts: [
        {
          functionResponse: {
            name: message.toolName,
            response: { content: messageText(message) }
          }
        }
      ]
    }
  })
}

function buildGeminiBody(context: Context): JsonRecord {
  const tools = geminiToolsForContext(context)
  return {
    system_instruction: { parts: [{ text: context.systemPrompt }] },
    contents: geminiContentsForContext(context),
    ...(tools.length > 0
      ? {
          tools,
          tool_config: { function_calling_config: { mode: 'AUTO' } }
        }
      : {})
  }
}

function usageFromGemini(raw: JsonRecord | undefined): Usage {
  const input = Number(raw?.promptTokenCount ?? 0)
  const output = Number(raw?.candidatesTokenCount ?? 0)
  return {
    input,
    output,
    cacheRead: 0,
    cacheWrite: 0,
    totalTokens: Number(raw?.totalTokenCount ?? input + output),
    cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 }
  }
}

function assistantMessageFromGemini(route: PiModelRoute, raw: JsonRecord): AssistantMessage {
  const candidates = Array.isArray(raw.candidates) ? raw.candidates : []
  const candidate = candidates[0] as JsonRecord | undefined
  const contentRecord = candidate?.content as JsonRecord | undefined
  const parts = Array.isArray(contentRecord?.parts) ? contentRecord.parts : []
  const content: AssistantMessage['content'] = []
  parts.forEach((part, index) => {
    if (!part || typeof part !== 'object') return
    const record = part as JsonRecord
    if (typeof record.text === 'string') {
      content.push({ type: 'text', text: record.text })
      return
    }
    const functionCall = record.functionCall as JsonRecord | undefined
    if (functionCall && typeof functionCall.name === 'string') {
      const args = functionCall.args
      content.push({
        type: 'toolCall',
        id: `gemini-${Date.now()}-${index}`,
        name: functionCall.name,
        arguments: args && typeof args === 'object' && !Array.isArray(args) ? args : {}
      })
    }
  })
  const hasToolCalls = content.some((block) => block.type === 'toolCall')
  return {
    role: 'assistant',
    content,
    ...assistantMetadata(route),
    usage: usageFromGemini(raw.usageMetadata as JsonRecord | undefined),
    stopReason: stopReason(String(candidate?.finishReason ?? ''), hasToolCalls),
    timestamp: Date.now()
  }
}

function cloneAssistant(message: AssistantMessage): AssistantMessage {
  return {
    ...message,
    content: message.content.map((block) => ({ ...block }))
  }
}

function emitAssistantMessage(
  stream: AssistantMessageEventStream,
  message: AssistantMessage
): void {
  const partial: AssistantMessage = { ...message, content: [] }
  stream.push({ type: 'start', partial: cloneAssistant(partial) })
  message.content.forEach((block, index) => {
    if (block.type === 'text') {
      partial.content = [...partial.content, { type: 'text', text: '' }]
      stream.push({ type: 'text_start', contentIndex: index, partial: cloneAssistant(partial) })
      ;(partial.content[index] as TextContent).text = block.text
      stream.push({
        type: 'text_delta',
        contentIndex: index,
        delta: block.text,
        partial: cloneAssistant(partial)
      })
      stream.push({
        type: 'text_end',
        contentIndex: index,
        content: block.text,
        partial: cloneAssistant(partial)
      })
      return
    }
    if (block.type !== 'toolCall') return
    partial.content = [
      ...partial.content,
      { type: 'toolCall', id: block.id, name: block.name, arguments: {} }
    ]
    stream.push({ type: 'toolcall_start', contentIndex: index, partial: cloneAssistant(partial) })
    ;(partial.content[index] as ToolCall).arguments = block.arguments
    stream.push({
      type: 'toolcall_delta',
      contentIndex: index,
      delta: JSON.stringify(block.arguments ?? {}),
      partial: cloneAssistant(partial)
    })
    stream.push({
      type: 'toolcall_end',
      contentIndex: index,
      toolCall: block,
      partial: cloneAssistant(partial)
    })
  })
  stream.push({
    type: 'done',
    reason:
      message.stopReason === 'toolUse' || message.stopReason === 'length'
        ? message.stopReason
        : 'stop',
    message
  })
  stream.end(message)
}

function errorAssistantMessage(error: unknown, route: PiModelRoute = omiRoute()): AssistantMessage {
  return {
    role: 'assistant',
    content: [],
    ...assistantMetadata(route),
    usage: EMPTY_USAGE,
    stopReason: 'error',
    errorMessage: error instanceof Error ? error.message : String(error),
    timestamp: Date.now()
  }
}

function buildPiProviderRequest(
  route: PiModelRoute,
  context: Context,
  token: string
): { url: string; init: RequestInit } {
  if (route.kind === 'omi') {
    return {
      url: route.baseUrl,
      init: {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          authorization: `Bearer ${token}`
        },
        body: JSON.stringify(buildOpenAiChatCompletionBody(context, route.model))
      }
    }
  }

  switch (route.provider) {
    case 'openai':
      return {
        url: route.baseUrl,
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${route.key}`
          },
          body: JSON.stringify(buildOpenAiChatCompletionBody(context, route.model))
        }
      }
    case 'openrouter':
      return {
        url: route.baseUrl,
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${route.key}`,
            'HTTP-Referer': 'https://omi.me',
            'X-Title': 'Omi Windows'
          },
          body: JSON.stringify(buildOpenAiChatCompletionBody(context, route.model))
        }
      }
    case 'anthropic':
      return {
        url: route.baseUrl,
        init: {
          method: 'POST',
          headers: {
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
            'x-api-key': route.key
          },
          body: JSON.stringify(buildAnthropicBody(context, route.model))
        }
      }
    case 'gemini':
      return {
        url: route.baseUrl,
        init: {
          method: 'POST',
          headers: {
            'content-type': 'application/json',
            'x-goog-api-key': route.key
          },
          body: JSON.stringify(buildGeminiBody(context))
        }
      }
  }
}

function assistantMessageFromProvider(route: PiModelRoute, raw: JsonRecord): AssistantMessage {
  if (route.kind === 'omi' || route.provider === 'openai' || route.provider === 'openrouter') {
    return assistantMessageFromOpenAiCompletion(route, raw as OpenAiChatCompletion)
  }
  if (route.provider === 'anthropic') return assistantMessageFromAnthropic(route, raw)
  return assistantMessageFromGemini(route, raw)
}

async function callPiProvider(
  route: PiModelRoute,
  context: Context,
  token: string,
  options: PiChatBridgeOptions
): Promise<AssistantMessage> {
  const request = buildPiProviderRequest(route, context, token)
  const response = await (options.fetchImpl ?? fetch)(request.url, request.init)
  if (!response.ok) {
    throw routeError(route, response.status)
  }
  return assistantMessageFromProvider(route, (await response.json()) as JsonRecord)
}

function createPiStreamFn(token: string, route: PiModelRoute, options: PiChatBridgeOptions) {
  return (_model: Model<string>, context: Context): AssistantMessageEventStream => {
    const stream = createAssistantMessageEventStream()
    void (async () => {
      try {
        const message = await callPiProvider(route, context, token, options)
        emitAssistantMessage(stream, message)
      } catch (error) {
        const message = errorAssistantMessage(error, route)
        stream.push({ type: 'error', reason: 'error', error: message })
        stream.end(message)
      }
    })()
    return stream
  }
}

function truncateForToolResult(text: string): string {
  if (text.length <= MAX_TOOL_RESULT_CHARS) return text
  return `${text.slice(0, MAX_TOOL_RESULT_CHARS)}\n\n[truncated ${text.length - MAX_TOOL_RESULT_CHARS} chars]`
}

function resultToToolContent(value: unknown): string {
  const text = typeof value === 'string' ? value : JSON.stringify(value)
  return truncateForToolResult(text)
}

function prepareToolArgs(args: unknown): Record<string, unknown> {
  if (args == null) return {}
  if (typeof args === 'object' && !Array.isArray(args)) return args as Record<string, unknown>
  throw new Error('tool arguments must be a JSON object')
}

function nativePiTool(
  definition: LocalAgentToolDefinition,
  options: PiChatBridgeOptions
): AgentTool<TSchema> {
  const runTool = options.runTool ?? runLocalAgentTool
  const runtimeContext = options.runtimeContext ?? defaultRuntimeContext()
  return {
    name: definition.name,
    label: definition.name
      .split('_')
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(' '),
    description: definition.description,
    parameters: Type.Unsafe(definition.inputSchema as unknown as TSchema),
    prepareArguments: prepareToolArgs,
    executionMode: 'sequential',
    execute: async (_toolCallId, params): Promise<AgentToolResult<unknown>> => {
      addObservabilityBreadcrumb(
        'native_pi.tool_call_started',
        { toolName: definition.name },
        { category: 'native_pi' }
      )
      const result = await runTool(definition.name, params, runtimeContext)
      addObservabilityBreadcrumb(
        'native_pi.tool_call_finished',
        { ok: true, toolName: definition.name },
        { category: 'native_pi' }
      )
      return {
        content: [{ type: 'text', text: resultToToolContent(result) }],
        details: result
      }
    }
  }
}

function nativePiTools(options: PiChatBridgeOptions = {}): AgentTool<TSchema>[] {
  const toolDefinitions = options.toolDefinitions ?? listLocalAgentTools
  return toolDefinitions()
    .filter((tool) => NATIVE_PI_TOOL_NAMES.has(tool.name))
    .map((tool) => nativePiTool(tool, options))
}

function defaultRuntimeContext(): LocalAgentRuntimeContext {
  return {
    localUrl: 'omi://local-agent',
    toolEndpoint: 'omi://native-pi-tool',
    app: {
      name: 'Omi Windows',
      version: '1.0.0',
      appId: 'com.omiwindows.app'
    }
  }
}

function chatMessageToAgentMessage(message: ChatMessage, index = 0): Message {
  const timestamp = Date.now() + index
  if (message.role === 'user') {
    return {
      role: 'user',
      content: [{ type: 'text', text: message.content }],
      timestamp
    }
  }
  return {
    role: 'assistant',
    content: message.content ? [{ type: 'text', text: message.content }] : [],
    api: OMI_PI_API,
    provider: OMI_PI_PROVIDER,
    model: PI_MODEL_ID,
    usage: EMPTY_USAGE,
    stopReason: 'stop',
    timestamp
  }
}

function assistantText(message: AgentMessage): string {
  return message.role === 'assistant' && 'content' in message ? messageText(message) : ''
}

function usageFromAssistant(message: AgentMessage): PiChatUsage {
  if (message.role !== 'assistant' || !('usage' in message)) {
    return { promptTokens: 0, completionTokens: 0, totalTokens: 0 }
  }
  return {
    promptTokens: message.usage.input + message.usage.cacheRead + message.usage.cacheWrite,
    completionTokens: message.usage.output,
    totalTokens: message.usage.totalTokens
  }
}

function systemPromptWithSkills(skillSections: string[]): string {
  if (skillSections.length === 0) return BASE_SYSTEM_PROMPT
  return [
    BASE_SYSTEM_PROMPT,
    'Use these selected skills as additional operating instructions when relevant:',
    skillSections.join('\n\n---\n\n')
  ].join('\n\n')
}

async function loadSelectedSkillSections(
  request: PiChatSendRequest,
  options: PiChatBridgeOptions
): Promise<string[]> {
  const ids = request.skillIds?.filter((id) => typeof id === 'string' && id.trim()) ?? []
  if (ids.length === 0) return []
  const load = options.loadSkillSections ?? loadSkillPromptSections
  return load(ids)
}

export async function sendPiChat(
  request: PiChatSendRequest,
  options: PiChatBridgeOptions = {}
): Promise<PiChatResponse> {
  const token = request.token.trim()
  if (!token) {
    throw new Error('Pi/Omi chat requires a Firebase ID token')
  }

  const skillSections = await loadSelectedSkillSections(request, options)
  const route = await resolvePiModelRoute(request, options)
  const agent = new Agent({
    initialState: {
      systemPrompt: systemPromptWithSkills(skillSections),
      model: piModelForRoute(route),
      tools: nativePiTools(options),
      thinkingLevel: 'off'
    },
    streamFn: createPiStreamFn(token, route, options),
    toolExecution: 'sequential',
    transport: 'sse'
  })

  let finalText = ''
  let usage: PiChatUsage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 }
  const toolCalls: PiChatToolCall[] = []

  agent.subscribe((event: AgentEvent) => {
    if (event.type === 'tool_execution_start') {
      toolCalls.push({ id: event.toolCallId, name: event.toolName })
      return
    }
    if (event.type === 'message_end' && event.message.role === 'assistant') {
      finalText = assistantText(event.message)
      usage = addResponseUsage(usage, usageFromAssistant(event.message))
    }
  })

  addObservabilityBreadcrumb(
    'native_pi.send_started',
    {
      messageCount: request.messages.length,
      toolCount: agent.state.tools.length,
      skillCount: skillSections.length,
      provider: route.provider,
      model: route.model,
      route: route.kind
    },
    { category: 'native_pi' }
  )

  try {
    await agent.prompt(request.messages.map(chatMessageToAgentMessage))
  } catch (error) {
    captureMainException('native_pi.send_failed', error, {
      messageCount: request.messages.length,
      toolCallCount: toolCalls.length
    })
    throw error
  }

  const errorMessage = agent.state.errorMessage
  if (errorMessage) {
    throw new Error(errorMessage)
  }

  addObservabilityBreadcrumb(
    'native_pi.send_finished',
    {
      ok: true,
      toolCallCount: toolCalls.length,
      promptTokens: usage.promptTokens,
      completionTokens: usage.completionTokens,
      totalTokens: usage.totalTokens
    },
    { category: 'native_pi' }
  )

  return {
    text: finalText,
    usage,
    toolCalls
  }
}
