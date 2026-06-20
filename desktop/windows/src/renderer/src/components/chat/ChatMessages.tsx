import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Check } from 'lucide-react'
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
  const cardClass =
    'flex w-full items-center gap-2.5 rounded-lg border border-white/[0.12] bg-white/[0.06] px-3 py-2.5 text-left transition-colors hover:border-white/20 hover:bg-white/[0.10]'
  return (
    <div className={`mt-2.5 space-y-1.5 ${variant === 'overlay' ? 'max-w-[80%]' : 'max-w-[85%]'}`}>
      <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest text-white/40">
        <span>📎</span>
        <span>Sources</span>
      </p>
      {citations.map((c) => {
        const emoji = c.emoji ? (
          <span className="text-base leading-none">{c.emoji}</span>
        ) : (
          <span className="text-sm leading-none text-white/30">💬</span>
        )
        const body = (
          <>
            {emoji}
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-white/85">{c.title}</p>
              {c.preview && (
                <p className="mt-0.5 line-clamp-1 text-[10px] text-white/40">{c.preview}</p>
              )}
              {c.created_at && (
                <p className="mt-0.5 text-[10px] text-white/30">
                  {new Date(c.created_at).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })}
                </p>
              )}
            </div>
            <span className="shrink-0 rounded border border-white/10 bg-white/[0.06] px-1.5 py-0.5 text-[10px] text-white/40">
              Open
            </span>
          </>
        )
        return variant === 'overlay' ? (
          // In the overlay, <Link> would navigate inside the overlay window (broken).
          // Instead, call openMainRoute() which hides the overlay and navigates the main window.
          <button
            key={c.id}
            onClick={() => window.omiOverlay?.openMainRoute(`/conversations/${c.id}`)}
            className={cardClass}
          >
            {body}
          </button>
        ) : (
          <Link key={c.id} to={`/conversations/${c.id}`} className={cardClass}>
            {body}
          </Link>
        )
      })}
    </div>
  )
}

function CopyMsgButton({ text }: { text: string }): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 1500)
        })
      }}
      aria-label="Copy message"
      title="Copy message"
      className="mt-1.5 flex items-center gap-1 self-start rounded-md border border-white/[0.10] bg-white/[0.04] px-2 py-1 text-[11px] text-white/45 transition-all hover:border-white/20 hover:bg-white/[0.09] hover:text-white/80"
    >
      {copied ? (
        <Check className="h-3 w-3 text-green-400" strokeWidth={2.5} />
      ) : (
        <Copy className="h-3 w-3" strokeWidth={2} />
      )}
      {copied ? 'Copied' : 'Copy'}
    </button>
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
        const isStreaming = isLast && sending && m.role === 'assistant'
        return (
          <div key={m.id ?? i} className="group flex flex-col">
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
            {m.role === 'assistant' && m.content && !isStreaming && (
              <CopyMsgButton text={m.content} />
            )}
            {m.role === 'assistant' && m.citations && m.citations.length > 0 && (
              <CitationCards citations={m.citations} variant={variant} />
            )}
          </div>
        )
      })}
    </>
  )
}
