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

// Mac's transcript panel: chat-style speaker bubbles in a 450pt drawer that
// slides in from the trailing edge (0.25s ease-in-out), closed by default.
//
// Text is deliberately NOT selectable. Mac removed selection because it caused
// 2s+ main-thread hangs at ~400 segments; users copy via the header's "Copy
// transcript" button instead. We inherit that rule, and additionally lean on
// `content-visibility: auto` so off-screen bubbles cost nothing to lay out —
// that is what keeps a 400-segment scroll smooth without a virtualization dep.

const DRAWER_WIDTH = 450 // px — Mac's exact drawer width

function formatTime(seconds?: number | null): string {
  if (seconds == null) return ''
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`
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

        <div
          className="max-w-full select-none rounded-2xl px-3 py-2 text-[13px] leading-relaxed text-white"
          style={{ background: bubbleColor(speakerId, isUser) }}
        >
          {segment.text}
        </div>

        {translation && (
          <div
            className="max-w-full select-none rounded-2xl px-3 py-2 text-[13px] italic leading-relaxed text-white opacity-50"
            style={{ background: bubbleColor(speakerId, isUser) }}
          >
            {translation}
          </div>
        )}
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
    <aside
      // Kept mounted so the slide animates both ways; hidden from AT + tab order
      // when closed so a collapsed drawer can't be focused.
      aria-hidden={!open}
      inert={!open}
      data-testid="transcript-drawer"
      data-open={open}
      className="absolute inset-y-0 right-0 z-20 flex flex-col border-l border-border bg-bg-secondary shadow-2xl"
      style={{
        width: DRAWER_WIDTH,
        transform: open ? 'translateX(0)' : `translateX(${DRAWER_WIDTH}px)`,
        transition: 'transform 0.25s ease-in-out'
      }}
    >
      <header className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
        <h2 className="font-display text-sm font-semibold text-white">Transcript</h2>
        <button
          onClick={onClose}
          className="btn-ghost p-1.5"
          title="Hide Transcript"
          aria-label="Hide Transcript"
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
  )
}
