import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, MessageSquare, RotateCcw, Send, Trash2, X } from 'lucide-react'
import type { ActionItemRecord } from '../../../../shared/types'
import {
  clearTaskChat,
  loadTaskChat,
  sendTaskChatMessage,
  type TaskChatMessage
} from '../../lib/taskChat'

// Per-task "Investigate with Omi" chat (mac parity: TaskChatPanel.swift). A
// trailing panel scoped to one task: transcript persisted per backendId, sends
// through the task-scoped prompt in lib/taskChat, and degrades honestly — a
// failed send keeps the user's turn visible with a retry instead of a fake reply.
// The page remounts this component (keyed by task) when the target task changes,
// so all state here is naturally per-task — no reset effect needed.

export type TaskChatPanelProps = {
  task: ActionItemRecord
  onClose: () => void
}

export function TaskChatPanel({ task, onClose }: TaskChatPanelProps): React.JSX.Element {
  const [messages, setMessages] = useState<TaskChatMessage[]>(() => loadTaskChat(task.backendId))
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // The transcript the retry re-sends: the history BEFORE the failed turn plus
  // the turn's text, captured at failure time.
  const retryRef = useRef<{ history: TaskChatMessage[]; text: string } | null>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, sending])

  const send = useCallback(
    async (text: string, history: TaskChatMessage[]): Promise<void> => {
      if (sending) return
      const trimmed = text.trim()
      if (!trimmed) return
      setSending(true)
      setError(null)
      // Show the user's turn immediately; sendTaskChatMessage persists it too.
      setMessages([...history, { role: 'user', content: trimmed, at: Date.now() }])
      setInput('')
      try {
        const next = await sendTaskChatMessage(task, history, trimmed)
        setMessages(next)
        retryRef.current = null
      } catch {
        retryRef.current = { history, text: trimmed }
        setError('Omi could not reply. Check your connection and retry.')
      } finally {
        setSending(false)
      }
    },
    [sending, task]
  )

  const retry = (): void => {
    const pending = retryRef.current
    if (pending) void send(pending.text, pending.history)
  }

  const clear = (): void => {
    clearTaskChat(task.backendId)
    setMessages([])
    setError(null)
    retryRef.current = null
  }

  return (
    <aside
      data-testid="task-chat-panel"
      className="flex h-full w-[360px] shrink-0 flex-col border-l border-white/10 bg-black/30"
    >
      <div className="flex items-start justify-between px-4 py-3">
        <div className="min-w-0">
          <h2 className="flex items-center gap-1.5 text-sm font-semibold text-white/90">
            <MessageSquare className="h-4 w-4 text-white/50" />
            Investigate
          </h2>
          <p className="truncate text-[11px] text-white/45" title={task.description}>
            {task.description}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {messages.length > 0 && (
            <button
              data-testid="task-chat-clear"
              onClick={clear}
              disabled={sending}
              className="rounded-md p-1 text-white/40 hover:bg-white/5 hover:text-white/80 disabled:opacity-40"
              title="Clear this task's chat"
              aria-label="Clear this task's chat"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
          <button
            data-testid="task-chat-close"
            onClick={onClose}
            className="rounded-md p-1 text-white/40 hover:bg-white/5 hover:text-white/80"
            aria-label="Close investigate panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        {messages.length === 0 && !sending && (
          <p className="pt-6 text-center text-xs leading-relaxed text-white/40">
            Ask Omi to break this task down, draft a reply, or figure out the next step.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={`${m.at}-${i}`}
            className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-xs leading-relaxed ${
              m.role === 'user'
                ? 'ml-auto bg-white/15 text-white'
                : 'mr-auto bg-white/5 text-white/85'
            }`}
          >
            {m.content}
          </div>
        ))}
        {sending && (
          <div className="mr-auto flex items-center gap-2 rounded-2xl bg-white/5 px-3 py-2 text-xs text-white/50">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Thinking…
          </div>
        )}
        {error && (
          <div className="mr-auto flex items-center gap-2 text-xs text-rose-300/80">
            <span>{error}</span>
            <button
              data-testid="task-chat-retry"
              onClick={retry}
              className="inline-flex items-center gap-1 rounded-md border border-white/15 px-2 py-0.5 text-white/70 hover:bg-white/5"
            >
              <RotateCcw className="h-3 w-3" />
              Retry
            </button>
          </div>
        )}
      </div>

      <div className="border-t border-white/10 p-3">
        <div className="flex items-end gap-2">
          <textarea
            data-testid="task-chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send(input, messages)
              }
            }}
            rows={2}
            placeholder="Ask about this task…"
            className="input-field min-h-0 flex-1 resize-none text-xs"
            disabled={sending}
          />
          <button
            data-testid="task-chat-send"
            onClick={() => void send(input, messages)}
            disabled={sending || !input.trim()}
            className="btn-primary px-3 py-2 disabled:opacity-40"
            aria-label="Send"
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </aside>
  )
}
