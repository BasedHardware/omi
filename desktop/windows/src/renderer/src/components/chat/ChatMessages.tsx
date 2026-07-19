import { useState } from 'react'
import { Check, Copy } from 'lucide-react'
import type { ChatMsg } from '../../hooks/useChat'
import { RevealMarkdown } from './RevealMarkdown'
import { ChatAttachmentStrip } from './ChatAttachmentStrip'
import { OmiThinkingSpinner } from './OmiThinkingSpinner'

const BUBBLE: Record<'main' | 'overlay', { user: string; assistant: string }> = {
  main: {
    user: 'bubble-in ml-auto w-fit max-w-[75%] rounded-[18px] rounded-br-[6px] bg-[color:var(--accent)] px-4 py-2.5 text-sm leading-snug text-[color:var(--accent-contrast)]',
    assistant:
      'bubble-in mr-auto w-fit max-w-[85%] rounded-2xl rounded-bl-md bg-white/[0.06] px-4 py-2.5 text-sm leading-relaxed text-white/85'
  },
  // Same bubble design as the main window (Home) — shape, padding, asymmetric
  // corner, the white-accent user bubble, and the bubble-in entrance — sized
  // down slightly for the floating bar's dark acrylic panel.
  overlay: {
    user: 'bubble-in ml-auto w-fit max-w-[80%] rounded-2xl rounded-br-md bg-[color:var(--accent)] px-3.5 py-2 text-sm leading-snug text-[color:var(--accent-contrast)]',
    assistant:
      'bubble-in mr-auto w-fit max-w-[80%] rounded-2xl rounded-bl-md bg-neutral-800/60 px-3.5 py-2 text-sm leading-snug text-neutral-100'
  }
}

/**
 * Hover-revealed "copy this message" affordance, mirroring macOS (ChatBubble's
 * always-on Copy in the main chat and AIResponseView's hover Copy on the floating
 * bar reply). Anchored just outside the bubble on the side facing the thread's
 * centre, so it never covers the text or clips at the panel edge, and it reserves
 * no layout space (absolute) — the resting thread looks exactly as before. Each
 * button owns its own brief check-tick so bubbles flip independently.
 */
function CopyMessageButton({
  text,
  role,
  compact
}: {
  text: string
  role: 'user' | 'assistant'
  compact: boolean
}): React.JSX.Element {
  const [copied, setCopied] = useState(false)
  const copy = (): void => {
    void navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 1400)
      })
      .catch(() => {
        /* clipboard denied — nothing to fall back to */
      })
  }
  // Sit flush against the bubble (no margin gap) so the hover region stays
  // contiguous: `right-full`/`left-full` abut the button's edge exactly against
  // the bubble box. A margin here would open a dead gap where `group/msg:hover`
  // drops — the button would flip back to pointer-events-none mid-traverse and
  // vanish before the pointer could land on it.
  const side = role === 'user' ? 'right-full' : 'left-full'
  const glyph = compact ? 'h-3 w-3' : 'h-3.5 w-3.5'
  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? 'Copied' : 'Copy message'}
      title="Copy message"
      className={`focus-ring pointer-events-none absolute bottom-1 ${side} ${
        compact ? 'h-5 w-5' : 'h-6 w-6'
      } flex items-center justify-center rounded-md text-white/50 opacity-0 transition-[opacity,color,background-color] hover:bg-white/10 hover:text-white/90 focus-visible:opacity-100 group-hover/msg:pointer-events-auto group-hover/msg:opacity-100`}
    >
      {copied ? (
        <Check className={glyph} strokeWidth={2.25} />
      ) : (
        <Copy className={glyph} strokeWidth={2} />
      )}
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
  const compact = variant === 'overlay'
  return (
    <>
      {messages.map((m, i) => {
        const isLast = i === messages.length - 1
        // Bar chat (overlay): while Omi's reply is still pending — the last
        // assistant turn exists as an empty placeholder — show a standalone
        // spinning Omi mark instead of a bubble of dots. A distinct key means the
        // real bubble mounts fresh (bubble-in pop-in) the moment content lands and
        // this loader is unmounted. The main window keeps its own indicators.
        if (variant === 'overlay' && isLast && sending && m.role === 'assistant' && !m.content) {
          return <OmiThinkingSpinner key={`omi-thinking-${m.id ?? i}`} />
        }
        // Never offer copy on the reply that is still streaming in (or on an
        // empty placeholder) — only once there is settled text to copy.
        const streaming = isLast && sending && m.role === 'assistant'
        const canCopy = !streaming && m.content.trim().length > 0
        const bubbleClass = `group/msg relative ${m.role === 'user' ? cls.user : cls.assistant}`
        const bubbleChildren = (
          <>
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
            {canCopy ? (
              <CopyMessageButton text={m.content} role={m.role} compact={compact} />
            ) : null}
          </>
        )

        // User attachments render as a card strip ABOVE the bubble, trailing-
        // aligned (Mac's ChatBubble). A files-only message (attachments but no
        // text) shows just the strip — no empty bubble. Messages with no
        // attachments emit exactly the single bubble div as before.
        if (m.role === 'user' && m.attachments?.length) {
          const filesOnly = !m.content.trim()
          return (
            <div key={m.id ?? i} className="flex flex-col items-end gap-1.5">
              <ChatAttachmentStrip attachments={m.attachments} compact={compact} align="end" />
              {filesOnly ? null : <div className={bubbleClass}>{bubbleChildren}</div>}
            </div>
          )
        }
        return (
          <div key={m.id ?? i} className={bubbleClass}>
            {bubbleChildren}
          </div>
        )
      })}
    </>
  )
}
