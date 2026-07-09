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
import type { LocalAgentRuntimeContext, LocalAgentToolDefinition } from '../localAgent/tools'
import { listLocalAgentTools, runLocalAgentTool } from '../localAgent/tools'
import type { ChatMessage, PiChatResponse, PiChatToolCall, PiChatUsage } from '../../shared/types'

const DEFAULT_DESKTOP_API_BASE = 'https://desktop-backend-hhibjajaja-uc.a.run.app'
const PI_MODEL_ID = 'omi-sonnet'
const PI_MODEL_NAME = 'Omi Sonnet'
const OMI_PI_API = 'omi-chat-completions'
const OMI_PI_PROVIDER = 'omi'
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
  loadSkillSections?: (ids: string[]) => Promise<string[]>
}

export type PiChatSendRequest = {
  token: string
  messages: ChatMessage[]
  skillIds?: string[]
}

const TRUTHY_FLAG_VALUES = new Set(['1', 'true', 'yes', 'on'])

function isTruthyFlag(value: string | undefined): boolean {
  return value != null && TRUTHY_FLAG_VALUES.has(value.trim().toLowerCase())
}

/**
 * Experimental Pi/Omi chat routing is fail-closed: it forwards chat history and
 * the Firebase ID token to the desktop backend and exposes local tool access to
 * the agent runtime, so it must stay off unless explicitly enabled via
 * OMI_WINDOWS_PI_CHAT=1 (or OMI_PI_CHAT=1).
 */
export function isPiChatEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return isTruthyFlag(env.OMI_WINDOWS_PI_CHAT) || isTruthyFlag(env.OMI_PI_CHAT)
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

function piModel(baseUrl = desktopApiBaseUrl()): Model<string> {
  return {
    id: PI_MODEL_ID,
    name: PI_MODEL_NAME,
    api: OMI_PI_API,
    provider: OMI_PI_PROVIDER,
    baseUrl: chatCompletionsUrl(baseUrl),
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

function buildOmiChatCompletionBody(context: Context): JsonRecord {
  const tools = openAiToolsForContext(context)
  return {
    model: PI_MODEL_ID,
    stream: false,
    messages: openAiMessagesForContext(context),
    ...(tools.length > 0 ? { tools, tool_choice: 'auto' } : {})
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

function stopReason(
  finishReason?: string | null,
  hasToolCalls = false
): AssistantMessage['stopReason'] {
  if (hasToolCalls || finishReason === 'tool_calls') return 'toolUse'
  if (finishReason === 'length') return 'length'
  return 'stop'
}

function assistantMessageFromCompletion(completion: OpenAiChatCompletion): AssistantMessage {
  const choice = completion.choices?.[0]
  const message = choice?.message
  if (!message) throw new Error('Omi chat returned no message')

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
    api: OMI_PI_API,
    provider: OMI_PI_PROVIDER,
    model: PI_MODEL_ID,
    usage: usageFrom(completion.usage),
    stopReason: stopReason(choice.finish_reason, toolCalls.length > 0),
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

function errorAssistantMessage(error: unknown): AssistantMessage {
  return {
    role: 'assistant',
    content: [],
    api: OMI_PI_API,
    provider: OMI_PI_PROVIDER,
    model: PI_MODEL_ID,
    usage: EMPTY_USAGE,
    stopReason: 'error',
    errorMessage: error instanceof Error ? error.message : String(error),
    timestamp: Date.now()
  }
}

async function callOmiChatCompletions(
  context: Context,
  token: string,
  options: PiChatBridgeOptions
): Promise<OpenAiChatCompletion> {
  const response = await (options.fetchImpl ?? fetch)(
    chatCompletionsUrl(options.desktopApiBaseUrl),
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${token}`
      },
      body: JSON.stringify(buildOmiChatCompletionBody(context))
    }
  )
  if (!response.ok) {
    throw new Error(`Omi Pi provider request failed with HTTP ${response.status}`)
  }
  return (await response.json()) as OpenAiChatCompletion
}

function createOmiStreamFn(token: string, options: PiChatBridgeOptions) {
  return (_model: Model<string>, context: Context): AssistantMessageEventStream => {
    const stream = createAssistantMessageEventStream()
    void (async () => {
      try {
        const completion = await callOmiChatCompletions(context, token, options)
        emitAssistantMessage(stream, assistantMessageFromCompletion(completion))
      } catch (error) {
        const message = errorAssistantMessage(error)
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

export function resultToToolContent(value: unknown): string {
  let text: string
  if (typeof value === 'string') {
    text = value
  } else {
    try {
      text = JSON.stringify(value) ?? 'null'
    } catch {
      text = String(value)
    }
  }
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
      const result = await runTool(definition.name, params, runtimeContext)
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
  return options.loadSkillSections ? options.loadSkillSections(ids) : []
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
  const agent = new Agent({
    initialState: {
      systemPrompt: systemPromptWithSkills(skillSections),
      model: piModel(options.desktopApiBaseUrl),
      tools: nativePiTools(options),
      thinkingLevel: 'off'
    },
    streamFn: createOmiStreamFn(token, options),
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

  await agent.prompt(request.messages.map(chatMessageToAgentMessage))

  const errorMessage = agent.state.errorMessage
  if (errorMessage) {
    throw new Error(errorMessage)
  }
  return {
    text: finalText,
    usage,
    toolCalls
  }
}
