// The bar's expanded content — Mac-parity. The hub (list view) hosts an inline
// "Ask Omi anything" input (Mac's AskAIInputView / .mainInput) plus the connected
// coding-agent rows; a send flips to the conversation INLINE in the panel (Mac's
// showAIConversation / .mainResponse), with a back chevron to the hub. The chat is
// a VIEWPORT over the main window's single engine: messages arrive as projected
// state (chatState) and sends go out through the bridge (onSubmit → the bar's
// window.omiBar.sendChat). This component owns NO chat engine.
import { memo, useCallback, useEffect, useLayoutEffect, useRef } from 'react'
import { ChatMessages } from '../chat/ChatMessages'
import { displayLabel, displayTintToken, isFinished, type AgentPill } from './agentPills'
import { pillChipClasses } from './agentPillTranscript'
import type { BarChatState } from '../../../../shared/types'

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

function ChatBubbleIcon(): React.JSX.Element {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d="M13.5 7.3c0 2.15-2.35 3.9-5.25 3.9-.62 0-1.22-.08-1.77-.23L3.3 12.2l.72-2.02A3.5 3.5 0 0 1 3 7.3c0-2.15 2.35-3.9 5.25-3.9S13.5 5.15 13.5 7.3Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/** The bar hub's static "Omi Chat" entry (Mac FloatingControlBarView's
 *  notchOmiChatRow) — the assistant's own chat entry. A plain navigable ROW that
 *  opens the shared Omi conversation WITHOUT sending anything (pure view flip, no
 *  draft seeding). Sits between the Ask-Omi composer and the run pills. Styled
 *  deliberately as a list row (leading chat glyph + trailing chevron), NOT like the
 *  input above it: an input-styled entry whose single click navigated was the
 *  reported #209 bug. Neutral only (no purple — brand rule). */
function OmiChatRow({ onOpen }: { onOpen: () => void }): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-white/[0.06]"
    >
      <span
        aria-hidden="true"
        className="flex h-5 w-5 shrink-0 items-center justify-center text-neutral-400"
      >
        <ChatBubbleIcon />
      </span>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-neutral-100">Omi Chat</span>
      <span
        aria-hidden="true"
        className="shrink-0 text-neutral-600 transition-colors group-hover:text-neutral-300"
      >
        <ChevronRight />
      </span>
    </button>
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
 *  Dismiss; an active pill offers Stop (when a canceller is wired). The open,
 *  Dismiss, and Stop targets are sibling buttons (the row itself has no click
 *  handler), so an action click never also opens the pill. */
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
          onClick={() => onDismiss(pill.id)}
          aria-label="Dismiss agent"
          title="Dismiss"
          className="shrink-0 rounded-md px-2 py-1 text-xs font-medium text-neutral-500 transition-colors hover:bg-white/[0.06] hover:text-neutral-200"
        >
          Dismiss
        </button>
      ) : onStop ? (
        <button
          type="button"
          onClick={() => onStop(pill)}
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

type ChatComposerProps = {
  inputRef: React.RefObject<HTMLTextAreaElement | null>
  draft: string
  setDraft: React.Dispatch<React.SetStateAction<string>>
  onKeyDown: (e: React.KeyboardEvent) => void
  onKeyUp: (e: React.KeyboardEvent) => void
  onSubmit: () => void
  sendDisabled: boolean
  placeholder: string
  /** Wrapper padding differs by surface (tight in the hub, roomier in the
   *  conversation); the textarea + Send button are identical. */
  className: string
}

/** The shared textarea + Send composer used by BOTH the hub and the conversation
 *  (Mac's one AskAIInputView). memo'd on a narrow prop surface — draft +
 *  send-state + the STABLE handlers — so it re-renders on keystrokes and
 *  send-state changes only, never on the projected-chat ticks that re-render the
 *  parent to grow the message list. (The handlers stay stable via the parent's
 *  latest-ref, so a chat tick doesn't churn their identity.) */
const ChatComposer = memo(function ChatComposer({
  inputRef,
  draft,
  setDraft,
  onKeyDown,
  onKeyUp,
  onSubmit,
  sendDisabled,
  placeholder,
  className
}: ChatComposerProps): React.JSX.Element {
  return (
    <div className={className}>
      <textarea
        ref={inputRef}
        rows={1}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onKeyUp={onKeyUp}
        placeholder={placeholder}
        className="max-h-32 flex-1 resize-none rounded-xl bg-neutral-800/70 px-3 py-2 text-sm text-neutral-100 placeholder-neutral-500 outline-none focus:ring-1 focus:ring-neutral-500"
      />
      <button
        type="button"
        onClick={onSubmit}
        disabled={sendDisabled}
        className="rounded-xl bg-neutral-200 px-3 py-2 text-sm font-medium text-neutral-900 disabled:opacity-40"
      >
        Send
      </button>
    </div>
  )
})

export type BarChatSurfaceProps = {
  chat: BarChatState
  view: 'list' | 'conversation'
  /** Whether the bar is expanded (the chat surface is visible). Drives focus-on-
   *  appear: this component stays mounted while the bar is a collapsed pill, so the
   *  hub input is only focused once the surface actually opens. */
  expanded: boolean
  /** Title for the open conversation's header. The bar's chat is always the one
   *  shared Omi thread (INV-CHAT-1), so this is "Omi Chat"; kept a prop so the
   *  header stays data-driven rather than hardcoded. */
  conversationTitle: string
  /** Open the inline Omi Chat conversation. The ONLY transition from the hub's
   *  ask state (Mac's .mainInput) to the response state (.mainResponse), driven by
   *  a SEND (Enter or the Send button). */
  onOpenConversation: () => void
  /** Live/recent floating agent pills — one per spawned kernel run (B3). Each pill
   *  row opens that run's OWN transcript (onOpenPill), never the shared Omi thread.
   *  This is the ONLY agent surface in the bar's hub (Mac parity: the list is
   *  strictly pills-for-actual-runs; there are no idle connected-agent rows —
   *  connecting agents lives in Settings → Agents). */
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
  const { chat, view, expanded } = props
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const messagesRef = useRef<HTMLDivElement>(null)
  const followRef = useRef(true)
  // Monotonic submit id — a refused send may only restore its text if it is still
  // the last thing the user asked (see submit()).
  const submitSeq = useRef(0)
  // Latest-ref so the composer handlers below can be STABLE (memoized once) yet
  // always read current props — that stability is what lets the memoized
  // ChatComposer skip the projected-chat ticks that re-render this parent.
  const propsRef = useRef(props)
  // eslint-disable-next-line react-hooks/refs -- latest-ref for the stable composer handlers
  propsRef.current = props

  // Focus the active view's input when the surface is EXPANDED (Mac AskAIInputView
  // focusOnAppear: expanding lands with the cursor in the input, ready to type in
  // place). Keyed on [expanded, view], guarded on `expanded`: this component stays
  // mounted while the bar is a collapsed pill, so a plain [view] effect would fire
  // once at startup against the hidden textarea and never re-run on expand (the
  // MODE flips to expanded while the view stays 'list'). Guarding on `expanded`
  // fires it on the real expand AND on each list⇄conversation switch, and never
  // steals focus while collapsed. inputRef attaches to whichever textarea is
  // mounted (the two views never render together), so one ref drives focus +
  // auto-grow for both.
  useEffect(() => {
    if (expanded) inputRef.current?.focus()
  }, [expanded, view])

  // Auto-grow the mounted textarea to its content (re-run on a view switch so the
  // freshly mounted input sizes to the shared draft immediately).
  useLayoutEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [props.draft, view])

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

  // The single send path. Whether it navigates is DERIVED from the view: a hub
  // send (view 'list') opens the conversation — the ONLY moment the surface
  // transitions from the ask state (Mac's .mainInput) to the response state
  // (.mainResponse); an in-conversation send is already there. Send-once either
  // way: onSubmit runs a single time; the navigate is a pure view flip in the
  // parent, not a second send. Stable (reads propsRef) so the memoized composer's
  // onSubmit identity doesn't churn on chat ticks.
  const submit = useCallback((): void => {
    const p = propsRef.current
    const text = p.draft.trim()
    if (!text) return
    p.setDraft('')
    followRef.current = true
    // Flip to the conversation BEFORE awaiting the send so the reply streams into
    // the response state (always the shared Omi thread). A send refused by the
    // usage limit still lands here and surfaces its notice + restored text inline,
    // exactly as an in-conversation refusal does.
    if (p.view === 'list') p.onOpenConversation()
    const seq = ++submitSeq.current
    void p.onSubmit(text).then((notice) => {
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
      p.setDraft((current) => (current.trim() ? current : text))
    })
  }, [])

  // Textarea key handling, one stable handler per surface flavor. Both let PTT
  // claim Space first (hold-to-talk while focused) and send on Enter. The hub
  // flavor ALSO clears a non-empty draft on Esc in place (Mac: Esc clears the
  // inline input) and stops that Esc reaching BarApp's window handler (which hides
  // the bar); a blank/whitespace-only draft bubbles through, so a second Esc still
  // closes the bar (draft.trim() — a stray space must not eat the close).
  const hubKeyDown = useCallback(
    (e: React.KeyboardEvent): void => {
      const p = propsRef.current
      if (p.pttKeyDown(e)) return
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        submit()
        return
      }
      if (e.key === 'Escape' && p.draft.trim()) {
        e.preventDefault()
        e.stopPropagation()
        p.setDraft('')
      }
    },
    [submit]
  )
  const conversationKeyDown = useCallback(
    (e: React.KeyboardEvent): void => {
      const p = propsRef.current
      if (p.pttKeyDown(e)) return
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        submit()
      }
    },
    [submit]
  )
  const onComposerKeyUp = useCallback((e: React.KeyboardEvent): void => {
    propsRef.current.pttKeyUp(e)
  }, [])

  // send-state for the Send button + Enter (mirrors macOS: no send while a turn is
  // in flight or the draft is blank). Passed to the memoized composer as a plain
  // bool so a chat tick that doesn't change it can't force a composer re-render.
  const sendDisabled = chat.sending || props.recording || props.transcribing || !props.draft.trim()

  if (view === 'list') {
    return (
      // key={view} remounts on every list⇄conversation switch so bar-view-enter
      // replays — the swap morphs in place instead of popping a new sheet.
      <div key="list" className="bar-view-enter flex flex-col gap-1 px-3 pb-3 pt-1">
        {/* The hub's Ask-Omi input (Mac AskAIInputView / .mainInput). Clicking or
            focusing it just puts the cursor here — it does NOT navigate (the old
            "Omi Chat" row opened the conversation on a single click, the reported
            bug). Typing stays in place; only SEND (Enter or the button) flips to
            the conversation (.mainResponse), driven by submit()'s view-derived
            navigate. The shared draft (INV-CHAT-1) carries the text into the one
            thread. Esc clears in place (hubKeyDown). */}
        <ChatComposer
          inputRef={inputRef}
          draft={props.draft}
          setDraft={props.setDraft}
          onKeyDown={hubKeyDown}
          onKeyUp={onComposerKeyUp}
          onSubmit={submit}
          sendDisabled={sendDisabled}
          placeholder="Ask Omi anything…  ·  hold Space to talk"
          className="flex items-end gap-2 px-1 pb-1 pt-1"
        />

        {/* A failed push-to-talk hold while the hub is focused surfaces its hint
            inline (same copy the conversation composer shows). */}
        {props.pttNotice ? (
          <div role="status" className="px-2 pb-1 pt-1 text-xs leading-relaxed text-amber-300/90">
            {props.pttNotice}
          </div>
        ) : null}

        {/* The static "Omi Chat" row (Mac notchOmiChatRow) — always present so the
            shared Omi conversation is reachable from the bar without sending a
            message. A single click flips to the response state (no draft, no send).
            Sits above the run pills when any exist. */}
        <OmiChatRow onOpen={props.onOpenConversation} />

        {/* Live/recent spawned agent runs (B3) — the bar's only agent surface.
            Each pill opens its OWN run transcript, not the shared Omi thread. */}
        {props.pills.length > 0 ? (
          <div className="flex flex-col gap-1">
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

      <ChatComposer
        inputRef={inputRef}
        draft={props.draft}
        setDraft={props.setDraft}
        onKeyDown={conversationKeyDown}
        onKeyUp={onComposerKeyUp}
        onSubmit={submit}
        sendDisabled={sendDisabled}
        placeholder="Ask Omi…  ·  hold Space to talk"
        className="flex items-end gap-2 px-3 pb-3 pt-2"
      />
    </div>
  )
}
