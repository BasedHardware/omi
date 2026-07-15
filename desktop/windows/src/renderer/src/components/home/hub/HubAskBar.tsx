import { useState } from 'react'
import { ArrowUp, Link as LinkIcon, Loader2, Paperclip } from 'lucide-react'
import { cn } from '../../../lib/utils'
import {
  addAttachments,
  removeAttachment,
  MAX_CHAT_ATTACHMENTS
} from '../../../lib/chatAttachments'
import { filesToPickedChatFiles } from '../../../lib/chatDropFiles'
import { usePendingAttachments } from '../../../hooks/usePendingAttachments'
import { AttachmentChip } from './AttachmentChip'

// The Hub's ask bar. It is the ONLY chat input on the Hub — it re-docks to the
// bottom of the chat panel rather than being replaced by a second bar, so there
// is one input element and one draft across both stage modes.
//
// Attachments (Mac parity): a paperclip at the leading edge opens the native file
// picker, files can be dropped onto the bar, and staged files show as chips above
// the pill. The pending list + upload lifecycle live in Track 1's module-level
// attachment layer (lib/chatAttachments); this component reads it via
// usePendingAttachments and drives it with addAttachments/removeAttachment.
// useChat.send() drains the pending list at send time, so a message can carry
// text, files, or both.

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
  const [dragging, setDragging] = useState(false)
  const attachments = usePendingAttachments()
  const atCap = attachments.length >= MAX_CHAT_ATTACHMENTS
  // A send is allowed with text, with attachments, or both — never while a reply
  // is streaming. (useChat.send applies the same rule; this drives the button.)
  const canSend = (value.trim().length > 0 || attachments.length > 0) && !sending

  const pickFiles = async (): Promise<void> => {
    const picked = await window.omi.openChatFiles()
    if (picked.length > 0) addAttachments(picked)
  }

  const onDrop = async (e: React.DragEvent): Promise<void> => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length === 0) return
    addAttachments(await filesToPickedChatFiles(files))
  }

  return (
    <div
      className="w-full"
      data-testid="hub-ask-bar"
      onDragOver={(e) => {
        e.preventDefault()
        if (!dragging) setDragging(true)
      }}
      onDragLeave={(e) => {
        // Only clear when the pointer actually leaves the bar — dragLeave also
        // fires when crossing into a child, which would flicker the highlight.
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false)
      }}
      onDrop={onDrop}
    >
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1.5" data-testid="hub-attachment-chips">
          {attachments.map((a) => (
            <AttachmentChip key={a.id} attachment={a} onRemove={() => removeAttachment(a.id)} />
          ))}
        </div>
      )}

      <div
        className={cn(
          'flex h-[58px] w-full items-center rounded-[29px] border pl-2 pr-2',
          'transition-[background-color,border-color,box-shadow] duration-150 ease-out',
          dragging
            ? 'border-[rgb(var(--home-stage-glow-rgb)/0.4)] bg-home-tile'
            : focused
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
        {/* Leading paperclip — opens the native picker; disabled at the 4-file cap. */}
        <button
          type="button"
          onClick={pickFiles}
          disabled={atCap}
          aria-label={
            atCap ? `Attachment limit reached (${MAX_CHAT_ATTACHMENTS} files)` : 'Attach files'
          }
          className={cn(
            'focus-ring mr-1 flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full',
            'transition-colors duration-150',
            atCap
              ? 'cursor-not-allowed text-home-faint'
              : 'text-home-muted hover:bg-white/10 hover:text-home-ink'
          )}
        >
          <Paperclip className="h-[15px] w-[15px]" strokeWidth={2.25} />
        </button>

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
    </div>
  )
}
