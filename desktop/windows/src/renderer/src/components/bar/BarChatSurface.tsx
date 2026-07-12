// The bar's expanded content — Mac-parity: a CHAT LIST (top row "Omi Chat",
// agent rows a later scaffold) that opens the conversation INLINE in the panel
// (like Mac's showAIConversation), with a back chevron to the list. The chat is
// a VIEWPORT over the main window's single engine: messages arrive as projected
// state (chatState) and sends go out through the bridge (onSubmit → the bar's
// window.omiBar.sendChat). This component owns NO chat engine.
import { useEffect, useLayoutEffect, useRef } from 'react'
import { ChatMessages } from '../chat/ChatMessages'
import { agentRowStatus, omiChatListStatus, type BarAgentRow } from './barDisplay'
import type { BarChatState } from '../../../../shared/types'

function ChevronRight(): React.JSX.Element {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M6 3.5 10.5 8 6 12.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

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

/** Leading status column shared by EVERY list row so all titles line up on one
 *  left margin (no ragged edge). The dot pulses when that row is active — Omi
 *  thinking/speaking, or an agent running a task — and is a calm neutral marker
 *  otherwise. Neutral/emerald only (no purple — brand rule). */
function RowStatusDot({ active }: { active: boolean }): React.JSX.Element {
  return (
    <span
      aria-hidden="true"
      className={`h-2 w-2 shrink-0 rounded-full ${
        active ? 'animate-pulse bg-emerald-400' : 'bg-neutral-600'
      }`}
    />
  )
}

export type BarChatSurfaceProps = {
  chat: BarChatState
  /** Connected coding agents to list under "Omi Chat". */
  agents: BarAgentRow[]
  view: 'list' | 'conversation'
  onOpenConversation: () => void
  onBack: () => void
  onClose: () => void
  draft: string
  setDraft: (s: string) => void
  /** Send the typed draft (typed turn — spoken=false). */
  onSubmit: (text: string) => void
  /** PTT gets first dibs on Space in the textarea (hold-to-talk). Returns true
   *  when it consumed the event (skip Enter/typing). */
  pttKeyDown: (e: React.KeyboardEvent) => boolean
  pttKeyUp: (e: React.KeyboardEvent) => boolean
  recording: boolean
  transcribing: boolean
  /** Max height (px, in this surface's own units) for the scrolling message
   *  list, so a long reply scrolls internally instead of overflowing the fixed
   *  bar window (C4). */
  maxListHeight: number
}

export function BarChatSurface(props: BarChatSurfaceProps): React.JSX.Element {
  const { chat, view } = props
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const followRef = useRef(true)

  // Focus the input whenever the conversation view opens.
  useEffect(() => {
    if (view === 'conversation') inputRef.current?.focus()
  }, [view])

  // Auto-grow the textarea to its content.
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [props.draft])

  // Keep the list pinned to the live edge while streaming, but disengage when the
  // reader scrolls up (re-engage on returning to the bottom).
  const hasHistory = chat.messages.length > 0
  useEffect(() => {
    if (view !== 'conversation') return
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
  }, [hasHistory, view])

  const submit = (): void => {
    const text = props.draft.trim()
    if (!text) return
    props.setDraft('')
    followRef.current = true
    props.onSubmit(text)
  }

  if (view === 'list') {
    return (
      <div className="flex flex-col gap-1 px-3 pb-3 pt-1">
        {/* Omi Chat — always present (INV-CHAT-1: the one shared thread). Its
            dot pulses while Omi is thinking/speaking, matching the agent rows so
            every title shares one left margin. */}
        <button
          type="button"
          onClick={props.onOpenConversation}
          className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-white/[0.06]"
        >
          <RowStatusDot active={chat.status !== 'idle'} />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-neutral-100">Omi Chat</div>
            <div className="truncate text-xs text-neutral-500">{omiChatListStatus(chat)}</div>
          </div>
          <span className="shrink-0 text-neutral-600 transition-colors group-hover:text-neutral-400">
            <ChevronRight />
          </span>
        </button>
        {/* Connected coding agents. A row opens the SAME inline conversation —
            agent progress streams into the shared thread (no separate store). */}
        {props.agents.map((agent) => (
          <button
            key={agent.id}
            type="button"
            onClick={props.onOpenConversation}
            className="group flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-white/[0.06]"
          >
            <RowStatusDot active={agent.working} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-neutral-100">{agent.displayName}</div>
              <div className="truncate text-xs text-neutral-500">{agentRowStatus(agent)}</div>
            </div>
            <span className="shrink-0 text-neutral-600 transition-colors group-hover:text-neutral-400">
              <ChevronRight />
            </span>
          </button>
        ))}
      </div>
    )
  }

  return (
    <div className="flex flex-col">
      <div className="flex items-center gap-1.5 px-2 pb-1 pt-1">
        <button
          type="button"
          onClick={props.onBack}
          aria-label="Back to list"
          className="flex h-6 w-6 items-center justify-center rounded-md text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-100"
        >
          <ChevronLeft />
        </button>
        <span className="text-sm font-medium text-neutral-200">Omi Chat</span>
        <button
          type="button"
          onClick={props.onClose}
          aria-label="Close"
          title="Close (same as the shortcut)"
          className="ml-auto flex h-5 w-5 items-center justify-center rounded-md text-xs leading-none text-neutral-500 transition-colors hover:bg-neutral-700/50 hover:text-neutral-200"
        >
          ✕
        </button>
      </div>

      {chat.messages.length > 0 ? (
        <div
          ref={scrollRef}
          style={{ maxHeight: props.maxListHeight }}
          className="min-h-0 overflow-y-auto px-3 pb-1 pr-1.5"
        >
          <div ref={messagesRef} className="space-y-2 py-1">
            <ChatMessages messages={chat.messages} sending={chat.sending} variant="overlay" />
          </div>
        </div>
      ) : (
        <div className="px-4 pb-2 pt-1 text-sm text-neutral-500">
          Ask Omi anything, or hold Space to talk.
        </div>
      )}

      <div className="flex items-end gap-2 px-3 pb-3 pt-2">
        <textarea
          ref={inputRef}
          rows={1}
          value={props.draft}
          onChange={(e) => props.setDraft(e.target.value)}
          onKeyDown={(e) => {
            // Push-to-talk claims Space first; otherwise Enter sends.
            if (props.pttKeyDown(e)) return
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          onKeyUp={(e) => props.pttKeyUp(e)}
          placeholder="Ask Omi…  ·  hold Space to talk"
          className="max-h-32 flex-1 resize-none rounded-xl bg-neutral-800/70 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:ring-1 focus:ring-neutral-500"
        />
        <button
          type="button"
          onClick={submit}
          disabled={chat.sending || props.recording || props.transcribing || !props.draft.trim()}
          className="rounded-xl bg-neutral-200 px-3 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  )
}
