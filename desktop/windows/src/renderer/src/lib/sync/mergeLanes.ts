/**
 * Merge the two screen-session lanes (mic + system audio) into one
 * `/v1/conversations/from-segments` transcript, ordered by the wall-clock
 * offsets stamped at arrival (see segmentRetention.ts).
 *
 * Speaker identity: the two transcribe-stream sockets each start their own
 * speaker numbering, and the mic/system distinction never reaches the backend
 * (both report source=desktop) — so system-lane speaker_ids are offset past the
 * mic lane's to keep them distinct, and system segments are never the user
 * (is_user=false): the user's voice arrives via the mic lane.
 */
import type { SyncSegment } from '../../../../shared/types'
import type { RetainedSegment } from './segmentRetention'

function toSyncSegment(seg: RetainedSegment, isUser: boolean, speakerId: number): SyncSegment {
  return {
    text: seg.text.trim(),
    speaker: seg.speaker ?? `SPEAKER_${speakerId}`,
    speaker_id: speakerId,
    is_user: isUser,
    person_id: seg.person_id ?? null,
    start: seg.start,
    end: Math.max(seg.start, seg.end)
  }
}

export function mergeLanes(mic: RetainedSegment[], system: RetainedSegment[]): SyncSegment[] {
  const micMaxSpeaker = mic.reduce((m, s) => Math.max(m, s.speaker_id ?? 0), 0)
  const systemOffset = micMaxSpeaker + 1

  const micMapped = mic
    .filter((s) => s.text.trim().length > 0)
    .map((s) => toSyncSegment(s, s.is_user, s.speaker_id ?? 0))
  // System-lane speaker labels are regenerated from the offset id: the stream's
  // own labels ("SPEAKER_0" …) would collide with the mic lane's numbering.
  const systemMapped = system
    .filter((s) => s.text.trim().length > 0)
    .map((s) => toSyncSegment({ ...s, speaker: undefined }, false, (s.speaker_id ?? 0) + systemOffset))

  // Stable merge of two already-chronological lists; mic wins ties so the
  // user's words lead when both lanes land on the same instant.
  const out: SyncSegment[] = []
  let i = 0
  let j = 0
  while (i < micMapped.length || j < systemMapped.length) {
    const takeMic =
      j >= systemMapped.length || (i < micMapped.length && micMapped[i].start <= systemMapped[j].start)
    out.push(takeMic ? micMapped[i++] : systemMapped[j++])
  }
  return out
}
