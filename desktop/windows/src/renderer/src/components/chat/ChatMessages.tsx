import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Copy, Check } from 'lucide-react'
import type { ChatMsg, ChatCitation } from '../../hooks/useChat'
import { Markdown } from '../Markdown'

// Smooth text reveal, decoupled from SSE chunk sizes so a reply streams in evenly
// instead of landing in bulky jumps. Rendered as markdown either way.
const REVEAL_MS = 16
const REVEAL_MIN_CHARS = 2

// Snap a code-unit index to a safe boundary so we never slice inside a
// surrogate pair (emoji above U+FFFF). If the character just before `n` is a
// high surrogate, advance by 1 to include its paired low surrogate.
function snapBoundary(text: string, n: number): number {
  if (n <= 0 || n >= text.length) return n
  const code = text.charCodeAt(n - 1)
  return code >= 0xd800 && code <= 0xdbff ? n + 1 : n
}

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
  return <Markdown text={text.slice(0, snapBoundary(text, shown))} />
}

/** Animated 3-dot typing indicator — mirrors macOS TypingIndicator component */
function TypingIndicator(): React.JSX.Element {
  return (
    <span className="flex items-center gap-[3px] py-0.5">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="typing-dot inline-block h-[5px] w-[5px] rounded-full bg-white/50"
        />
      ))}
    </span>
  )
}

// macOS-exact bubble spec:
//   User:      bg #43389F (OmiColors.userBubble), corner 20pt continuous, sharp bottom-right
//   Assistant: bg #252525 @ 95% opacity (OmiColors.backgroundTertiary), sharp bottom-left
//   Padding:   14px horiz / 10px vert (matches .padding(.horizontal, 14).padding(.vertical, 10))
//   Gap:       18pt between messages (LazyVStack spacing: 18)
const BUBBLE: Record<'main' | 'overlay', { user: string; assistant: string }> = {
  main: {
    user:
      'bg-[#43389F] ml-auto max-w-[85%] rounded-[20px] rounded-br-[6px] px-[14px] py-[10px] text-sm leading-snug text-white select-text',
    assistant:
      'bg-[#252525]/95 mr-auto max-w-[85%] rounded-[20px] rounded-bl-[6px] px-[14px] py-[10px] text-sm leading-snug text-white/85 select-text'
  },
  overlay: {
    user: 'bubble-in ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-neutral-700/70 px-3.5 py-2 text-sm leading-snug text-neutral-100 select-text',
    assistant:
      'bubble-in mr-auto w-fit max-w-[80%] rounded-2xl rounded-bl-md bg-neutral-800/60 px-3.5 py-2 text-sm leading-snug text-neutral-100 select-text'
  }
}

// Message truncation at 500 chars — matches macOS behavior
const TRUNCATE_AT = 500

function TruncatedContent({ text }: { text: string }): React.JSX.Element {
  const [expanded, setExpanded] = useState(false)
  if (text.length <= TRUNCATE_AT || expanded) {
    return <Markdown text={text} />
  }
  return (
    <>
      <Markdown text={text.slice(0, TRUNCATE_AT) + '…'} />
      <button
        onClick={() => setExpanded(true)}
        className="mt-1 text-[11px] text-white/40 underline-offset-2 hover:text-white/70 hover:underline"
      >
        Show more
      </button>
    </>
  )
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

/** Icon-only copy button — matches macOS (doc.on.doc icon, no text label) */
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
      className="mt-1 self-start rounded-md p-1.5 text-white/30 transition-colors hover:bg-white/[0.06] hover:text-white/70"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-green-400" strokeWidth={2.5} />
      ) : (
        <Copy className="h-3.5 w-3.5" strokeWidth={2} />
      )}
    </button>
  )
}

/**
 * Shared chat message list used by both the main window (Home) and the overlay.
 * Main variant matches macOS exactly: purple user bubbles, dark-grey assistant bubbles,
 * 20pt continuous corners, 14/10px padding, 18px gap, icon-only copy, typing dots.
 */
export function ChatMessages({
  messages,
  sending,
  variant,
  suggestions,
  onSuggest
}: {
  messages: ChatMsg[]
  sending: boolean
  variant: 'main' | 'overlay'
  suggestions?: string[]
  onSuggest?: (text: string) => void
}): React.JSX.Element {
  const cls = BUBBLE[variant]
  // 18px gap between messages matches macOS LazyVStack(spacing: 18)
  const gapClass = variant === 'main' ? 'flex flex-col gap-[18px]' : 'flex flex-col gap-3'
  return (
    <div className={gapClass}>
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1
        const isStreaming = isLast && sending && m.role === 'assistant'
        return (
          <div key={m.id ?? i} className="group flex flex-col">
            <div className={m.role === 'user' ? cls.user : cls.assistant}>
              {m.role === 'assistant' ? (
                m.content ? (
                  variant === 'main' ? (
                    isStreaming ? (
                      <RevealMarkdown text={m.content} startRevealed={false} />
                    ) : (
                      <TruncatedContent text={m.content} />
                    )
                  ) : (
                    <RevealMarkdown text={m.content} startRevealed={!(isLast && sending)} />
                  )
                ) : sending ? (
                  <TypingIndicator />
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
            {/* Suggestion chips — only on the last AI message when not streaming (main variant) */}
            {isLast && m.role === 'assistant' && !sending && variant === 'main' && suggestions && suggestions.length > 0 && onSuggest && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => onSuggest(s)}
                    className="rounded-2xl border border-white/[0.10] bg-white/[0.04] px-3 py-1.5 text-xs text-white/55 transition-colors hover:border-white/20 hover:bg-white/[0.08] hover:text-white/80"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
