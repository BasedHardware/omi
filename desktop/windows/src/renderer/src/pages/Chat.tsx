import { useEffect, useRef, useState } from 'react'
import { Send, Paperclip, RotateCcw } from 'lucide-react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { useAppState } from '../state/AppStateProvider'
import { ChatMessages } from '../components/chat/ChatMessages'
import omiMark from '../assets/omi-logo.png'


export function Chat(): React.JSX.Element {
  const { chat } = useAppState()
  const [user, setUser] = useState<{ displayName?: string | null; email?: string | null } | null>(
    auth.currentUser
  )
  const [input, setInput] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const nearBottomRef = useRef(true)

  useEffect(() => onAuthStateChanged(auth, (u) => setUser(u)), [])

  // Auto-scroll when new messages arrive (only if near bottom)
  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (nearBottomRef.current) {
      el.scrollTop = el.scrollHeight
    }
  }, [chat.history])

  // Track scroll position to decide auto-scroll
  const onScroll = (): void => {
    const el = scrollRef.current
    if (!el) return
    nearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80
  }

  const send = (): void => {
    const text = input.trim()
    if (!text || chat.sending) return
    setInput('')
    nearBottomRef.current = true
    void chat.send(text)
  }

  const handleAudio = (file: File): void => {
    if (chat.sending) return
    nearBottomRef.current = true
    void chat.sendAudio(file)
  }

  const firstName = user?.displayName?.trim().split(/\s+/)[0] ?? user?.email?.split('@')[0] ?? 'there'

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b border-white/[0.07] px-6 py-3.5">
        <div className="flex items-center gap-3">
          <img src={omiMark} alt="Omi" className="h-6 w-6" />
          <span className="font-semibold text-text-primary">Chat with Omi</span>
        </div>
        {chat.history.length > 0 && (
          <button
            onClick={chat.reset}
            title="Start new conversation"
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs text-text-quaternary hover:bg-white/[0.06] hover:text-text-tertiary"
          >
            <RotateCcw className="h-3 w-3" />
            New chat
          </button>
        )}
      </div>

      {/* Thread */}
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
      >
        {chat.history.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <img src={omiMark} alt="Omi" className="h-14 w-14 opacity-60" />
            <div>
              <p className="text-lg font-semibold text-text-secondary">Hi {firstName}!</p>
              <p className="mt-1 text-sm text-text-quaternary">
                Ask me anything — I know your memories, tasks, and screen context.
              </p>
            </div>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              {[
                'What did I work on today?',
                'Summarize my recent conversations',
                'What are my open tasks?',
              ].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => {
                    setInput(prompt)
                    nearBottomRef.current = true
                    void chat.send(prompt)
                  }}
                  className="rounded-xl border border-white/[0.08] bg-white/[0.04] px-3.5 py-2 text-xs text-text-tertiary hover:border-white/15 hover:bg-white/[0.07] hover:text-text-secondary"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mx-auto max-w-2xl">
            <ChatMessages messages={chat.history} sending={chat.sending} variant="main" />
          </div>
        )}
      </div>

      {/* Input bar */}
      <div className="shrink-0 border-t border-white/[0.07] px-4 py-3">
        <div className="mx-auto flex max-w-2xl items-center gap-2 rounded-2xl border border-white/10 bg-[color:var(--surface)] px-3 py-1.5">
          <input
            ref={fileRef}
            type="file"
            accept="audio/*"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleAudio(f)
              e.target.value = ''
            }}
          />
          <button
            disabled={chat.sending}
            onClick={() => fileRef.current?.click()}
            aria-label="Attach audio"
            title="Attach audio file"
            className="shrink-0 rounded-xl p-2 text-white/40 transition-colors hover:bg-white/[0.06] hover:text-white/80 disabled:opacity-40"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
            }}
            placeholder="Ask Omi…"
            className="flex-1 border-0 bg-transparent px-2 py-2 text-sm text-white placeholder:text-white/40 focus:outline-none focus:ring-0"
          />
          <button
            disabled={chat.sending || !input.trim()}
            onClick={send}
            aria-label="Send"
            className="shrink-0 rounded-xl bg-white/[0.06] p-2.5 text-white/80 transition-colors hover:bg-white/[0.12] hover:text-white disabled:opacity-50"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
