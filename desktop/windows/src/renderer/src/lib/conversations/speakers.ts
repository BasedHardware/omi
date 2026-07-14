// Speaker presentation + naming logic for the conversation transcript, ported
// from the macOS app (TranscriptSegmentView / NameSpeakerSheet). Pure — no React,
// no network — so the color/initial/segment-id rules are unit-testable on their
// own.
//
// The palette is Mac's `OmiColors.speakerColors` + `userBubble`, ported verbatim
// per the Track 4 ruling (TRACK4-PLAN.md). Note INV-UI-1's no-purple ratchet
// (.github/scripts/check_brand_ui.py) only scans desktop/macos, app/lib and web/
// — never desktop/windows — so these are the intended values here, not debt.

import type { Person, TranscriptSegment } from '../omiApi.generated'

/** Mac's 6 dark speaker tones, indexed by `speakerId % 6`. */
export const SPEAKER_COLORS = [
  '#2D3748', // 0 dark blue-gray
  '#1E3A5F', // 1 navy
  '#2D4A3E', // 2 dark teal
  '#4A3728', // 3 dark brown
  '#3D2E4A', // 4 dark purple
  '#4A3A2D' // 5 dark amber
] as const

/** Fill for the user's own bubbles (Mac `OmiColors.userBubble`). */
export const USER_BUBBLE = '#43389F'

/** Avatar fill for a speaker nobody has named yet. */
export const AVATAR_UNNAMED = '#35343B'

/** Mac's `purplePrimary` — the avatar fill for the user (and, at 30%, for a
 *  named person). The Windows token set has no purple accent (Track 5 made
 *  `--accent` white), so this ports Mac's literal value rather than a token. */
export const AVATAR_NAMED = '#8B5CF6'
export const AVATAR_NAMED_SOFT = 'rgba(139, 92, 246, 0.3)'

/**
 * Pull the numeric speaker index out of a segment's speaker string:
 * `"SPEAKER_04"` → `4`. Anything unparseable (null, "", "SPEAKER_XX") → `0`,
 * matching Mac's default.
 */
export function parseSpeakerId(speaker?: string | null): number {
  const m = /(\d+)/.exec(speaker ?? '')
  if (!m) return 0
  const n = Number.parseInt(m[1], 10)
  return Number.isFinite(n) && n >= 0 ? n : 0
}

/** The speaker index for a segment — the speaker string wins (Mac's rule), with
 *  the structured `speaker_id` as a fallback when there is no string. */
export function speakerIdOf(seg: Pick<TranscriptSegment, 'speaker' | 'speaker_id'>): number {
  if (seg.speaker) return parseSpeakerId(seg.speaker)
  return seg.speaker_id ?? 0
}

/** Bubble fill: the user always gets `userBubble`; everyone else cycles the
 *  6-tone palette by `speakerId % 6`. */
export function bubbleColor(speakerId: number, isUser: boolean): string {
  if (isUser) return USER_BUBBLE
  const i = ((speakerId % SPEAKER_COLORS.length) + SPEAKER_COLORS.length) % SPEAKER_COLORS.length
  return SPEAKER_COLORS[i]
}

/** Single character shown in the 32px avatar circle: "Y" for the user, the first
 *  letter of a named person, else the raw speaker digit. */
export function avatarInitial(
  speakerId: number,
  isUser: boolean,
  personName?: string | null
): string {
  if (isUser) return 'Y'
  const first = personName?.trim()?.[0]
  if (first) return first.toUpperCase()
  return String(speakerId)
}

/** Avatar fill, mirroring `avatarInitial`'s three cases. */
export function avatarFill(isUser: boolean, personName?: string | null): string {
  if (isUser) return AVATAR_NAMED
  if (personName?.trim()) return AVATAR_NAMED_SOFT
  return AVATAR_UNNAMED
}

/** Display label under/over a bubble. */
export function speakerLabel(
  speakerId: number,
  isUser: boolean,
  personName?: string | null
): string {
  if (isUser) return 'You'
  const name = personName?.trim()
  if (name) return name
  return `Speaker ${speakerId}`
}

/** Look up the name assigned to a segment's speaker, if any. */
export function personNameFor(
  seg: Pick<TranscriptSegment, 'person_id'>,
  people: Person[]
): string | null {
  if (!seg.person_id) return null
  return people.find((p) => p.id === seg.person_id)?.name ?? null
}

export type SpeakerSegments = {
  /** Real backend ids — the only ones safe to send to assign-bulk. */
  ids: string[]
  /** How many of this speaker's segments have no backend id yet (unsynced). */
  unsyncedCount: number
  /** Total segments attributed to this speaker in this conversation. */
  total: number
}

/**
 * Collect the segments belonging to one speaker, split into ones the server can
 * actually address and ones it can't.
 *
 * Mac bug we deliberately do NOT port: when a segment has no backend id, Mac
 * substitutes a synthetic `"#index:N"` string. The server resolves segments by
 * real id, so those entries match nothing and the PATCH silently no-ops — the
 * user renames a speaker and nothing happens, with no error. Here, a segment
 * without a real id is never turned into an id; it is counted as unsynced so the
 * caller can disable the action or say so plainly.
 */
export function collectSpeakerSegments(
  segments: TranscriptSegment[],
  speakerId: number
): SpeakerSegments {
  const mine = segments.filter((s) => !s.is_user && speakerIdOf(s) === speakerId)
  const ids: string[] = []
  let unsyncedCount = 0
  for (const s of mine) {
    const id = s.id?.trim()
    if (id) ids.push(id)
    else unsyncedCount++
  }
  return { ids, unsyncedCount, total: mine.length }
}

/** The segment ids a save should target: just the tapped one, or every synced
 *  segment from that speaker when "also tag N others" is on. */
export function segmentIdsToAssign(
  segments: TranscriptSegment[],
  tapped: TranscriptSegment,
  applyToAll: boolean
): string[] {
  if (applyToAll) return collectSpeakerSegments(segments, speakerIdOf(tapped)).ids
  const id = tapped.id?.trim()
  return id ? [id] : []
}
