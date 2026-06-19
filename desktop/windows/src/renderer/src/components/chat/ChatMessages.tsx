import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ChatMsg, ChatCitation } from '../../hooks/useChat'
import { Markdown } from '../Markdown'

// Smooth text reveal, decoupled from SSE chunk sizes so a reply streams in evenly
// instead of landing in bulky jumps. Rendered as markdown either way.
const REVEAL_MS = 16
const REVEAL_MIN_CHARS = 2

function RevealMarkdown({
  text,
  startRevealed
}: {
  text: string
  startRevealed: boolean
}): React.JSX.Element {
  const [shown, setShown] = useState(startRevealed ? text.length : 0)
  const targetRef = useRef(text)
  targetRef.current = text
  useEffect(() => {
    const id = setInterval(() => {
      setShown((prev) => {
        const t = targetRef.current.length
        if (prev >= t) return prev
        const step = Math.max(REVEAL_MIN_CHARS, Math.ceil((t - prev) / 24))
        return Math.min(t, prev + step)
      })
    }, REVEAL_MS)
    return () => clearInterval(id)
  }, [])
  return <Markdown text={text.slice(0, shown)} />
}

const BUBBLE: Record<'main' | 'overlay', { user: string; assistant: string }> = {
  main: {
    user: 'glass ml-auto max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed text-white select-text',
    assistant:
      'glass-subtle mr-auto max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed text-white/75 select-text'
  },
  // Same bubble design as the main window (Home) — shape, padding, asymmetric
  // corner, and the bubble-in entrance animation — but keeping the overlay's
  // neutral colors (the floating bar's dark acrylic, not Home's accent/white).
  overlay: {
    user: 'bubble-in ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-neutral-700/70 px-3.5 py-2 text-sm leading-snug text-neutral-100 select-text',
    assistant:
      'bubble-in mr-auto w-fit max-w-[80%] rounded-2xl rounded-bl-md bg-neutral-800/60 px-3.5 py-2 text-sm leading-snug text-neutral-100 select-text'
  }
}

function CitationCards({
  citations,
  variant
}: {
  citations: ChatCitation[]
  variant: 'main' | 'overlay'
}): React.JSX.Element {
  return (
    <div className={`mt-2 space-y-1.5 ${variant === 'overlay' ? 'max-w-[80%]' : 'max-w-[85%]'}`}>
      <p className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wide text-white/35">
        <span>Sources</span>
      </p>
      {citations.map((c) => (
        <Link
          key={c.id}
          to={`/conversations/${c.id}`}
          className="flex items-center gap-2.5 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-left transition-colors hover:bg-white/[0.08]"
        >
          {c.emoji && <span className="text-base leading-none">{c.emoji}</span>}
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-medium leading-none text-white/80">{c.title}</p>
          </div>
          <span className="shrink-0 text-[10px] text-white/25">›</span>
        </Link>
      ))}
    </div>
  )
}

/**
 * Shared chat message list used by both the main window (Home) and the overlay.
 * Owns bubble styling (per `variant`), markdown rendering, and the smooth reveal
 * of the live assistant message. Callers provide their own scroll container.
 */
export function ChatMessages({
  messages,
  sending,
  variant
}: {
  messages: ChatMsg[]
  sending: boolean
  variant: 'main' | 'overlay'
}): React.JSX.Element {
  const cls = BUBBLE[variant]
  return (
    <>
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1
        return (
          <div key={m.id ?? i} className="flex flex-col">
            <div className={m.role === 'user' ? cls.user : cls.assistant}>
              {m.role === 'assistant' ? (
                m.content ? (
                  <RevealMarkdown text={m.content} startRevealed={!(isLast && sending)} />
                ) : sending ? (
                  '…'
                ) : (
                  ''
                )
              ) : (
                <div className="whitespace-pre-wrap">{m.content}</div>
              )}
            </div>
            {m.role === 'assistant' && m.citations && m.citations.length > 0 && (
              <CitationCards citations={m.citations} variant={variant} />
            )}
          </div>
        )
      })}
    </>
  )
}
