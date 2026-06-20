// Turning a transcript segment's speaker fields into a readable label. Used by
// the live view, the stored-conversation view, and the screen-recording view, so
// they all agree.
//
// The backend conveys the speaker several ways: `is_user` (the wearer),
// `speaker` (a raw diarization tag like "SPEAKER_00" OR a real assigned name),
// `speaker_id` (a 0-based diarization index), and `person_name` (a matched
// person). Use `makeSpeakerLabeler` for a conversation — it works out, once for
// the whole set, how to identify the wearer; `speakerLabel` is the per-segment
// primitive it builds on.

type SpeakerFields = {
  is_user?: boolean
  speaker?: string
  speaker_id?: number
  person_name?: string
  // For local screen recordings: which stream the line came from. mic/system are
  // diarized independently, so their ids must not be treated as the same person.
  source?: string
  text?: string
}

// Matches a raw diarization tag like "SPEAKER_00" / "speaker_2" and captures its
// index. A real name ("Alice") or "Speaker 0" (with a space) won't match.
const DIARIZATION_TAG = /^speaker_?(\d+)$/i

function speakerIndex(seg: SpeakerFields): number | undefined {
  if (typeof seg.speaker_id === 'number') return seg.speaker_id
  const raw = seg.speaker?.trim()
  const m = raw ? DIARIZATION_TAG.exec(raw) : null
  return m ? Number(m[1]) : undefined
}

// A human-identified name: a matched person, or a non-tag `speaker` string.
function personName(seg: SpeakerFields): string | undefined {
  const matched = seg.person_name?.trim()
  if (matched) return matched
  const raw = seg.speaker?.trim()
  if (raw && !DIARIZATION_TAG.test(raw)) return raw
  return undefined
}

/**
 * Per-segment label. `isWearer` (computed per conversation) wins; otherwise a
 * named person, then a diarization "Speaker N", then "You" for the lone wearer
 * flag in single-speaker context.
 */
export function speakerLabel(
  seg: SpeakerFields,
  multiSpeaker = false,
  isWearer = false
): string | undefined {
  if (isWearer) return 'You'
  const name = personName(seg)
  const idx = speakerIndex(seg)

  if (multiSpeaker) {
    if (name) return name
    if (idx != null) return `Speaker ${idx}`
    if (seg.is_user) return 'You'
    return undefined
  }

  // Single-speaker context: the wearer is "You".
  if (seg.is_user) return 'You'
  if (name) return name
  if (idx != null) return `Speaker ${idx}`
  return undefined
}

// Stable key identifying a distinct speaker. Includes `source` so a mic Speaker 0
// and a system-audio Speaker 0 (numbered independently) count as two people.
function speakerKey(seg: SpeakerFields): string | null {
  const src = seg.source ? `${seg.source}:` : ''
  const idx = speakerIndex(seg)
  if (idx != null) return `${src}id${idx}`
  const name = personName(seg)
  if (name) return `${src}name:${name.toLowerCase()}`
  if (seg.is_user) return `${src}you`
  return null
}

/** How many distinct voices a set of segments contains. >1 ⇒ multi-speaker. */
export function countDistinctSpeakers(segs: SpeakerFields[]): number {
  const keys = new Set<string>()
  for (const s of segs) {
    const k = speakerKey(s)
    if (k) keys.add(k)
  }
  return keys.size
}

/**
 * Build a labeler for one conversation. It resolves the wearer once, then labels
 * each segment. Wearer detection (works for any signed-in user, no enrollment
 * assumptions):
 *   • Local recordings carry `source`: the mic stream is the wearer (there
 *     `is_user` is just the channel default), system audio is everyone else.
 *   • Server conversations have no `source` but a PER-SPEAKER `is_user` set by
 *     speaker identification — trust it, but only when it actually varies (if
 *     every segment is is_user=true the user has no profile match, so we can't
 *     single anyone out and just number the voices).
 */
export function makeSpeakerLabeler(
  segs: SpeakerFields[]
): (seg: SpeakerFields) => string | undefined {
  const multi = countDistinctSpeakers(segs) > 1
  const hasSource = segs.some((s) => s.source)
  const isUserVaries = new Set(segs.map((s) => !!s.is_user)).size > 1

  // Fallback wearer signal: a conversation the user records is THEIRS, and the
  // backend gives us no reliable per-speaker "is the wearer" flag (is_user is
  // either uniform or absent on the stored segments). So when there's no source
  // and is_user doesn't distinguish anyone, treat the PRIMARY voice — the lowest
  // diarization id, i.e. whoever opens the conversation — as the wearer ("You").
  // (The user confirmed they come through as speaker 0.)
  let primaryId: number | undefined
  if (!hasSource && !isUserVaries) {
    const ids = segs.map(speakerIndex).filter((n): n is number => n != null)
    if (ids.length) primaryId = Math.min(...ids)
  }

  const isWearer = (seg: SpeakerFields): boolean => {
    if (hasSource) return seg.source === 'mic'
    if (isUserVaries) return !!seg.is_user
    if (primaryId != null) return speakerIndex(seg) === primaryId
    return false
  }

  return (seg) => speakerLabel(seg, multi, isWearer(seg))
}
