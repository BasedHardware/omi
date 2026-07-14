import { useMemo, useState } from 'react'
import { Check, Loader2, X } from 'lucide-react'
import type { Person, TranscriptSegment } from '../../lib/omiApi.generated'
import { assignSegmentsBulk, createPerson } from '../../lib/conversations/people'
import {
  collectSpeakerSegments,
  segmentIdsToAssign,
  speakerIdOf
} from '../../lib/conversations/speakers'
import { toast } from '../../lib/toast'
import { ModalShell } from './ModalShell'
import { AVATAR_UNNAMED } from './speakerPalette'

// Mac's NameSpeakerSheet (NameSpeakerSheet.swift), rendered as a centered Windows
// modal per the Track 4 ruling. Mac's sheet is a fixed 400x450 whose height is
// filled by a real structure (NameSpeakerSheet.swift:48-117):
//
//   header ("Name Speaker" + dismiss) / divider / SCROLLVIEW (speaker preview,
//   "Who is this?" chips, tag-others toggle) / divider / footer (Cancel + Save)
//
// The scroll region absorbs the leftover height, so the sheet is never half-empty.
// An earlier revision here rendered only three full-width rows inside the fixed
// 450px box — leaving ~220px of dead space — and saved instantly on chip click,
// skipping Mac's select-then-Save flow. Both reviewer-caught; this is the port.
//
// People are ACCOUNT-WIDE (not conversation-scoped). The "also tag N others"
// toggle defaults ON, so naming a speaker applies to ALL of that speaker's
// segments in THIS conversation (never across other conversations).

const PREVIEW_MAX = 120 // Mac truncates the segment preview at 120 chars

type Selection =
  | { kind: 'none' }
  | { kind: 'user' }
  | { kind: 'person'; id: string }
  | { kind: 'new' }

export function NameSpeakerModal({
  conversationId,
  segments,
  segment,
  people,
  onClose,
  onSaved,
  onPersonCreated
}: {
  conversationId: string
  segments: TranscriptSegment[]
  /** The segment whose speaker label was clicked. */
  segment: TranscriptSegment
  people: Person[]
  onClose: () => void
  /** Called after a successful assign so the page can refetch the conversation. */
  onSaved: () => void
  /** Called with a newly created person so the page can add them to the roster. */
  onPersonCreated: (person: Person) => void
}): React.JSX.Element {
  const [selection, setSelection] = useState<Selection>({ kind: 'none' })
  const [newName, setNewName] = useState('')
  const [applyToAll, setApplyToAll] = useState(true) // Mac default: ON
  const [saving, setSaving] = useState(false)

  const speakerId = speakerIdOf(segment)
  const speaker = useMemo(() => collectSpeakerSegments(segments, speakerId), [segments, speakerId])

  const targetIds = segmentIdsToAssign(segments, segment, applyToAll)
  // Nothing the server can address: every segment for this speaker is still
  // syncing. Mac would send a synthetic "#index:N" id here and the PATCH would
  // silently no-op — the user names a speaker and nothing happens. Say so instead.
  const unaddressable = targetIds.length === 0
  const partiallySynced = applyToAll && !unaddressable && speaker.unsyncedCount > 0

  const preview =
    segment.text.length > PREVIEW_MAX ? `${segment.text.slice(0, PREVIEW_MAX)}...` : segment.text

  const canSave =
    !unaddressable &&
    !saving &&
    (selection.kind === 'user' ||
      selection.kind === 'person' ||
      (selection.kind === 'new' && newName.trim().length > 0))

  const save = async (): Promise<void> => {
    if (!canSave) return
    setSaving(true)
    try {
      let assign: { type: 'is_user' } | { type: 'person_id'; personId: string }
      if (selection.kind === 'user') {
        assign = { type: 'is_user' }
      } else if (selection.kind === 'person') {
        assign = { type: 'person_id', personId: selection.id }
      } else {
        const person = await createPerson(newName.trim())
        onPersonCreated(person)
        assign = { type: 'person_id', personId: person.id }
      }
      await assignSegmentsBulk(conversationId, targetIds, assign)
      onSaved()
      onClose()
    } catch (e) {
      toast('Could not name speaker', { tone: 'error', body: (e as Error).message })
      setSaving(false)
    }
  }

  const chip = (label: string, selected: boolean, onClick: () => void): React.JSX.Element => (
    <button
      key={label}
      onClick={onClick}
      disabled={saving || unaddressable}
      aria-pressed={selected}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
        selected
          ? 'border-white bg-white text-bg-primary'
          : 'border-white/15 bg-white/[0.06] text-white hover:bg-white/[0.12]'
      }`}
    >
      {label}
    </button>
  )

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-[400px]" labelledBy="name-speaker-title">
      {/* -m-6 cancels ModalShell's padding so the dividers span edge to edge.
          Mac's sheet is a FIXED 400x450, but a fixed height leaves visible dead space
          under a short roster (reviewer-caught). We keep Mac's 450 as a CEILING and
          size to content below it: a small roster gives a compact sheet with no void,
          and a large roster still caps at 450 with the middle region scrolling. */}
      <div className="-m-6 flex max-h-[min(450px,80vh)] flex-col">
        <header className="flex shrink-0 items-center justify-between px-5 pb-3 pt-5">
          <h2 id="name-speaker-title" className="font-display text-base font-semibold text-white">
            Name Speaker
          </h2>
          <button onClick={onClose} className="btn-ghost p-1" title="Close" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="h-px shrink-0 bg-border" />

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {/* Speaker preview (Mac's speakerInfoSection) */}
          <div className="rounded-xl bg-bg-secondary p-3">
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
                style={{ background: AVATAR_UNNAMED }}
              >
                {speakerId}
              </span>
              <span className="text-sm font-medium text-white">Speaker {speakerId}</span>
            </div>
            <p className="mt-2 line-clamp-3 text-[13px] italic text-text-secondary">“{preview}”</p>
          </div>

          {unaddressable ? (
            <div className="rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
              This conversation is still syncing, so these segments can’t be named yet. Try again in
              a moment.
            </div>
          ) : partiallySynced ? (
            <div className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs leading-relaxed text-text-tertiary">
              {speaker.unsyncedCount} of this speaker’s {speaker.total} segments are still syncing
              and will keep their current label.
            </div>
          ) : null}

          {/* Mac's peopleSelectionSection: a wrapping row of chips, not full-width rows */}
          <div>
            <p className="mb-2.5 text-[13px] font-medium text-text-secondary">Who is this?</p>
            <div className="flex flex-wrap gap-2">
              {chip('You', selection.kind === 'user', () => setSelection({ kind: 'user' }))}
              {people.map((p) =>
                chip(p.name, selection.kind === 'person' && selection.id === p.id, () =>
                  setSelection({ kind: 'person', id: p.id })
                )
              )}
              {chip('+ Add Person', selection.kind === 'new', () => setSelection({ kind: 'new' }))}
            </div>

            {selection.kind === 'new' && (
              /* autoFocus is intentional: the field only exists once "+ Add Person" is picked */
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Person name"
                aria-label="New person name"
                disabled={saving}
                className="mt-3 w-full rounded-lg border border-white/15 bg-bg-secondary px-2.5 py-2 text-[13px] text-white placeholder:text-text-quaternary focus:border-white/40 focus:outline-none"
              />
            )}
          </div>

          {/* Mac shows this only when the speaker has more than one segment */}
          {speaker.total > 1 && (
            <label className="flex cursor-pointer items-center gap-2.5 text-xs text-text-secondary">
              <input
                type="checkbox"
                checked={applyToAll}
                onChange={(e) => setApplyToAll(e.target.checked)}
                disabled={saving}
                className="sr-only"
              />
              <span
                aria-hidden
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border transition-colors ${
                  applyToAll ? 'border-white bg-white text-bg-primary' : 'border-white/25'
                }`}
              >
                {applyToAll && <Check className="h-3 w-3" strokeWidth={3} />}
              </span>
              Also tag {speaker.total - 1} other segment
              {speaker.total - 1 === 1 ? '' : 's'} from this speaker
            </label>
          )}
        </div>

        <div className="h-px shrink-0 bg-border" />

        <footer className="flex shrink-0 items-center justify-end gap-2 px-5 py-3.5">
          <button
            onClick={onClose}
            disabled={saving}
            className="btn-ghost px-4 py-1.5 text-sm text-text-secondary"
          >
            Cancel
          </button>
          <button
            onClick={save}
            disabled={!canSave}
            className="flex items-center gap-1.5 rounded-full bg-white px-5 py-1.5 text-sm font-medium text-bg-primary disabled:bg-white/15 disabled:text-text-tertiary"
          >
            {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Save
          </button>
        </footer>
      </div>
    </ModalShell>
  )
}
