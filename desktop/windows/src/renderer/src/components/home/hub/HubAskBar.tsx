import { useRef, useState } from 'react'
import { ArrowUp, Link as LinkIcon, Loader2, Paperclip } from 'lucide-react'
import { cn } from '../../../lib/utils'
import {
  addAttachments,
  removeAttachment,
  MAX_CHAT_ATTACHMENTS,
  type RejectReason
} from '../../../lib/chatAttachments'
import { filesToPickedChatFiles } from '../../../lib/chatDropFiles'
import { usePendingAttachments } from '../../../hooks/usePendingAttachments'
import { AttachmentChip } from './AttachmentChip'
import type { PickedChatFile } from '../../../../../shared/types'

// A one-line summary of what the attachment layer rejected, so files never drop
// silently (Mac surfaces these). Reasons are ranked by how actionable they are.
function describeRejections(rejected: { reason: RejectReason }[]): string {
  const reasons = new Set(rejected.map((r) => r.reason))
  if (reasons.has('too_large')) return 'Some files exceed the 25 MB limit.'
  if (reasons.has('cap_exceeded')) return `You can attach up to ${MAX_CHAT_ATTACHMENTS} files.`
  return "Some files couldn't be added."
}

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
  const { value, onChange, onSubmit, onFocus, sending, connectActive, onToggleConnect, autoFocus } =
    props
  const [focused, setFocused] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [rejectNote, setRejectNote] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const attachments = usePendingAttachments()
  const atCap = attachments.length >= MAX_CHAT_ATTACHMENTS
  // Send is allowed with text OR at least one attachment that hasn't failed —
  // never while a reply streams, and never a failed-only set (that would post an
  // empty message). useChat.send applies the same rule plus a post-upload
  // recheck; this just drives the button.
  const canSend =
    (value.trim().length > 0 || attachments.some((a) => a.status !== 'failed')) && !sending

  // Stage picked/dropped files and surface anything the attachment layer rejected
  // (over the 4-file cap, over 25 MB, or unreadable) rather than dropping silently.
  const stage = (picked: PickedChatFile[]): void => {
    const { rejected } = addAttachments(picked)
    setRejectNote(rejected.length > 0 ? describeRejections(rejected) : null)
  }

  const pickFiles = async (): Promise<void> => {
    try {
      const picked = await window.omi.openChatFiles()
      if (picked.length > 0) stage(picked)
    } catch {
      // The picker IPC threw (rare); nothing to stage — don't leak a rejection.
    }
  }

  const onDrop = async (e: React.DragEvent): Promise<void> => {
    e.preventDefault()
    setDragging(false)
    const files = Array.from(e.dataTransfer.files)
    if (files.length === 0) return
    stage(await filesToPickedChatFiles(files))
  }

  // The WHOLE pill is a hit target — clicking anywhere in it seats the caret in the
  // input, matching Mac's `.contentShape(.rect(cornerRadius: 29)).onTapGesture` on the
  // whole HomeAskBar pill (DashboardPage.swift:2211-2214). Without this only the input's
  // own thin text line was clickable: the 58px pill's top/bottom strips and the padding
  // to either side were dead zones, so a click near the pill's edge did nothing — the
  // reported bug. The paperclip and the trailing Connect/Send button keep their own
  // actions (a click that lands on a button returns early), and a click already on the
  // input keeps native caret placement.
  const focusFromPill = (e: React.MouseEvent): void => {
    const target = e.target as HTMLElement
    if (target === inputRef.current || target.closest('button')) return
    // preventDefault so the mousedown doesn't move focus to the container (or start a
    // text selection on it). Then hand focus to the input on the NEXT frame — a
    // focus() called synchronously inside a preventDefault'd mousedown is swallowed by
    // Chromium/Electron (the browser's own post-dispatch focus handling reverts it, so
    // the input never actually focuses — verified: the handler ran but activeElement
    // stayed <body>). Deferring past the event makes the focus stick, and focusing the
    // input fires onFocus, opening the chat stage exactly as a direct input click does.
    e.preventDefault()
    requestAnimationFrame(() => inputRef.current?.focus())
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
        onMouseDown={focusFromPill}
        className={cn(
          'flex h-[58px] w-full cursor-text items-center rounded-[29px] border pl-2 pr-2',
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
              ? 'cursor-not-allowed text-home-muted opacity-40'
              : 'cursor-pointer text-home-muted hover:bg-white/10 hover:text-home-ink'
          )}
        >
          <Paperclip className="h-[15px] w-[15px]" strokeWidth={2.25} />
        </button>

        <input
          ref={inputRef}
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
            className="focus-ring flex h-[34px] w-[34px] shrink-0 cursor-pointer items-center justify-center rounded-full bg-white text-home-paper transition-opacity duration-150 hover:opacity-90"
          >
            <ArrowUp className="h-[13px] w-[13px]" strokeWidth={2.75} />
          </button>
        ) : focused ? null : (
          <button
            type="button"
            onClick={onToggleConnect}
            aria-pressed={connectActive}
            className={cn(
              'focus-ring flex h-[34px] shrink-0 cursor-pointer items-center gap-1.5 rounded-full px-[13px]',
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
      {rejectNote && (
        <p className="mt-1.5 px-1 text-[11px] text-home-muted" role="status">
          {rejectNote}
        </p>
      )}
    </div>
  )
}
