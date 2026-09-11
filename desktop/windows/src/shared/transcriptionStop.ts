// Why a transcription lane stopped, classified from its message text. Pure and
// string-based so the capture renderer (reconnect decisions, usage popup) and
// main (the meeting toast, which only receives the message) share one rule.
//
// The backend closes with WS 1008 for many unrelated reasons — trial_expired,
// "Daily transcription budget exhausted", "Idle timeout: no audio for 60s",
// rate limits, a finalized session — so the code alone says nothing. Only the
// close REASON separates an entitlement stop from a benign idle teardown.

export type TranscriptionStopKind =
  /** Account not entitled to cloud STT (free quota / trial used up). Terminal. */
  | 'quota'
  /** The rolling 24h voice-transcription duration budget is spent. Terminal, and
   *  plan-independent: upgrading does not lift it, so never offer an upgrade. */
  | 'daily_limit'
  /** Anything else — network drop, idle timeout, rate limit, transient server
   *  close, source failure. Retry-worthiness is decided by the caller. */
  | 'generic'

export const QUOTA_MESSAGE =
  'free Omi transcription quota is used up (1008) — add an Omi subscription or sign in with an entitled account to keep transcribing'

export const DAILY_LIMIT_MESSAGE =
  "Omi's daily voice transcription limit is used up — it frees up again over a rolling 24 hours"

/** Classify a backend close reason (not the code — see file comment). */
export function classifyCloseReason(reason: string): TranscriptionStopKind {
  if (/budget exhausted/i.test(reason)) return 'daily_limit'
  if (/trial_expired|freemium|quota/i.test(reason)) return 'quota'
  return 'generic'
}

/** Classify a surfaced stop/error message. Recognizes this module's own messages
 *  plus raw reasons carried inside pass-through messages (`… closed (1008) <reason>`). */
export function classifyTranscriptionStop(message: string): TranscriptionStopKind {
  if (message.includes(DAILY_LIMIT_MESSAGE)) return 'daily_limit'
  return classifyCloseReason(message)
}
