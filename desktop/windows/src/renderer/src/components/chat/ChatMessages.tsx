import type { ChatMsg } from '../../hooks/useChat'
import { RevealMarkdown } from './RevealMarkdown'

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
