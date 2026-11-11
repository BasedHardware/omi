import { Pencil, X } from 'lucide-react'
import type { Person, TranscriptSegment } from '../../lib/omiApi.generated'
import {
  avatarFill,
  avatarInitial,
  bubbleColor,
  personNameFor,
  speakerIdOf,
  speakerLabel
} from '../../lib/conversations/speakers'

// Mac's transcript panel (ConversationDetailView.swift:114-166): the root is an
// `HStack(spacing: 0)` whose children are the content column
// (`.frame(maxWidth: .infinity)`) and — when open — a 1px divider plus the drawer
// at `.frame(width: 450)` with `.transition(.move(edge: .trailing))`.
//
// That means the drawer is a LAYOUT SIBLING, not an overlay: opening it COMPRESSES
// the content column, and the page header (with its action buttons) stays fully
// visible and reachable. An earlier revision here positioned the drawer absolutely,
// which covered the header's Copy link / Copy transcript / Move / Delete cluster and
// the View/Hide Transcript pill itself — reviewer-caught, and wrong versus Mac.
//
// The reveal keeps the Mac feel without squishing text mid-animation: the outer
// element animates its width 0 -> 450 while an inner fixed-450 panel is pinned to
// its right edge (justify-end + overflow-hidden), so the panel slides in from the
// trailing edge and the content column reflows around it.
//
// Text is deliberately NOT selectable. Mac removed selection because it caused 2s+
// main-thread hangs at ~400 segments; users copy via the header's "Copy transcript"
// button instead. `content-visibility` keeps a 400-segment scroll smooth without a
// virtualization dep.

const DRAWER_WIDTH = 450 // px — Mac's exact drawer width

function formatTime(seconds?: number | null): string {
  if (seconds == null) return ''
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`
}

/** Mac renders a translation as a sub-bubble whose FILL is the speaker color at
 *  50% (`bubbleColor.opacity(0.5)`) with normal-opacity italic secondary text —
 *  not the whole element at 50%, which would wash out the text too. */
function fillAt50(hex: string): string {
  const m = /^#([0-9a-f]{6})$/i.exec(hex)
  if (!m) return hex
  const n = Number.parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, 0.5)`
}

function SegmentBubble({
  segment,
  people,
  onNameSpeaker
}: {
  segment: TranscriptSegment
  people: Person[]
  onNameSpeaker: (segment: TranscriptSegment) => void
}): React.JSX.Element {
  const isUser = segment.is_user
  const speakerId = speakerIdOf(segment)
  const name = personNameFor(segment, people)
  const label = speakerLabel(speakerId, isUser, name)
  const fill = bubbleColor(speakerId, isUser)
  const translation = segment.translations?.[0]?.text

  return (
    <li
      className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}
      style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 72px' }}
    >
      <span
        aria-hidden
        className="mt-0.5 flex h-8 w-8 shrink-0 select-none items-center justify-center rounded-full text-xs font-semibold text-white"
        style={{ background: avatarFill(isUser, name) }}
      >
        {avatarInitial(speakerId, isUser, name)}
      </span>

      <div className={`flex min-w-0 flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
        <div className="flex items-center gap-1.5">
          {isUser ? (
            <span className="text-[11px] font-medium text-text-quaternary">{label}</span>
          ) : (
            // Tapping a non-user speaker opens the NameSpeaker sheet.
            <button
              onClick={() => onNameSpeaker(segment)}
              className="group flex items-center gap-1 text-[11px] font-medium text-text-tertiary transition-colors hover:text-white"
              title={name ? `Rename ${name}` : 'Name this speaker'}
            >
              {label}
              <Pencil className="h-2.5 w-2.5 opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          )}
          {segment.start != null && (
            <span className="font-mono text-[10px] text-text-quaternary">
              {formatTime(segment.start)}
            </span>
          )}
        </div>

        {/* The bubble and its translation share one box, so their edges line up
            (Mac lets each size to its own text; aligning them reads cleaner and was
            a review request). */}
        <div className={`flex max-w-full flex-col gap-1 ${isUser ? 'items-end' : 'items-start'}`}>
          <div
            className="w-full select-none rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed text-white"
            style={{ background: fill }}
          >
            {segment.text}
          </div>

          {translation && (
            <div
              className="w-full select-none rounded-2xl px-3.5 py-2 text-[13px] italic leading-relaxed text-text-secondary"
              style={{ background: fillAt50(fill) }}
            >
              {translation}
            </div>
          )}
        </div>
      </div>
    </li>
  )
}

export function TranscriptDrawer({
  open,
  segments,
  people,
  onClose,
  onNameSpeaker
}: {
  open: boolean
  segments: TranscriptSegment[]
  people: Person[]
  onClose: () => void
  onNameSpeaker: (segment: TranscriptSegment) => void
}): React.JSX.Element {
  return (
    <div
      // Kept mounted so the slide animates both ways; hidden from AT + tab order
      // when closed so a collapsed drawer can't be focused.
      aria-hidden={!open}
      inert={!open}
      data-testid="transcript-drawer"
      data-open={open}
      className="flex shrink-0 justify-end overflow-hidden"
      style={{
        width: open ? DRAWER_WIDTH : 0,
        transition: 'width 0.25s ease-in-out'
      }}
    >
      <aside
        data-testid="transcript-panel"
        className="flex h-full flex-col border-l border-border bg-bg-secondary"
        style={{ width: DRAWER_WIDTH }}
      >
        <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
          <h2 className="font-display text-sm font-semibold text-white">Transcript</h2>
          {/* Named distinctly from the header's "Hide Transcript" pill — two buttons
              with the same accessible name is ambiguous for screen readers. */}
          <button
            onClick={onClose}
            className="btn-ghost p-1.5"
            title="Close transcript"
            aria-label="Close transcript"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {segments.length === 0 ? (
            <p className="mt-6 text-center text-xs text-text-quaternary">No transcript yet.</p>
          ) : (
            <ul className="space-y-3.5">
              {segments.map((s, i) => (
                <SegmentBubble
                  key={s.id || i}
                  segment={s}
                  people={people}
                  onNameSpeaker={onNameSpeaker}
                />
              ))}
            </ul>
          )}
        </div>
      </aside>
    </div>
  )
}
