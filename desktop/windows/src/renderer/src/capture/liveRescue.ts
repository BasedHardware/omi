// Pure helpers for the always-on mic session's reconnect + from-segments rescue
// (see liveMicSession). Kept side-effect-free so the backoff schedule and the
// segment mapping are exhaustively unit-testable in node.
import type { BackendSegment, SyncSegment } from '../../../shared/types'

// Reconnect budget. A dropped /v4/listen resumes the SAME conversation (via
// client_conversation_id) with capped exponential backoff before giving up — a
// brief network blip must not end the recording. (Previously any close was
// terminal: 3 attempts, no resume, then error-stop.)
export const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_MAX_MS = 32_000

/** Capped exponential backoff for the Nth reconnect attempt (1-based): 2s, 4s, 8s,
 *  16s, 32s, then 32s — matching the macOS reference (min(2^n, 32s), no jitter). */
export function reconnectDelayMs(attempt: number): number {
  const n = Math.max(1, attempt)
  return Math.min(RECONNECT_MAX_MS, 2 ** n * 1000)
}

/** Whether a transcription error is worth reconnecting for. Quota/entitlement
 *  exhaustion (1008 / trial_expired) and a missing sign-in are terminal —
 *  reconnecting just re-hits the same wall, so surface them at once instead of
 *  burning the whole backoff budget (~55s) first. Everything else (network drops,
 *  timeouts, transient server closes) is retryable. */
export function isRetryableDropError(message: string): boolean {
  return !/quota|1008|trial_expired|not signed in|requires sign-in/i.test(message)
}

/**
 * Map retained /v4/listen raw segments to the from-segments wire shape. Unlike the
 * transcribe-stream lanes (whose timestamps compress silence, so segmentRetention
 * re-derives wall-clock offsets), /v4/listen segment start/end are already real
 * conversation-relative seconds — pass them through verbatim.
 */
export function toSyncSegments(segs: BackendSegment[]): SyncSegment[] {
  return segs.map((s) => ({
    text: s.text,
    speaker: s.speaker ?? null,
    speaker_id: s.speaker_id ?? null,
    is_user: s.is_user,
    person_id: s.person_id ?? null,
    start: s.start,
    end: s.end
  }))
}

/** A speaker-prefixed transcript string for the rescued conversation's preview. */
export function segmentsToTranscript(segs: BackendSegment[]): string {
  return segs
    .map((s) => (s.speaker ? `${s.speaker}: ${s.text}` : s.text))
    .filter(Boolean)
    .join('\n')
    .trim()
}

export type SegmentRetainer = {
  /** Absorb a backend batch. /v4/listen re-emits a segment (same id) as it refines
   *  around pauses; those upsert in place so the retained copy never duplicates. */
  add: (segs: BackendSegment[]) => void
  /** All retained segments in arrival order (defensive copies). */
  list: () => BackendSegment[]
}

export function createSegmentRetainer(): SegmentRetainer {
  const ordered: BackendSegment[] = []
  const byId = new Map<string, BackendSegment>()
  return {
    add(segs): void {
      for (const s of segs) {
        const existing = s.id ? byId.get(s.id) : undefined
        if (existing) {
          Object.assign(existing, s) // refine in place (existing is the same ref held in `ordered`)
        } else {
          ordered.push(s)
          if (s.id) byId.set(s.id, s)
        }
      }
    },
    list: () => ordered.map((s) => ({ ...s }))
  }
}
