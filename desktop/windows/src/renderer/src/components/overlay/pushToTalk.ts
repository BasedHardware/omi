// Pure helpers for the overlay's hold-Space push-to-talk. Kept free of React /
// DOM / audio so they can be unit-tested under node Vitest; the effectful parts
// (timers, mic capture, analyser, transcription) live in usePushToTalk.
import type { TranscriptLine } from '../../../../shared/types'

/**
 * How long Space must be held (ms) before it flips from "type a space" to
 * "push-to-talk". Tuned above a normal keypress (~80–150ms) with margin so fast
 * typing never trips it, while a deliberate hold still feels responsive.
 */
export const HOLD_THRESHOLD_MS = 350

/** True when a press lasted long enough to count as a hold (vs a quick tap). */
export function isHold(downAt: number, upAt: number, thresholdMs = HOLD_THRESHOLD_MS): boolean {
  return upAt - downAt >= thresholdMs
}

/** Tunables for {@link shouldFinalize}. */
export type FinalizeConfig = {
  /** Hard cap since release — always commit past this, whatever the state. */
  maxMs: number
  /** Nothing captured (no voice, no segment) ⇒ end this quickly (fast tap / silence). */
  noVoiceGraceMs: number
  /** Mic quiet at least this long ⇒ the user has stopped speaking. */
  silenceMs: number
  /** ...and no new segment for at least this long ⇒ the backend has caught up. */
  settleMs: number
  /**
   * Minimum time since release before the silence/settle path may commit. Omi's
   * v4/listen delivers its trailing FINAL segment ~1.8s late with NO interim, so
   * a quick release can otherwise commit in the GAP before the tail lands —
   * dropping the last words. This floor holds the commit open long enough for
   * that trailing segment to arrive (the hard cap `maxMs` still bounds the wait).
   */
  trailingGraceMs: number
}

/** Live inputs to the finalize decision, sampled each poll after Space is released. */
export type FinalizeState = {
  /** Time since the key was released. */
  elapsedMs: number
  /** Whether the mic ever detected speech this hold. */
  everVoiced: boolean
  /** Time since the mic last had speech-level energy. */
  silentForMs: number
  /** Time since the last accepted segment, or null if none has arrived this hold. */
  sinceLastSegmentMs: number | null
}

/**
 * Decide whether to commit the push-to-talk capture. We wait until the user has
 * actually stopped speaking (VAD silence) AND the backend's trailing segment has
 * landed and settled — rather than a fixed delay stacked on top of the ~1.8s
 * backend latency. A capture that produced nothing ends quickly; a hard cap always
 * ends it eventually.
 */
export function shouldFinalize(s: FinalizeState, cfg: FinalizeConfig): boolean {
  if (s.elapsedMs >= cfg.maxMs) return true
  // Nothing captured at all → end fast (e.g. a key drop so quick no audio was caught).
  if (!s.everVoiced && s.sinceLastSegmentMs === null) return s.elapsedMs >= cfg.noVoiceGraceMs
  // Otherwise: hold the commit open until the backend's trailing segment has had
  // time to arrive (trailingGraceMs), THEN require you've stopped talking AND the
  // last segment has settled. Without the grace, a quick release commits in the
  // gap before the ~1.8s-late trailing segment lands and drops the last words.
  return (
    s.elapsedMs >= cfg.trailingGraceMs &&
    s.silentForMs >= cfg.silenceMs &&
    s.sinceLastSegmentMs !== null &&
    s.sinceLastSegmentMs >= cfg.settleMs
  )
}

/**
 * Merge a transcript line into the accumulated list IN PLACE. v4/listen re-sends
 * the same segment (same `id`) as it refines it and re-emits earlier segments
 * around pauses; appending those would duplicate speech, so a line whose `id`
 * matches an existing one REPLACES it. Lines without an id are treated as
 * distinct and appended.
 */
export function upsertLine(lines: TranscriptLine[], line: TranscriptLine): void {
  const idx = line.id != null ? lines.findIndex((x) => x.id === line.id) : -1
  if (idx >= 0) lines[idx] = line
  else lines.push(line)
}

/**
 * Flatten finalized transcript lines + any in-progress interim text into the
 * single string we auto-send as the chat message. Speaker labels are dropped —
 * it's all the user's own speech — and surrounding whitespace is collapsed so an
 * empty/whitespace-only capture yields '' (caller skips sending).
 */
export function assembleTranscript(lines: TranscriptLine[], interim: string): string {
  return [...lines.map((l) => l.text), interim]
    .map((s) => s.trim())
    .filter(Boolean)
    .join(' ')
    .trim()
}
