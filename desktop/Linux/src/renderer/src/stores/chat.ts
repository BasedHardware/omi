import { create } from 'zustand'
import { api } from '../api/client'
import { buildSystemPrompt, streamChatCompletion, type ChatMessage } from '../api/chat'
import { useSettings } from './settings'
import { speak } from '../lib/tts'

export interface UiChatMessage {
  id: string
  serverId?: string
  role: 'user' | 'assistant'
  text: string
  imageDataUrl?: string
  streaming?: boolean
  error?: boolean
  rating?: 1 | -1 | 0
  /** ISO timestamp the message was created; rendered under each bubble. */
  createdAt?: string
}

interface ChatStore {
  messages: UiChatMessage[]
  streaming: boolean
  historyLoaded: boolean
  sessionId: string | null
  userName?: string
  setUserName: (name?: string) => void
  setSession: (sessionId: string | null) => Promise<void>
  loadHistory: () => Promise<void>
  send: (text: string, opts?: { imageDataUrl?: string; screenContext?: string }) => Promise<void>
  rate: (uiId: string, value: 1 | -1) => Promise<void>
  stop: () => void
  clear: () => void
}

function currentModel(): string {
  return useSettings.getState().settings?.aiModel || 'claude-sonnet-4-6'
}

async function persistMessage(sessionId: string | null, text: string, sender: 'human' | 'ai'): Promise<string | undefined> {
  try {
    const res = await window.omi.api.request({
      method: 'POST',
      url: 'v2/desktop/messages',
      base: 'python',
      body: JSON.stringify({ text, sender, session_id: sessionId ?? undefined })
    })
    if (res.status >= 200 && res.status < 300) return (JSON.parse(res.body) as { id?: string }).id
  } catch {
    // best-effort persistence
  }
  return undefined
}

let activeCancel: (() => void) | null = null
let counter = 0
const nextId = () => `m${++counter}_${Date.now()}`

function toApiMessages(history: UiChatMessage[], opts?: { imageDataUrl?: string; screenContext?: string }, userName?: string): ChatMessage[] {
  const messages: ChatMessage[] = [{ role: 'system', content: buildSystemPrompt(userName) }]
  // Cap context at the last 20 turns, mirroring the floating bar's short history window.
  const recent = history.slice(-20)
  for (let i = 0; i < recent.length; i++) {
    const m = recent[i]
    const isLast = i === recent.length - 1
    if (m.role === 'user' && isLast && opts?.imageDataUrl) {
      messages.push({
        role: 'user',
        content: [
          { type: 'text', text: m.text || 'What do you see on my screen?' },
          { type: 'image_url', image_url: { url: opts.imageDataUrl } }
        ]
      })
    } else if (m.role === 'user' && isLast && opts?.screenContext) {
      messages.push({
        role: 'user',
        content: `${m.text}\n\n[Current screen text (OCR)]:\n${opts.screenContext.slice(0, 6000)}`
      })
    } else {
      messages.push({ role: m.role, content: m.text })
    }
  }
  return messages
}

export const useChat = create<ChatStore>((set, get) => ({
  messages: [],
  streaming: false,
  historyLoaded: false,
  sessionId: null,
  userName: undefined,
  setUserName: (name) => set({ userName: name }),
  setSession: async (sessionId) => {
    // Cancel any in-flight stream from the previous session so its deltas and
    // persistence do not bleed into the new one, and clear the streaming flag.
    activeCancel?.()
    activeCancel = null
    set({ sessionId, messages: [], historyLoaded: false, streaming: false })
    await get().loadHistory()
  },
  loadHistory: async () => {
    try {
      const sessionId = get().sessionId
      const server = sessionId ? await api.listSessionMessages(sessionId, 100) : await api.listMessages(60)
      const sorted = server
        .slice()
        .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
      const mapped: UiChatMessage[] = sorted.map((m) => ({
        id: m.id,
        serverId: m.id,
        role: m.sender === 'ai' ? 'assistant' : 'user',
        text: m.text,
        createdAt: m.created_at
      }))
      set({ messages: mapped, historyLoaded: true })
    } catch {
      set({ historyLoaded: true })
    }
  },
  rate: async (uiId, value) => {
    const msg = get().messages.find((m) => m.id === uiId)
    if (!msg?.serverId) return
    const next = msg.rating === value ? 0 : value
    set({ messages: get().messages.map((m) => (m.id === uiId ? { ...m, rating: next } : m)) })
    try {
      await api.rateMessage(msg.serverId, next === 0 ? null : next)
    } catch {
      // ignore
    }
  },
  send: async (text, opts) => {
    const trimmed = text.trim()
    if (!trimmed && !opts?.imageDataUrl) return
    if (get().streaming) return

    const sessionId = get().sessionId
    const now = new Date().toISOString()
    const userMsg: UiChatMessage = { id: nextId(), role: 'user', text: trimmed, imageDataUrl: opts?.imageDataUrl, createdAt: now }
    const assistantMsg: UiChatMessage = { id: nextId(), role: 'assistant', text: '', streaming: true, createdAt: now }
    set({ messages: [...get().messages, userMsg, assistantMsg], streaming: true })
    void persistMessage(sessionId, trimmed, 'human')

    const finish = (errorText?: string) => {
      if (sessionId !== get().sessionId) {
        // Session switched mid-stream: do not write into the new session, do not
        // persist this reply to the old session, and leave activeCancel/streaming
        // for whatever owns the current session.
        return
      }
      const finalText = errorText ?? get().messages.find((m) => m.id === assistantMsg.id)?.text ?? ''
      set({
        messages: get().messages.map((m) =>
          m.id === assistantMsg.id ? { ...m, streaming: false, error: !!errorText, text: finalText } : m
        ),
        streaming: false
      })
      activeCancel = null
      if (!errorText && finalText) {
        void persistMessage(sessionId, finalText, 'ai').then((serverId) => {
          if (serverId) {
            set({ messages: get().messages.map((m) => (m.id === assistantMsg.id ? { ...m, serverId } : m)) })
          }
        })
        if (useSettings.getState().settings?.ttsEnabled) void speak(finalText)
      }
    }

    const run = (withImage: boolean) => {
      const apiMessages = toApiMessages(
        get().messages.filter((m) => m.id !== assistantMsg.id),
        withImage ? opts : { screenContext: opts?.screenContext },
        get().userName
      )
      const handle = streamChatCompletion(
        apiMessages,
        (delta) => {
          if (sessionId !== get().sessionId) return
          set({
            messages: get().messages.map((m) => (m.id === assistantMsg.id ? { ...m, text: m.text + delta } : m))
          })
        },
        () => finish(),
        (status, body) => {
          if (withImage && opts?.imageDataUrl && (status === 400 || status === 422)) {
            // Proxy may not accept image parts, retry with OCR text context instead.
            run(false)
            return
          }
          if (status === 402 || status === 403) {
            finish('This feature needs an active Omi subscription or trial. Open omi.me to manage your plan.')
          } else if (status === 429) {
            finish('Rate limited, give it a few seconds and try again.')
          } else {
            finish(`Something went wrong (HTTP ${status}). ${body.slice(0, 200)}`)
          }
        },
        currentModel()
      )
      activeCancel = handle.cancel
    }

    run(!!opts?.imageDataUrl)
  },
  stop: () => {
    activeCancel?.()
    activeCancel = null
    set({
      streaming: false,
      messages: get().messages.map((m) => (m.streaming ? { ...m, streaming: false } : m))
    })
  },
  clear: () => {
    activeCancel?.()
    activeCancel = null
    set({ messages: [], streaming: false })
  }
}))
