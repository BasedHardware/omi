import { useEffect, useRef, useState } from 'react'
import type { ChatMsg } from '../../hooks/useChat'
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
    user: 'glass ml-auto max-w-[85%] rounded-2xl rounded-br-md px-4 py-3 text-sm leading-relaxed text-white',
    assistant:
      'glass-subtle mr-auto max-w-[85%] rounded-2xl rounded-bl-md px-4 py-3 text-sm leading-relaxed text-white/75'
  },
  // Same bubble design as the main window (Home) — shape, padding, asymmetric
  // corner, and the bubble-in entrance animation — but keeping the overlay's
  // neutral colors (the floating bar's dark acrylic, not Home's accent/white).
  overlay: {
    user: 'bubble-in ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-neutral-700/70 px-3.5 py-2 text-sm leading-snug text-neutral-100',
    assistant:
      'bubble-in mr-auto w-fit max-w-[80%] rounded-2xl rounded-bl-md bg-neutral-800/60 px-3.5 py-2 text-sm leading-snug text-neutral-100'
  }
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
          <div key={m.id ?? i} className={m.role === 'user' ? cls.user : cls.assistant}>
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
        )
      })}
    </>
  )
}
