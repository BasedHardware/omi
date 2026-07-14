// Speaker presentation + naming logic for the conversation transcript, ported
// from the macOS app (TranscriptSegmentView / NameSpeakerSheet). Pure — no React,
// no network — so the color/initial/segment-id rules are unit-testable on their
// own.
//
// The colors themselves live in ONE place — lib/macPalette.ts.
// Import them from there; never re-declare a hex inline and never promote one to a
// global token (see that module's header for why).

import type { Person, TranscriptSegment } from '../omiApi.generated'
import {
  AVATAR_PERSON,
  AVATAR_UNNAMED,
  AVATAR_USER,
  SPEAKER_COLORS,
  USER_BUBBLE
} from '../macPalette'

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
  if (isUser) return AVATAR_USER
  if (personName?.trim()) return AVATAR_PERSON
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
