import { useState } from 'react'
import { ArrowUp, Link as LinkIcon, Loader2 } from 'lucide-react'
import { cn } from '../../../lib/utils'

// The Hub's ask bar. It is the ONLY chat input on the Hub — it re-docks to the
// bottom of the chat panel rather than being replaced by a second bar, so there
// is one input element and one draft across both stage modes.
//
// Mac puts a paperclip (attachments) at the leading edge. Windows chat has no
// attachment path — send() takes text alone — so the icon is omitted rather than
// rendered dead: a visible paperclip invites a click that would do nothing, and
// hiding it from screen readers wouldn't stop that. The 16px leading pad it would
// have occupied is kept, so the bar's proportions hold and the icon can take the
// space back on the day it arrives with a real handler.

export function HubAskBar(props: {
  value: string
  onChange: (v: string) => void
  onSubmit: () => void
  onFocus: () => void
  sending: boolean
  connectActive: boolean
  onToggleConnect: () => void
  /** Take keyboard focus on mount. See HomeHub: the bar RE-DOCKS into the chat
   *  panel, which means React unmounts and remounts this input under a new parent
   *  — and the caret goes with it. Without this, clicking the ask bar opens the
   *  panel and silently drops your focus on the floor, so the first thing you type
   *  goes nowhere. */
  autoFocus?: boolean
}): React.JSX.Element {
  const {
    value,
    onChange,
    onSubmit,
    onFocus,
    sending,
    connectActive,
    onToggleConnect,
    autoFocus
  } = props
  const [focused, setFocused] = useState(false)
  const canSend = value.trim().length > 0 && !sending

  return (
    <div
      className={cn(
        'flex h-[58px] w-full items-center rounded-[29px] border pl-4 pr-2',
        'transition-[background-color,border-color,box-shadow] duration-150 ease-out',
        focused
          ? 'border-[rgb(var(--home-stage-glow-rgb)/0.16)] bg-home-tile'
          : 'border-[rgb(var(--home-stage-glow-rgb)/0.08)] bg-home-tile/[0.92] hover:bg-home-tile'
      )}
      style={{
        // Two stacked shadows: a violet stage-glow bloom and a black lift. Both
        // deepen on focus, so the bar reads as raised off the stage.
        boxShadow: focused
          ? '0 8px 22px rgb(var(--home-stage-glow-rgb) / 0.11), 0 10px 24px rgb(0 0 0 / 0.45)'
          : '0 8px 16px rgb(var(--home-stage-glow-rgb) / 0.045), 0 10px 24px rgb(0 0 0 / 0.34)'
      }}
    >
      <input
        // Not a page-load autofocus: this fires only when the bar re-mounts inside the
        // chat panel, restoring the focus the user already had. In the resting hub it is
        // false. No jsx-a11y plugin is configured here, so autoFocus needs no disable.
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => {
          setFocused(true)
          onFocus()
        }}
        onBlur={() => setFocused(false)}
        onKeyDown={(e) => {
          // isComposing: while an IME candidate window is open (CJK, and Windows'
          // own emoji/handwriting panels), Enter COMMITS the candidate — it is not a
          // submit. Sending here would fire off a half-composed message and swallow
          // the keystroke the user meant for the IME.
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) onSubmit()
        }}
        placeholder="Ask omi anything"
        aria-label="Ask omi anything"
        className="mr-3 min-w-0 flex-1 border-0 bg-transparent text-[15px] text-home-ink placeholder:text-home-muted focus:outline-none focus:ring-0"
      />

      {/* Exactly one thing sits on the right, in priority order. */}
      {sending ? (
        // A BUSY INDICATOR, not a stop button. Mac shows stop here, but a real
        // stop needs an abort that leaves history intact — useChat exposes only
        // reset(), which starts a fresh conversation, so wiring a stop to it would
        // delete the user's thread to halt one reply. useChat already holds an
        // abortRef and a generation counter to build a true stop() on; that work
        // belongs to the chat-platform track that owns the engine, not here. Until
        // then this is deliberately non-interactive — no button, no click handler —
        // so nothing invites a press that can't be honored. Keeps the 34x34
        // footprint so the bar doesn't shift geometry when a send starts.
        <div
          role="status"
          aria-busy="true"
          aria-label="Omi is replying"
          className="flex h-[34px] w-[34px] shrink-0 items-center justify-center"
        >
          <Loader2 className="h-4 w-4 animate-spin text-home-muted" strokeWidth={2.5} />
        </div>
      ) : canSend ? (
        <button
          type="button"
          onClick={onSubmit}
          aria-label="Send"
          className="focus-ring flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-white text-home-paper transition-opacity duration-150 hover:opacity-90"
        >
          <ArrowUp className="h-[13px] w-[13px]" strokeWidth={2.75} />
        </button>
      ) : focused ? null : (
        <button
          type="button"
          onClick={onToggleConnect}
          aria-pressed={connectActive}
          className={cn(
            'focus-ring flex h-[34px] shrink-0 items-center gap-1.5 rounded-full px-[13px]',
            'text-[12px] font-medium transition-colors duration-150',
            connectActive
              ? 'bg-white text-home-paper'
              : 'border border-home-hairline bg-white/[0.07] text-home-ink hover:bg-white/[0.14]'
          )}
        >
          <LinkIcon className="h-[11px] w-[11px] shrink-0" strokeWidth={2.5} />
          Connect
        </button>
      )}
    </div>
  )
}
