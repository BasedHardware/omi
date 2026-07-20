import { useEffect, useRef, useState } from 'react'
import { ArrowUp } from 'lucide-react'
import type { User } from 'firebase/auth'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { useAppState } from '../state/appState'
import { ChatMessages } from '../components/chat/ChatMessages'
import { QuickTaskWidget } from '../components/home/QuickTaskWidget'
import { maybeBuildLocalGraph } from '../lib/kgSynthesis'
import { maybeStartInsightEngine } from '../lib/insightEngine'
import { maybeStartRetentionSweep } from '../lib/retentionSweep'
import { maybeStartScreenSynthesis } from '../lib/screenSynthesis'

const SUGGESTIONS = [
  'What should I focus on today?',
  'What matters most on my screen?',
  'Break my goal into the next 3 steps.'
]

function firstName(user: User | null): string {
  const displayName = user?.displayName?.trim().split(/\s+/)[0]
  return displayName || user?.email?.split('@')[0] || 'there'
}

export function Home(): React.JSX.Element {
  const { chat } = useAppState()
  const [user, setUser] = useState<User | null>(auth.currentUser)
  const [input, setInput] = useState('')
  const messageListRef = useRef<HTMLDivElement>(null)

  useEffect(() => onAuthStateChanged(auth, setUser), [])

  useEffect(() => {
    const timer = window.setTimeout(() => void maybeBuildLocalGraph(), 1800)
    maybeStartScreenSynthesis()
    maybeStartInsightEngine()
    maybeStartRetentionSweep()
    return () => window.clearTimeout(timer)
  }, [])

  useEffect(() => {
    const element = messageListRef.current
    if (!element) return
    element.scrollTop = element.scrollHeight
  }, [chat.history, chat.sending])

  const send = (value: string): void => {
    if (!value.trim() || chat.sending) return
    setInput('')
    void chat.send(value)
  }

  const hasHistory = chat.history.length > 0

  return (
    <div className="relative flex h-full min-h-0 overflow-hidden bg-[#090909] text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_50%_35%,rgba(255,255,255,0.055),transparent_52%)]" />
      <div className="relative mx-auto flex min-h-0 w-full max-w-6xl flex-1 flex-col px-6 pb-8 pt-16 lg:px-12">
        <section className="flex min-h-0 flex-1 flex-col items-center">
          {hasHistory ? (
            <div
              ref={messageListRef}
              className="w-full max-w-3xl flex-1 overflow-y-auto pb-8 pr-1"
              aria-label="Conversation"
            >
              <div className="flex min-h-full flex-col justify-end gap-2">
                <ChatMessages messages={chat.history} sending={chat.sending} variant="main" />
              </div>
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center pb-16 text-center">
              <p className="select-none font-display text-6xl font-semibold lowercase tracking-tight text-white sm:text-7xl">
                omi.
              </p>
              <h1 className="mt-6 text-xl font-medium text-white/85">Hi, {firstName(user)}</h1>
              <p className="mt-2 max-w-sm text-sm leading-relaxed text-white/45">
                Ask about your work, conversations, and what needs your attention.
              </p>
            </div>
          )}
        </section>

        <section className="mx-auto w-full max-w-4xl shrink-0">
          <form
            onSubmit={(event) => {
              event.preventDefault()
              send(input)
            }}
            className="flex items-end gap-2 rounded-[22px] border border-white/10 bg-white/[0.055] p-2 shadow-2xl shadow-black/30"
          >
            <textarea
              rows={1}
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  send(input)
                }
              }}
              placeholder="Ask Omi…"
              className="max-h-32 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-sm leading-6 text-white placeholder:text-white/35 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!input.trim() || chat.sending}
              aria-label="Send"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-30"
            >
              <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
            </button>
          </form>

          <div className="mt-3 flex flex-wrap justify-center gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                disabled={chat.sending}
                onClick={() => send(suggestion)}
                className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs text-white/55 transition-colors hover:bg-white/[0.08] hover:text-white disabled:opacity-40"
              >
                {suggestion}
              </button>
            ))}
          </div>

          <div className="mx-auto mt-4 max-w-2xl">
            <QuickTaskWidget />
          </div>
        </section>
      </div>
    </div>
  )
}
