import { useEffect, useRef, useState } from 'react'
import { auth } from '../lib/firebase'
import { gatherLocalContext } from '../lib/localAgent'
import { readCurrentScreen } from '../lib/screenContext'
import type { ChatMessage } from '../../../shared/types'
import type { ChatMsg } from './useChat'

const OMI_BASE = import.meta.env.VITE_OMI_API_BASE as string

/**
 * Session-aware chat hook for the Chat page.
 * Unlike useChat (which manages a single app-lifetime thread), this hook
 * re-loads history whenever sessionId changes and persists to that specific
 * local conversation — enabling the sessions sidebar.
 */
export function useSessionChat(sessionId: string | null): {
  history: ChatMsg[]
  sending: boolean
  send: (text: string) => Promise<void>
  reset: () => void
  sessionTitle: string | null
} {
  const [history, setHistory] = useState<ChatMsg[]>([])
  const [sending, setSending] = useState(false)
  const [sessionTitle, setSessionTitle] = useState<string | null>(null)
  const sendingRef = useRef(false)
  const startedAtRef = useRef<number>(0)

  // Load history whenever sessionId changes
  useEffect(() => {
    setHistory([])
    setSessionTitle(null)
    startedAtRef.current = 0
    if (!sessionId) return
    let cancelled = false
    void window.omi.getLocalConversation(sessionId).then((c) => {
      if (cancelled || !c) return
      startedAtRef.current = c.startedAt || Date.now()
      setSessionTitle(c.title ?? null)
      setHistory(
        (c.messages ?? []).map((m: ChatMessage) => ({
          id: (m as { id?: string }).id ?? crypto.randomUUID(),
          role: m.role,
          content: m.content
        }))
      )
    }).catch(() => {})
    return () => { cancelled = true }
  }, [sessionId])

  const persist = async (thread: ChatMsg[]): Promise<void> => {
    if (!sessionId) return
    if (!startedAtRef.current) startedAtRef.current = Date.now()
    const transcript = thread.map((m) => `${m.role === 'user' ? 'You' : 'Omi'}: ${m.content}`).join('\n\n')
    try {
      await window.omi.insertLocalConversation({
        id: sessionId,
        startedAt: startedAtRef.current,
        endedAt: Date.now(),
        transcript,
        createdAt: startedAtRef.current,
        kind: 'chat',
        messages: thread.map((m) => ({ id: m.id, role: m.role, content: m.content }))
      })
      window.omi.notifyConversationsChanged?.()
    } catch (e) {
      console.error('Failed to persist chat session:', e)
    }
  }

  const send = async (text: string): Promise<void> => {
    if (!text.trim() || sendingRef.current || !sessionId) return
    sendingRef.current = true
    const userMsg: ChatMsg = { id: crypto.randomUUID(), role: 'user', content: text }
    const baseHistory = history
    setHistory((h) => [...h, userMsg])

    const assistantId = crypto.randomUUID()
    setHistory((h) => [...h, { id: assistantId, role: 'assistant', content: '' }])
    setSending(true)

    void persist([...baseHistory, userMsg, { id: assistantId, role: 'assistant', content: '' }])

    let assistantText = ''
    try {
      const token = await auth.currentUser?.getIdToken()
      const [screenContext, localContext] = await Promise.all([
        readCurrentScreen(),
        gatherLocalContext(userMsg.content)
      ])
      const contextParts = [screenContext, localContext].filter(Boolean)
      const textToSend = contextParts.length
        ? `${contextParts.join('\n\n')}\n\n${userMsg.content}`
        : userMsg.content
      const res = await fetch(`${OMI_BASE}/v2/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text: textToSend })
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''
        for (const line of lines) {
          if (!line || line.startsWith('done:') || line.startsWith('think:')) continue
          const content = line.startsWith('data:') ? line.slice(5).replace(/^ /, '') : line
          if (content.startsWith('think:')) continue
          const chunk = content.replace(/__CRLF__/g, '\n')
          if (!chunk) continue
          assistantText += chunk
          setHistory((h) => {
            const next = [...h]
            next[next.length - 1] = { id: assistantId, role: 'assistant', content: assistantText }
            return next
          })
        }
      }
    } catch (e) {
      assistantText = `Error: ${(e as Error).message}`
      setHistory((h) => {
        const next = [...h]
        next[next.length - 1] = { id: assistantId, role: 'assistant', content: assistantText }
        return next
      })
    } finally {
      sendingRef.current = false
      setSending(false)
      await persist([...baseHistory, userMsg, { id: assistantId, role: 'assistant', content: assistantText }])
    }
  }

  const reset = (): void => {
    setHistory([])
    setSending(false)
    sendingRef.current = false
    startedAtRef.current = 0
  }

  return { history, sending, send, reset, sessionTitle }
}
