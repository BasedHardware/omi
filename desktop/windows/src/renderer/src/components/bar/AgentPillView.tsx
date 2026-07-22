// The bar's per-pill transcript view (B3) — a dedicated read-only surface for a
// single spawned agent RUN, keyed by pill id. Faithful port of macOS'
// AgentMainChatView (upstream FloatingControlBar/FloatingControlBarView.swift):
// its messages are the pill's OWN client-synthesized transcript (query + evolving
// assistant text), NOT the shared Omi thread (INV-CHAT-1). This is the fix — a
// click on a spawned-agent pill lands here, on that run's own conversation, never
// the shared chat.
import { useEffect, useLayoutEffect, useRef } from 'react'
import { ChatMessages } from '../chat/ChatMessages'
import { displayLabel, displayTintToken, isFinished, type AgentPill } from './agentPills'
import { pillChipClasses } from './agentPillTranscript'
import type { ChatMsg } from '../../hooks/useChat'

function ChevronLeft(): React.JSX.Element {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M10 3.5 5.5 8 10 12.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export type AgentPillViewProps = {
  pill: AgentPill
  /** The pill's synthesized transcript (from useAgentPills.transcriptFor). */
  transcript: { messages: ChatMsg[]; sending: boolean }
  onBack: () => void
  onClose: () => void
  /** Remove this pill from the bar (offered once the run is finished). */
  onDismiss: (id: string) => void
  /** Cancel a still-running run (cancel_agent_run). Absent ⇒ no stop control. */
  onStop?: (pill: AgentPill) => void
  /** Max height (px, this surface's units) for the internally-scrolling list. */
  maxListHeight: number
}

export function AgentPillView(props: AgentPillViewProps): React.JSX.Element {
  const { pill, transcript } = props
  const finished = isFinished(pill.displayStatus)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const followRef = useRef(true)

  // Focus the surface so Esc/back keys land here on open.
  useEffect(() => {
    scrollRef.current?.focus?.()
  }, [])

  // Keep the list pinned to the live edge while the assistant text streams, but
  // disengage when the reader scrolls up (re-engage at the bottom). Mirrors the
  // Omi conversation's follow logic in BarChatSurface.
  useLayoutEffect(() => {
    const el = scrollRef.current
    const content = messagesRef.current
    if (!el || !content) return
    const pin = (): void => {
      if (followRef.current) el.scrollTop = el.scrollHeight
    }
    pin()
    const ro = new ResizeObserver(pin)
    ro.observe(content)
    const onWheel = (e: WheelEvent): void => {
      if (e.deltaY < 0 && el.scrollHeight > el.clientHeight + 8) followRef.current = false
    }
    const onScroll = (): void => {
      if (el.scrollHeight - el.scrollTop - el.clientHeight <= 8) followRef.current = true
    }
    el.addEventListener('wheel', onWheel, { passive: true })
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      ro.disconnect()
      el.removeEventListener('wheel', onWheel)
      el.removeEventListener('scroll', onScroll)
    }
  }, [])

  return (
    <div key={`agent-${pill.id}`} className="flex flex-col">
      <div className="flex items-center gap-1.5 px-2 pb-1 pt-1">
        <button
          type="button"
          onClick={props.onBack}
          aria-label="Back to list"
          className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-100"
        >
          <ChevronLeft />
        </button>
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-neutral-200">
          {pill.title}
        </span>
        <span
          className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${pillChipClasses(
            displayTintToken(pill.displayStatus)
          )}`}
        >
          {displayLabel(pill.displayStatus)}
        </span>
        {finished ? (
          <button
            type="button"
            onClick={() => props.onDismiss(pill.id)}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-100"
          >
            Dismiss
          </button>
        ) : props.onStop ? (
          <button
            type="button"
            onClick={() => props.onStop?.(pill)}
            className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-100"
          >
            Stop
          </button>
        ) : null}
        <button
          type="button"
          onClick={props.onClose}
          aria-label="Close"
          className="ml-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-xs leading-none text-neutral-500 transition-colors hover:bg-neutral-700/50 hover:text-neutral-200"
        >
          ✕
        </button>
      </div>

      <div
        ref={scrollRef}
        tabIndex={-1}
        style={{ maxHeight: props.maxListHeight }}
        className="min-h-0 overflow-y-auto px-3 pb-2 pr-1.5 outline-none"
      >
        <div ref={messagesRef} className="space-y-2 py-1">
          <ChatMessages
            messages={transcript.messages}
            sending={transcript.sending}
            variant="overlay"
          />
        </div>
      </div>
    </div>
  )
}
