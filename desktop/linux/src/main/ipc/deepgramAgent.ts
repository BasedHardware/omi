// src/main/ipc/deepgramAgent.ts
// Deepgram Voice Agent — STT + LLM + TTS in one WebSocket
import { ipcMain, WebContents, webContents, shell } from 'electron'
import WebSocket from 'ws'
import fs from 'fs'
import path from 'path'
import { app } from 'electron'
import type { AgentConfig, DeepgramVoice } from '../../shared/types'
import { listLocalConversations, queryKgNodes } from './db'

const AGENT_WS_URL = 'wss://agent.deepgram.com/v1/agent/converse'

type AgentSession = {
  ws: WebSocket
  ownerId: number
  buffer: ArrayBuffer[]
  closed: boolean
  keepalive?: ReturnType<typeof setInterval>
}

const sessions = new Map<string, AgentSession>()

function emit(ownerId: number, channel: string, data: unknown): void {
  const wc = webContents.fromId(ownerId)
  if (wc && !wc.isDestroyed()) {
    wc.send(channel, data)
  }
}

type AgentMessage =
  | { type: 'Welcome'; request_id: string }
  | { type: 'SettingsApplied' }
  | { type: 'ConversationText'; role: 'user' | 'assistant'; content: string }
  | { type: 'AgentThinking'; content: string }
  | { type: 'AgentStartedSpeaking'; total_latency: number; tts_latency: number; ttt_latency: number }
  | { type: 'AgentAudioDone' }
  | { type: 'Error'; description: string; code: string }
  | { type: 'Warning'; description: string; code: string }
  | { type: 'History'; role?: string; content?: string; function_calls?: unknown[] }
  | { type: 'UserStartedSpeaking' }
  | { type: string; [key: string]: unknown }

// Tool execution functions
async function executeTool(name: string, args: Record<string, unknown>): Promise<string> {
  switch (name) {
    case 'web_search': {
      const query = (args.query as string) || ''
      try {
        const res = await fetch(`https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`, {
          headers: { 'User-Agent': 'Mozilla/5.0' }
        })
        const html = await res.text()
        // Extract snippets from DuckDuckGo HTML results
        const snippets: string[] = []
        const regex = /class="result__snippet">(.*?)<\/a>/gs
        let match
        while ((match = regex.exec(html)) !== null && snippets.length < 3) {
          const text = match[1].replace(/<[^>]+>/g, '').trim()
          if (text) snippets.push(text)
        }
        return snippets.length > 0
          ? `Search results for "${query}":\n${snippets.join('\n')}`
          : `No results found for "${query}"`
      } catch (e) {
        return `Search failed: ${(e as Error).message}`
      }
    }
    case 'get_time': {
      const now = new Date()
      return `Current time: ${now.toLocaleTimeString()} on ${now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}`
    }
    case 'calculate': {
      const expr = (args.expression as string) || ''
      try {
        // Safe math evaluation (no eval)
        const result = Function('"use strict"; return (' + expr.replace(/[^0-9+\-*/().%\s]/g, '') + ')')()
        return `${expr} = ${result}`
      } catch {
        return `Could not calculate "${expr}". Please check the expression.`
      }
    }
    case 'search_local_memories': {
      const query = (args.query as string) || ''
      try {
        const graph = queryKgNodes(query)
        if (graph.nodes.length === 0) return 'No relevant local memories found.'
        const context = graph.nodes.map(n => `[${n.nodeType}] ${n.label}: ${n.summary}`).join('\n')
        return `Relevant local memories:\n${context}`
      } catch (e) {
        return `Memory search failed: ${(e as Error).message}`
      }
    }
    case 'write_file': {
      const filePath = args.filePath as string
      const content = args.content as string
      try {
        const dir = path.dirname(filePath)
        if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true })
        fs.writeFileSync(filePath, content, 'utf8')
        return `File written successfully to ${filePath}`
      } catch (e) {
        return `Failed to write file: ${(e as Error).message}`
      }
    }
    case 'open_url': {
      const url = args.url as string
      try {
        shell.openExternal(url)
        return `Opened ${url} in the browser.`
      } catch (e) {
        return `Failed to open URL: ${(e as Error).message}`
      }
    }
    case 'set_reminder': {
      const message = (args.message as string) || ''
      const minutes = (args.minutes_from_now as number) || 0
      // Schedule reminder via renderer notification
      setTimeout(() => {
        // Find any open window and send notification
        const { BrowserWindow } = require('electron')
        const wins = BrowserWindow.getAllWindows()
        for (const win of wins) {
          if (!win.isDestroyed()) {
            win.webContents.send('deepgram-agent:reminder', { message, triggeredAt: Date.now() })
          }
        }
      }, minutes * 60 * 1000)
      return `Reminder set: "${message}" in ${minutes} minute${minutes !== 1 ? 's' : ''}`
    }
    default:
      return `Unknown tool: ${name}`
  }
}

function handleFunctionCall(
  session: AgentSession,
  ws: WebSocket,
  id: string,
  name: string,
  argsJson: string,
  sessionId: string
): void {
  let args: Record<string, unknown> = {}
  try {
    args = JSON.parse(argsJson)
  } catch { /* ignore */ }

  console.log(`[agent] executing tool: ${name}(${JSON.stringify(args)})`)

  executeTool(name, args).then((result) => {
    console.log(`[agent] tool result: ${name} -> ${result.substring(0, 100)}...`)
    // Send function call response back to Deepgram
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'SendFunctionCallResponse',
        id,
        name,
        content: result
      }))
    }
    // Also notify renderer
    emit(session.ownerId, 'deepgram-agent:message', {
      sessionId,
      kind: 'functionCall',
      name,
      args,
      result
    })
  }).catch((err) => {
    console.error(`[agent] tool error: ${name}:`, err)
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'SendFunctionCallResponse',
        id,
        name,
        content: `Error executing ${name}: ${(err as Error).message}`
      }))
    }
  })
}

function startAgentSession(
  sessionId: string,
  owner: WebContents,
  apiKey: string,
  config: AgentConfig
): void {
  const existing = sessions.get(sessionId)
  if (existing) {
    try { existing.ws.close() } catch { /* ignore */ }
    sessions.delete(sessionId)
  }

  const url = AGENT_WS_URL
  console.log(`[agent] connecting session ${sessionId}`)

  const ws = new WebSocket(url, {
    headers: {
      Authorization: `Token ${apiKey}`
    },
    handshakeTimeout: 10000
  })
  ws.binaryType = 'arraybuffer'

  const session: AgentSession = {
    ws,
    ownerId: owner.id,
    buffer: [],
    closed: false
  }
  sessions.set(sessionId, session)

  ws.on('open', () => {
    console.log(`[agent] session ${sessionId} connected, sending settings`)
    const systemPrompt = buildSystemPrompt(config)
    const agentName = config.agentName || 'friend'
    console.log(`[agent] system prompt: ${systemPrompt.substring(0, 200)}...`)

    // Build conversation context from past sessions
    const contextMessages = buildConversationContext()
    console.log(`[agent] loaded ${contextMessages.length} past conversation entries`)

    const tools = [
      {
        name: 'web_search',
        description: 'Search the web for current information. Use this when the user asks about news, facts, or anything you are not sure about.',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'The search query' }
          },
          required: ['query']
        }
      },
      {
        name: 'get_time',
        description: 'Get the current date and time.',
        parameters: { type: 'object', properties: {} }
      },
      {
        name: 'calculate',
        description: 'Perform a mathematical calculation.',
        parameters: {
          type: 'object',
          properties: {
            expression: { type: 'string', description: 'Math expression to evaluate, e.g. "2 + 2" or "sqrt(144)"' }
          },
          required: ['expression']
        }
      },
      {
        name: 'search_local_memories',
        description: 'Search the user\'s local knowledge graph for personal memories, preferences, and project details.',
        parameters: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'The search query to find relevant local memories' }
          },
          required: ['query']
        }
      },
      {
        name: 'write_file',
        description: 'Write text or code to a file on the local system. Use this to build games, scripts, or documents.',
        parameters: {
          type: 'object',
          properties: {
            filePath: { type: 'string', description: 'The absolute path where the file should be saved' },
            content: { type: 'string', description: 'The content to write to the file' }
          },
          required: ['filePath', 'content']
        }
      },
      {
        name: 'open_url',
        description: 'Open a URL or a local file path in the default browser or application.',
        parameters: {
          type: 'object',
          properties: {
            url: { type: 'string', description: 'The URL or file path to open' }
          },
          required: ['url']
        }
      },
      {
        name: 'set_reminder',
        description: 'Set a reminder for the user.',
        parameters: {
          type: 'object',
          properties: {
            message: { type: 'string', description: 'What to remind the user about' },
            minutes_from_now: { type: 'number', description: 'Minutes from now to trigger the reminder' }
          },
          required: ['message', 'minutes_from_now']
        }
      }
    ]

    // Build think provider based on llmProvider config
    let thinkProvider: { type: string; model: string; baseUrl?: string }
    const llmProvider = config.llmProvider || 'deepgram'
    const llmModel = config.llmModel
    const llmBaseUrl = config.llmBaseUrl

    switch (llmProvider) {
      case 'ollama':
        thinkProvider = {
          type: 'open_ai',
          model: llmModel || 'qwen3.5',
          baseUrl: llmBaseUrl || 'http://localhost:11434/v1'
        }
        console.log(`[agent] using Ollama: ${thinkProvider.model} at ${thinkProvider.baseUrl}`)
        break
      case 'openai':
        thinkProvider = {
          type: 'open_ai',
          model: llmModel || 'gpt-4o-mini'
        }
        console.log(`[agent] using OpenAI: ${thinkProvider.model}`)
        break
      case 'deepgram':
      default:
        thinkProvider = {
          type: 'open_ai',
          model: llmModel || 'gpt-4o-mini'
        }
        console.log(`[agent] using Deepgram hosted LLM: ${thinkProvider.model}`)
        break
    }

    // Allow explicit thinkProvider config to override
    if (config.thinkProvider) {
      thinkProvider = config.thinkProvider.provider
    }

    const settings: Record<string, unknown> = {
      type: 'Settings',
      audio: {
        input: { encoding: 'linear16', sample_rate: 16000 },
        output: { encoding: 'linear16', sample_rate: 24000 }
      },
      agent: {
        language: config.language || 'en',
        listen: {
          provider: {
            type: 'deepgram',
            model: 'nova-2',
            sentiment: true,
            diarize: true
          }
        },
        think: {
          provider: thinkProvider,
          prompt: systemPrompt,
          functions: tools
        },
        speak: {
          provider: {
            type: 'deepgram',
            model: config.ttsVoice || 'aura-2-thalia-en'
          }
        },
        greeting: config.greeting || `Hey! I'm ${agentName}. How can I help?`,
        ...(contextMessages.length > 0 ? { context: { messages: contextMessages } } : {})
      }
    }
    console.log(`[agent] sending settings with ${tools.length} tools, ${contextMessages.length} context messages`)
    ws.send(JSON.stringify(settings))
    // Flush buffered audio
    for (const chunk of session.buffer) {
      if (ws.readyState === WebSocket.OPEN) ws.send(chunk)
    }
    session.buffer = []
    // Keepalive
    const keepalive = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'KeepAlive' }))
      } else {
        clearInterval(keepalive)
      }
    }, 8000)
    session.keepalive = keepalive
  })

  ws.on('message', (data, isBinary) => {
    if (isBinary) {
      // Binary audio from agent TTS — forward to renderer
      emit(session.ownerId, 'deepgram-agent:audio', {
        sessionId,
        audio: Buffer.from(data as ArrayBuffer).toString('base64')
      })
      return
    }

    const text = data.toString().trim()
    if (!text) return

    let msg: AgentMessage
    try {
      msg = JSON.parse(text)
    } catch {
      return
    }

    console.log(`[agent] message: ${msg.type}`)

    switch (msg.type) {
      case 'Welcome':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'connected',
          requestId: msg.request_id
        })
        break
      case 'SettingsApplied':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'settingsApplied'
        })
        break
      case 'ConversationText':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'conversationText',
          role: msg.role,
          content: msg.content
        })
        break
      case 'AgentThinking':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'thinking',
          content: msg.content
        })
        break
      case 'AgentStartedSpeaking':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'agentSpeaking',
          totalLatency: msg.total_latency,
          ttsLatency: msg.tts_latency,
          tttLatency: msg.ttt_latency
        })
        break
      case 'AgentAudioDone':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'agentAudioDone'
        })
        break
      case 'Error':
        console.error(`[agent] error: ${msg.code} - ${msg.description}`)
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'error',
          message: msg.description,
          code: msg.code
        })
        break
      case 'Warning':
        console.warn(`[agent] warning: ${msg.code} - ${msg.description}`)
        break
      case 'History':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'history',
          role: msg.role,
          content: msg.content,
          functionCalls: msg.function_calls
        })
        break
      case 'UserStartedSpeaking':
        emit(session.ownerId, 'deepgram-agent:message', {
          sessionId,
          kind: 'userSpeaking'
        })
        break
      case 'FunctionCallRequest': {
        const funcs = (msg as { functions?: Array<{ id: string; name: string; arguments: string; client_side: boolean }> }).functions || []
        console.log(`[agent] function call request: ${funcs.length} functions`)
        for (const fn of funcs) {
          if (fn.client_side) {
            handleFunctionCall(session, ws, fn.id, fn.name, fn.arguments, sessionId)
          } else {
            console.log(`[agent] server-side function: ${fn.name}`)
          }
        }
        break
      }
      default:
        console.log(`[agent] unhandled message type: ${msg.type}`)
    }
  })

  ws.on('error', (err) => {
    console.error(`[agent] session ${sessionId} error:`, err.message)
    emit(session.ownerId, 'deepgram-agent:message', {
      sessionId,
      kind: 'error',
      message: err.message,
      fatal: true
    })
  })

  ws.on('close', (code, reasonBuf) => {
    if (session.closed) return
    session.closed = true
    if (session.keepalive) clearInterval(session.keepalive)
    sessions.delete(sessionId)
    console.log(`[agent] session ${sessionId} closed (${code})`)
    emit(session.ownerId, 'deepgram-agent:message', {
      sessionId,
      kind: 'closed',
      code,
      reason: reasonBuf.toString()
    })
  })
}

function feedAgent(sessionId: string, pcm: ArrayBuffer): void {
  const s = sessions.get(sessionId)
  if (!s || s.closed) return
  if (s.ws.readyState !== WebSocket.OPEN) {
    s.buffer.push(pcm)
    if (s.buffer.length > 200) s.buffer.shift()
    return
  }
  s.ws.send(pcm)
}

function stopAgent(sessionId: string): void {
  const s = sessions.get(sessionId)
  if (!s) return
  s.closed = true
  if (s.keepalive) clearInterval(s.keepalive)
  sessions.delete(sessionId)
  try { s.ws.close(1000, 'client close') } catch { /* ignore */ }
}


function loadSoulMd(): string {
  // Try app root first (dev/build), then resources path (packaged), then user config
  const candidates = [
    path.join(app.isPackaged ? process.resourcesPath : app.getAppPath(), 'soul.md'),
    path.join(app.isPackaged ? process.resourcesPath : app.getAppPath(), 'resources', 'soul.md'),
    path.join(app.getPath('home'), '.config', 'omi', 'soul.md'),
    path.join(process.cwd(), 'soul.md')
  ]
  for (const p of candidates) {
    try {
      const content = fs.readFileSync(p, 'utf-8')
      console.log(`[agent] loaded soul.md from: ${p}`)
      return content
    } catch { /* continue */ }
  }
  console.warn('[agent] no soul.md found, using default personality')
  return ''
}

const MAX_HISTORY_CONVERSATIONS = 5
const MAX_HISTORY_CHARS = 4000

function buildConversationContext(): Array<{ type: string; role: string; content: string }> {
  const messages: Array<{ type: string; role: string; content: string }> = []
  try {
    const conversations = listLocalConversations().slice(0, MAX_HISTORY_CONVERSATIONS)
    if (conversations.length === 0) return messages

    let totalChars = 0
    for (const convo of conversations) {
      const transcript = convo.transcript || ''
      if (!transcript) continue
      // Truncate individual transcripts to keep context manageable
      const truncated = transcript.length > 800 ? transcript.slice(0, 800) + '…' : transcript
      if (totalChars + truncated.length > MAX_HISTORY_CHARS) break
      totalChars += truncated.length
      messages.push({
        type: 'History',
        role: 'user',
        content: `[Past conversation — ${new Date(convo.startedAt).toLocaleDateString()}]: ${truncated}`
      })
    }
  } catch (err) {
    console.error('[agent] failed to load conversation history:', err)
  }
  return messages
}

function buildSystemPrompt(config: AgentConfig): string {
  const name = config.agentName || 'friend'
  const wakeWord = config.activationMode !== 'always'
  const clarification = config.clarificationEnabled !== false

  if (config.systemPrompt) return config.systemPrompt

  // Try loading soul.md first — it defines the agent's core identity
  const soulMd = loadSoulMd()
  let prompt: string

  if (soulMd) {
    // soul.md is the base personality — user settings layer on top
    prompt = soulMd
    // Override name if specified in settings
    if (name !== 'friend') {
      prompt += `\n\nYour name is "${name}".`
    }
  } else {
    // Fallback to built-in personality
    prompt = `You are ${name}, a high-intelligence voice companion. You are sharp, concise, and genuinely helpful.
    
Core rules:
- You are a real-time voice assistant. Keep responses extremely concise (1-2 sentences) unless asked for detail.
- Be natural, conversational, and a bit witty. Avoid "AI-speak".
- Never say "as an AI" or use disclaimes.
- Match the user's energy. If they are brief, be brief. If they are excited, be excited.`
  }
  
  if (wakeWord) {
    prompt += `
    
Activation & Crowded Rooms:
- You are named "${name}". Only respond when directly addressed by name.
- In crowded environments, use speaker diarization to ignore background chatter.
- If multiple people are talking, only engage if you are specifically called.
- Stay completely silent if you are not the focus of the conversation.`
  } else {
    prompt += `
    
Activation:
- You respond to everything the user says, but be sharp and avoid rambling.
- If you sense the user is talking to someone else, stay brief or silent.`
  }
  
  if (clarification) {
    prompt += `
    
Clarification:
- If a request is ambiguous, ask one sharp clarifying question. Don't guess.
- Keep it short: "Which project do you mean?" not "I'm not sure which project you're referring to, could you please clarify?"`
  }
  
  prompt += `
  
Intelligence & Memory:
- You have a local knowledge graph of the user's life, projects, and preferences.
- ALWAYS use 'search_local_memories' before answering questions about the user's history or preferences.
- Don't just recite memories; use them to provide personalized, smart insights.
- If the user shares a new idea or fact, encourage them or note that you'll remember it.
  
Action Capability:
- You can build things. Use 'write_file' to create code/documents and 'open_url' to show the result.
- If asked to "build a game" or "create a site", write the necessary files and then open the main file in the browser.
  
Conversation awareness:
- You hear the user's side of conversations. Offer brief, high-value insights only when genuinely helpful.
- Be the "smartest person in the room" who knows when to speak and when to listen.`
  
  // Inject conversation context if provided
  if (config.conversationContext) {
    prompt += `

Memory of past conversations:
${config.conversationContext}

Use this context to understand what the user has been working on. Reference it naturally: "Earlier you mentioned..." or "Last time we talked about..."`

    prompt += `

Memory:
- You have access to the user's recent conversation history
- Reference past discussions naturally
- You remember the user's projects, interests, and ongoing tasks
- Use this context to provide relevant, personalized help`
  }

  // Inject session context
  if (config.sessionContext) {
    if (config.sessionContext.currentProject) {
      prompt += `

Current project: ${config.sessionContext.currentProject}
- You're helping with this project right now
- Be ready to help with coding, debugging, or planning`
    }

    if (config.sessionContext.currentActivity) {
      prompt += `

Current activity: ${config.sessionContext.currentActivity}
- Adapt your responses to match what the user is doing`
    }

    if (config.sessionContext.recentFiles?.length) {
      prompt += `

Recent files:
${config.sessionContext.recentFiles.map((f) => `- ${f}`).join('\n')}
- Be aware of these when answering questions`
    }
  }

  // Inject cloud memories if provided
  if (config.memories && config.memories.length > 0) {
    const memoryList = config.memories
      .slice(0, 20)
      .map((m) => `- ${m.content}`)
      .join('\n')
    prompt += `

What you know about the user:
${memoryList}

Use these memories to personalize your responses. Reference them naturally when relevant, but don't recite them all at once. You know the user's projects, interests, and preferences.`
  }

  prompt += `

Workflow:
- Use web_search when you need current information
- Use calculate for any math
- Use set_reminder when the user wants to remember something
- Be proactive: if the user mentions a task, offer to set a reminder`

  return prompt
}

let deepgramApiKey = ''

export function setAgentApiKey(key: string): void {
  deepgramApiKey = key
}

export function getAgentApiKey(): string {
  return deepgramApiKey
}

export function registerDeepgramAgentHandlers(): void {
  ipcMain.handle('deepgram-agent:start', (e, args: { sessionId: string; config?: AgentConfig }) => {
    if (!deepgramApiKey) {
      console.warn('[agent] no API key configured')
      emit(e.sender.id, 'deepgram-agent:message', {
        sessionId: args.sessionId,
        kind: 'error',
        message: 'Deepgram API key not configured',
        fatal: true
      })
      return
    }
    startAgentSession(args.sessionId, e.sender, deepgramApiKey, args.config || {})
  })

  ipcMain.handle('deepgram-agent:stop', (_e, sessionId: string) => {
    stopAgent(sessionId)
  })

  ipcMain.on('deepgram-agent:feed', (_e, sessionId: string, pcm: ArrayBuffer) => {
    feedAgent(sessionId, pcm)
  })

  ipcMain.handle('deepgram-agent:listVoices', async () => {
    // Return known Deepgram Aura voices
    const voices: DeepgramVoice[] = [
      { id: 'aura-2-thalia-en', name: 'Thalia', lang: 'en' },
      { id: 'aura-2-asteria-en', name: 'Asteria', lang: 'en' },
      { id: 'aura-2-luna-en', name: 'Luna', lang: 'en' },
      { id: 'aura-2-stella-en', name: 'Stella', lang: 'en' },
      { id: 'aura-2-athena-en', name: 'Athena', lang: 'en' },
      { id: 'aura-2-hera-en', name: 'Hera', lang: 'en' },
      { id: 'aura-2-orion-en', name: 'Orion', lang: 'en' },
      { id: 'aura-2-arcas-en', name: 'Arcas', lang: 'en' },
      { id: 'aura-2-perseus-en', name: 'Perseus', lang: 'en' },
      { id: 'aura-2-angus-en', name: 'Angus', lang: 'en' },
      { id: 'aura-2-orpheus-en', name: 'Orpheus', lang: 'en' },
      { id: 'aura-2-helios-en', name: 'Helios', lang: 'en' },
      { id: 'aura-2-zeus-en', name: 'Zeus', lang: 'en' }
    ]
    return voices
  })

  // Ollama health check — verifies local LLM is reachable
  ipcMain.handle('deepgram-agent:ollamaCheck', async () => {
    try {
      const res = await fetch('http://localhost:11434/api/tags', { signal: AbortSignal.timeout(3000) })
      if (res.ok) {
        const data = await res.json() as { models?: Array<{ name: string }> }
        return {
          ok: true,
          models: (data.models ?? []).map((m) => m.name)
        }
      }
      return { ok: false, error: `HTTP ${res.status}` }
    } catch (e) {
      return { ok: false, error: (e as Error).message }
    }
  })
}
