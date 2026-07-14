import { useMemo, useState } from 'react'
import { Check, Loader2, Plus, User } from 'lucide-react'
import type { Person, TranscriptSegment } from '../../lib/omiApi.generated'
import { assignSegmentsBulk, createPerson } from '../../lib/conversations/people'
import {
  collectSpeakerSegments,
  segmentIdsToAssign,
  speakerIdOf
} from '../../lib/conversations/speakers'
import { toast } from '../../lib/toast'
import { ModalShell } from './ModalShell'
import { AVATAR_PERSON, AVATAR_USER } from './speakerPalette'

// Mac's NameSpeakerSheet (fixed 400x450), rendered as a centered Windows modal
// per the Track 4 ruling. Attribute a transcript segment to the user or to an
// account-wide Person — people are NOT conversation-scoped, so naming someone
// here offers them in every other conversation too.
//
// The "also tag N other segments" toggle defaults ON, so by default naming a
// speaker applies to ALL of that speaker's segments in THIS conversation (never
// across other conversations).

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
  const [applyToAll, setApplyToAll] = useState(true) // Mac default: ON
  const [saving, setSaving] = useState(false)
  const [addingName, setAddingName] = useState<string | null>(null)

  const speakerId = speakerIdOf(segment)
  const speaker = useMemo(() => collectSpeakerSegments(segments, speakerId), [segments, speakerId])

  const targetIds = segmentIdsToAssign(segments, segment, applyToAll)
  // Nothing the server can address: every segment for this speaker is still
  // syncing. Mac would send a synthetic "#index:N" id here and the PATCH would
  // silently no-op — the user names a speaker and nothing happens. Say so instead.
  const unaddressable = targetIds.length === 0
  // Some (but not all) of this speaker's segments have no backend id yet.
  const partiallySynced = applyToAll && !unaddressable && speaker.unsyncedCount > 0

  const save = async (
    assign: { type: 'is_user' } | { type: 'person_id'; personId: string }
  ): Promise<void> => {
    if (saving || unaddressable) return
    setSaving(true)
    try {
      await assignSegmentsBulk(conversationId, targetIds, assign)
      onSaved()
      onClose()
    } catch (e) {
      toast('Could not name speaker', { tone: 'error', body: (e as Error).message })
      setSaving(false)
    }
  }

  const addPerson = async (name: string): Promise<void> => {
    const trimmed = name.trim()
    if (!trimmed || saving) return
    setSaving(true)
    try {
      const person = await createPerson(trimmed)
      onPersonCreated(person)
      await assignSegmentsBulk(conversationId, targetIds, {
        type: 'person_id',
        personId: person.id
      })
      onSaved()
      onClose()
    } catch (e) {
      toast('Could not add person', { tone: 'error', body: (e as Error).message })
      setSaving(false)
    }
  }

  return (
    <ModalShell onClose={onClose} maxWidth="max-w-[400px]" labelledBy="name-speaker-title">
      <div className="flex h-[450px] max-h-[80vh] flex-col">
        <h2 id="name-speaker-title" className="font-display text-lg font-semibold text-white">
          Who is speaking?
        </h2>
        <p className="mt-1 text-xs text-text-tertiary">
          {speaker.total > 0
            ? `Speaker ${speakerId} · ${speaker.total} segment${speaker.total === 1 ? '' : 's'} in this conversation`
            : `Speaker ${speakerId}`}
        </p>

        {unaddressable ? (
          <div className="mt-4 rounded-lg border border-warning/25 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
            This conversation is still syncing, so these segments can’t be named yet. Try again in a
            moment.
          </div>
        ) : partiallySynced ? (
          <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs leading-relaxed text-text-tertiary">
            {speaker.unsyncedCount} of this speaker’s {speaker.total} segments are still syncing and
            will keep their current label.
          </div>
        ) : null}

        <div className="mt-4 min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
          <button
            onClick={() => save({ type: 'is_user' })}
            disabled={saving || unaddressable}
            className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-white transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {/* decorative: the initial repeats the label next to it */}
            <span
              aria-hidden
              style={{ background: AVATAR_USER }}
              className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
            >
              Y
            </span>
            You
          </button>

          {people.map((p) => (
            <button
              key={p.id}
              onClick={() => save({ type: 'person_id', personId: p.id })}
              disabled={saving || unaddressable}
              className="flex w-full items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-left text-sm text-white transition-colors hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span
                aria-hidden
                style={{ background: AVATAR_PERSON }}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white"
              >
                {p.name.trim()[0]?.toUpperCase() ?? <User className="h-3.5 w-3.5" />}
              </span>
              <span className="truncate">{p.name}</span>
            </button>
          ))}

          {addingName === null ? (
            <button
              onClick={() => setAddingName('')}
              disabled={saving || unaddressable}
              className="flex w-full items-center gap-3 rounded-xl border border-dashed border-white/15 px-3 py-2.5 text-left text-sm text-text-tertiary transition-colors hover:border-white/30 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-white/15">
                <Plus className="h-3.5 w-3.5" />
              </span>
              Add Person
            </button>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault()
                addPerson(addingName)
              }}
              className="flex items-center gap-2 rounded-xl border border-white/15 bg-white/[0.04] px-3 py-2"
            >
              {/* autoFocus is intentional: this row only exists once the user clicks "Add Person" */}
              <input
                autoFocus
                value={addingName}
                onChange={(e) => setAddingName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setAddingName(null)
                }}
                placeholder="Name"
                aria-label="New person name"
                className="min-w-0 flex-1 bg-transparent text-sm text-white placeholder:text-text-quaternary focus:outline-none"
              />
              <button
                type="submit"
                disabled={!addingName.trim() || saving}
                className="rounded-lg bg-white px-2.5 py-1 text-xs font-medium text-bg-primary disabled:opacity-40"
              >
                Add
              </button>
            </form>
          )}
        </div>

        {speaker.total > 1 && (
          <label className="mt-3 flex cursor-pointer items-center gap-2.5 border-t border-white/10 pt-3 text-xs text-text-secondary">
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

        {saving && (
          <div className="mt-3 flex items-center gap-2 text-xs text-text-tertiary">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            Saving…
          </div>
        )}
      </div>
    </ModalShell>
  )
}
