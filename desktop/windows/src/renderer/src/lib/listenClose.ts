// Pure helpers for classifying v4/listen quota / trial-expired signals into a
// clear, user-facing message. Kept dependency-free (no firebase/electron) so it
// can be unit-tested under node Vitest, unlike transcriptionClient (which pulls
// firebase at import).
//
// Background: the Omi backend paywalls CONNECTED desktop sessions (source=desktop)
// once the 3-day free trial is used up (backend utils/subscription.is_trial_paywalled).
// It signals this two ways, in order:
//   1. a `freemium_threshold_reached` event with remaining_seconds: 0, then
//   2. a WebSocket close with code 1008 and reason "trial_expired".
// Both must resolve to the SAME message: the session surfaces errors via a single
// "latest wins" sink (usePushToTalk.setError), so if the two signals produced
// different strings the generic close would clobber the meaningful one — which is
// exactly why the user only ever saw the cryptic "closed (1008)".

export const TRIAL_EXPIRED_MESSAGE =
  'Your free Omi trial has expired. Transcription is no longer available.'

// The backend also 1008-rejects a connected session when it can't tie the request
// to a known account: reason "Bad uid" (no uid derived from the token) or
// "Bad user" (the uid has no backend user record — e.g. a brand-new account whose
// record isn't provisioned yet). Both are identity problems the user can often
// clear by re-authenticating.
export const ACCOUNT_REJECTED_MESSAGE =
  "Omi couldn't verify your account, so transcription can't start. Try signing out and back in."

/** A post-connect 1008 close whose reason names the trial paywall. */
export function isTrialExpiredClose(code: number, reason: string): boolean {
  return code === 1008 && /trial_expired/i.test(reason ?? '')
}

/** A post-connect 1008 close where the backend rejected the account identity. */
export function isAccountRejectedClose(code: number, reason: string): boolean {
  return code === 1008 && /^bad (uid|user)$/i.test((reason ?? '').trim())
}

// User-facing messages that are already complete sentences — callers surface them
// verbatim instead of wrapping them in generic "transcription stopped" framing.
const COMPLETE_MESSAGES = new Set<string>([TRIAL_EXPIRED_MESSAGE, ACCOUNT_REJECTED_MESSAGE])

/** True if `message` is one of the ready-to-show, complete user-facing strings. */
export function isCompleteMessage(message: string): boolean {
  return COMPLETE_MESSAGES.has(message)
}

/**
 * Map a post-connect WebSocket close to a user-facing message. Trial-expired gets
 * the clear, shared message; every other close surfaces the code AND the backend's
 * reason string, so an unexpected 1008 (e.g. "Bad uid", "Bad user") is diagnosable
 * instead of a bare "(1008)".
 */
export function closeMessage(code: number, reason: string): string {
  if (isTrialExpiredClose(code, reason)) return TRIAL_EXPIRED_MESSAGE
  if (isAccountRejectedClose(code, reason)) return ACCOUNT_REJECTED_MESSAGE
  const r = (reason ?? '').trim()
  return r ? `Omi /v4/listen closed (${code}): ${r}` : `Omi /v4/listen closed (${code})`
}

/**
 * The backend emits `freemium_threshold_reached` right before the trial_expired
 * close. Treat a depleted (<= 0 remaining, or missing field) one as trial-expired
 * too, so we still react if the typed event lands but the close reason doesn't.
 * An early-warning variant with remaining_seconds > 0 is NOT exhaustion.
 */
export function isQuotaExhaustedEvent(ev: {
  type: string
  raw: Record<string, unknown>
}): boolean {
  if (ev.type !== 'freemium_threshold_reached') return false
  const remaining = ev.raw.remaining_seconds
  return typeof remaining !== 'number' || remaining <= 0
}
