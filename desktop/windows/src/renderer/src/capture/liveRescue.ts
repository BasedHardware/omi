// Pure helpers for the always-on mic session's reconnect + from-segments rescue
// (see liveMicSession). Kept side-effect-free so the backoff schedule and the
// segment mapping are exhaustively unit-testable in node.
import { isQuotaExhaustedMessage } from '../lib/transcriptionClient'
import type { BackendSegment, SyncSegment } from '../../../shared/types'

// Reconnect budget. A dropped /v4/listen resumes the SAME conversation (via
// client_conversation_id) with capped exponential backoff before giving up — a
// brief network blip must not end the recording. (Previously any close was
// terminal: 3 attempts, no resume, then error-stop.)
export const MAX_RECONNECT_ATTEMPTS = 10
const RECONNECT_MAX_MS = 32_000
// A 429 is the server explicitly saying "slow down", so a rate-limited drop backs
// off from at least this floor rather than the usual 2s first step.
const RATE_LIMIT_FLOOR_MS = 5_000
// Up-to jitter added to every reconnect delay, decorrelating retries during an
// account-wide 429 storm so the lanes don't all wake at the same instant.
const RECONNECT_JITTER_MS = 1_000

/** Capped exponential backoff for the Nth reconnect attempt (1-based): 2s, 4s, 8s,
 *  16s, 32s, then 32s — matching the macOS reference (min(2^n, 32s), no jitter).
 *  The base curve; the live loop uses reconnectDelayJitteredMs. */
export function reconnectDelayMs(attempt: number): number {
  const n = Math.max(1, attempt)
  return Math.min(RECONNECT_MAX_MS, 2 ** n * 1000)
}

/** Reconnect delay actually used by the live loop: the capped-exponential base plus
 *  decorrelating jitter, with a longer floor when the drop was a 429 so we don't
 *  hammer a server that just rate-limited us. `rand` is injectable for tests. */
export function reconnectDelayJitteredMs(
  attempt: number,
  opts: { rateLimited?: boolean; rand?: () => number } = {}
): number {
  const rand = opts.rand ?? Math.random
  const base = opts.rateLimited
    ? Math.min(RECONNECT_MAX_MS, Math.max(reconnectDelayMs(attempt), RATE_LIMIT_FLOOR_MS))
    : reconnectDelayMs(attempt)
  return Math.round(base + rand() * RECONNECT_JITTER_MS)
}

/** Whether a transcription error is worth reconnecting for. Quota/entitlement
 *  exhaustion (1008 / trial_expired) and a missing sign-in are terminal —
 *  reconnecting just re-hits the same wall, so surface them at once instead of
 *  burning the whole backoff budget (~55s) first. Everything else (network drops,
 *  timeouts, transient server closes) is retryable. */
export function isRetryableDropError(message: string): boolean {
  return !isQuotaExhaustedMessage(message) && !/not signed in|requires sign-in/i.test(message)
}

/** Whether a retryable drop was a backend rate-limit. The ws handshake surfaces a
 *  429 rejection as "Unexpected server response: 429", so match a standalone 429. */
export function isRateLimitedDropError(message: string): boolean {
  return /\b429\b/.test(message)
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
