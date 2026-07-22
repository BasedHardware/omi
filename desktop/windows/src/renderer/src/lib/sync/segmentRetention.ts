/**
 * Raw-segment retention for screen-session lanes (mic + system).
 *
 * The display path (segmentToLine → TranscriptLine) throws away everything the
 * from-segments POST needs (start/end/is_user/speaker_id/person_id), so each
 * lane keeps its raw BackendSegments here alongside the display lines.
 *
 * WALL-CLOCK STAMPING — the transcribe-stream endpoint's timestamps track
 * cumulative AUDIO time: the client's VAD gate drops silence before feeding, so
 * a segment spoken 5 minutes in can carry `start: 12`. We therefore re-derive
 * session-relative wall-clock offsets at ARRIVAL: each batch is anchored so its
 * latest stream `end` maps to "now - sessionStart", and the stream timestamps
 * are used only for ordering/relative spacing WITHIN the batch. Monotonicity
 * against previously-stored segments is enforced so re-ordered arrivals can't
 * produce a time-travelling transcript.
 *
 * The endpoint also re-emits a segment (same id) as it refines around pauses —
 * those upsert in place: text/speaker fields refresh, the original wall-clock
 * start is kept (re-stamping a refinement would smear it to the refinement's
 * arrival time), and the duration extends if the stream duration grew.
 */
import type { BackendSegment } from '../../../../shared/types'

export type RetainedSegment = {
  id?: string
  text: string
  speaker?: string
  speaker_id?: number
  is_user: boolean
  person_id?: string
  /** Wall-clock session-relative seconds (derived at arrival — see above). */
  start: number
  end: number
}

export type SegmentStore = {
  /** Record a batch of backend segments that arrived at `nowMs` (epoch ms). */
  add: (segments: BackendSegment[], nowMs: number) => void
  /** All retained segments, in stored (chronological) order. */
  list: () => RetainedSegment[]
}

export function createSegmentStore(sessionStartMs: number): SegmentStore {
  const stored: RetainedSegment[] = []
  const byId = new Map<string, RetainedSegment>()

  const add = (segments: BackendSegment[], nowMs: number): void => {
    if (segments.length === 0) return
    const arrival = Math.max(0, (nowMs - sessionStartMs) / 1000)

    const fresh: BackendSegment[] = []
    for (const seg of segments) {
      const existing = seg.id ? byId.get(seg.id) : undefined
      if (existing) {
        // Refinement of an already-stored segment: refresh content, keep the
        // original wall-clock start, extend duration if the stream's grew.
        existing.text = seg.text
        if (seg.speaker !== undefined) existing.speaker = seg.speaker
        if (seg.speaker_id !== undefined) existing.speaker_id = seg.speaker_id
        existing.is_user = seg.is_user
        if (seg.person_id !== undefined) existing.person_id = seg.person_id
        const streamDur = Math.max(0, (seg.end ?? 0) - (seg.start ?? 0))
        existing.end = Math.max(existing.end, existing.start + streamDur)
      } else {
        fresh.push(seg)
      }
    }
    if (fresh.length === 0) return

    // Anchor the batch: its latest stream `end` corresponds to ~arrival time.
    // Stream timestamps position segments within the batch relative to that.
    fresh.sort((a, b) => (a.start ?? 0) - (b.start ?? 0) || (a.end ?? 0) - (b.end ?? 0))
    const anchorEnd = Math.max(...fresh.map((s) => s.end ?? 0))
    let floor = stored.length > 0 ? stored[stored.length - 1].start : 0
    for (const seg of fresh) {
      const start = Math.max(0, floor, arrival - (anchorEnd - (seg.start ?? 0)))
      const end = Math.max(start, arrival - (anchorEnd - (seg.end ?? 0)))
      const retained: RetainedSegment = {
        id: seg.id,
        text: seg.text,
        speaker: seg.speaker,
        speaker_id: seg.speaker_id,
        is_user: seg.is_user,
        person_id: seg.person_id,
        start,
        end
      }
      stored.push(retained)
      if (seg.id) byId.set(seg.id, retained)
      floor = start
    }
  }

  return { add, list: () => stored.map((s) => ({ ...s })) }
}
