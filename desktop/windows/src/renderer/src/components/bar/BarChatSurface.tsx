// The bar's expanded content — Mac-parity: a CHAT LIST (top row "Omi Chat",
// agent rows a later scaffold) that opens the conversation INLINE in the panel
// (like Mac's showAIConversation), with a back chevron to the list. The chat is
// a VIEWPORT over the main window's single engine: messages arrive as projected
// state (chatState) and sends go out through the bridge (onSubmit → the bar's
// window.omiBar.sendChat). This component owns NO chat engine.
import { useEffect, useLayoutEffect, useRef } from 'react'
import { ChatMessages } from '../chat/ChatMessages'
import { agentRowStatus, omiChatListStatus, type BarAgentRow } from './barDisplay'
import { displayLabel, displayTintToken, isFinished, type AgentPill } from './agentPills'
import { pillChipClasses } from './agentPillTranscript'
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

/** One floating-agent-pill row in the bar list: title + status chip + live
 *  one-liner, opening that run's OWN transcript on click. A finished pill offers
 *  Dismiss; an active pill offers Stop (when a canceller is wired). Both action
 *  buttons stopPropagation so they don't also open the pill. */
function PillRow({
  pill,
  onOpen,
  onDismiss,
  onStop
}: {
  pill: AgentPill
  onOpen: (id: string) => void
  onDismiss: (id: string) => void
  onStop?: (pill: AgentPill) => void
}): React.JSX.Element {
  const finished = isFinished(pill.displayStatus)
  return (
    <div className="group flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-white/[0.06]">
      <button
        type="button"
        onClick={() => onOpen(pill.id)}
        className="flex min-w-0 flex-1 items-center gap-3 text-left"
      >
        <RowStatusDot active={!finished} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-neutral-100">{pill.title}</span>
            <span
              className={`shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${pillChipClasses(
                displayTintToken(pill.displayStatus)
              )}`}
            >
              {displayLabel(pill.displayStatus)}
            </span>
          </div>
          <div className="truncate text-xs text-neutral-500">{pill.latestActivity || '…'}</div>
        </div>
      </button>
      {finished ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onDismiss(pill.id)
          }}
          aria-label="Dismiss agent"
          title="Dismiss"
          className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-500 transition-colors hover:bg-white/[0.06] hover:text-neutral-200"
        >
          Dismiss
        </button>
      ) : onStop ? (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onStop(pill)
          }}
          aria-label="Stop agent"
          title="Stop"
          className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-500 transition-colors hover:bg-white/[0.06] hover:text-neutral-200"
        >
          Stop
        </button>
      ) : null}
    </div>
  )
}

export type BarChatSurfaceProps = {
  chat: BarChatState
  /** Connected coding agents to list under "Omi Chat". */
  agents: BarAgentRow[]
  view: 'list' | 'conversation'
  /** Title for the open conversation's header — "Omi Chat" for the Omi row, the
   *  agent's displayName (e.g. "Claude Code") when an agent row opened it. */
  conversationTitle: string
  /** Open the inline conversation for a row: `null` = the Omi Chat thread, or the
   *  clicked agent row (so the parent can title the header + seed the draft). */
  onOpenConversation: (target: BarAgentRow | null) => void
  /** Live/recent floating agent pills — one per spawned kernel run (B3). They
   *  COMPLEMENT the connected-agent summon rows above; a pill row opens that
   *  run's OWN transcript (onOpenPill), never the shared Omi thread. */
  pills: AgentPill[]
  /** Open a pill's per-run transcript view (keyed by pill id). */
  onOpenPill: (id: string) => void
  /** Remove a finished pill from the bar. */
  onDismissPill: (id: string) => void
  /** Cancel a still-running pill's run. Absent ⇒ no stop control on the row. */
  onStopPill?: (pill: AgentPill) => void
  onBack: () => void
  onClose: () => void
  draft: string
  setDraft: React.Dispatch<React.SetStateAction<string>>
  /** Send the typed draft (typed turn — spoken=false). Resolves to the
   *  usage-limit notice when the send was REFUSED, else null. */
  onSubmit: (text: string) => Promise<string | null>
  /** The chat usage limit refused the last send — show the line inline, above the
   *  input (Mac drops the same copy into the bar as a local assistant message).
   *  The main window raises the shared upgrade modal in parallel. */
  limitNotice?: string | null
  /** A push-to-talk hold that FAILED while the panel is open (e.g. holding Space in
   *  the textarea): the friendly hint / error from usePushToTalk. Shown inline above
   *  the input, next to the limit notice. Collapsed-pill holds surface it below the
   *  pill instead (BarHintStrip). Self-clearing via the hook's own timers — null in
   *  the common success case, so nothing renders. */
  pttNotice?: string | null
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
  // Monotonic submit id — a refused send may only restore its text if it is still
  // the last thing the user asked (see submit()).
  const submitSeq = useRef(0)

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
    const seq = ++submitSeq.current
    void props.onSubmit(text).then((notice) => {
      // A REFUSED send never reaches the transcript, so clearing the input would
      // just eat the user's question behind the amber notice — they'd have to
      // retype it (Mac keeps the turn visible as a bubble instead). Put the text
      // back so they can upgrade and resend.
      //
      // Only the LATEST submit may restore. Nothing disables the textarea while a
      // check is in flight, so Enter can fire a second send while the first
      // cold-start probe still awaits; both then refuse, and a first-come restore
      // would drop its stale text into the input the second submit just cleared —
      // the newer question would be the one lost. Belt-and-braces, never clobber
      // text the user typed after the clear.
      if (!notice || seq !== submitSeq.current) return
      props.setDraft((current) => (current.trim() ? current : text))
    })
  }

  if (view === 'list') {
    return (
      // key={view} remounts on every list⇄conversation switch so bar-view-enter
      // replays — the swap morphs in place instead of popping a new sheet.
      <div key="list" className="bar-view-enter flex flex-col gap-1 px-3 pb-3 pt-1">
        {/* Omi Chat — always present (INV-CHAT-1: the one shared thread). Its
            dot pulses while Omi is thinking/speaking, matching the agent rows so
            every title shares one left margin. */}
        <button
          type="button"
          onClick={() => props.onOpenConversation(null)}
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
            onClick={() => props.onOpenConversation(agent)}
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
        {/* Live/recent spawned agent runs (B3). Distinct from the summon rows
            above: each opens its OWN run transcript, not the shared thread. A
            thin rule sets them apart only when both sets are present. */}
        {props.pills.length > 0 ? (
          <div
            className={
              props.agents.length > 0
                ? 'mt-1 flex flex-col gap-1 border-t border-white/[0.06] pt-1'
                : 'flex flex-col gap-1'
            }
          >
            {props.pills.map((pill) => (
              <PillRow
                key={pill.id}
                pill={pill}
                onOpen={props.onOpenPill}
                onDismiss={props.onDismissPill}
                onStop={props.onStopPill}
              />
            ))}
          </div>
        ) : null}
      </div>
    )
  }

  return (
    // NO enter-animation class (unlike the list's bar-view-enter). The
    // conversation renders opaque at its final seated layout from frame 1; the
    // overflow:clip surface reveals it top-down as the box grows (see bar.css).
    // Any opacity/transform here reintroduces the black-flash / slide-from-above.
    <div key="conversation" className="flex flex-col">
      <div className="flex items-center gap-1.5 px-2 pb-1 pt-1">
        <button
          type="button"
          onClick={props.onBack}
          aria-label="Back to list"
          className="flex h-6 w-6 items-center justify-center rounded-md text-neutral-400 transition-colors hover:bg-white/[0.06] hover:text-neutral-100"
        >
          <ChevronLeft />
        </button>
        <span className="text-sm font-medium text-neutral-200">{props.conversationTitle}</span>
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

      {props.pttNotice ? (
        <div role="status" className="px-4 pb-1 pt-1 text-xs leading-relaxed text-amber-300/90">
          {props.pttNotice}
        </div>
      ) : null}

      {props.limitNotice ? (
        <div role="status" className="px-4 pb-1 pt-1 text-xs leading-relaxed text-amber-300/90">
          {props.limitNotice}
        </div>
      ) : null}

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
