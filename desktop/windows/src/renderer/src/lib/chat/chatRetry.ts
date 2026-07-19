// Bounded auto-retry policy for a rate-limited (HTTP 429) chat SEND. Pure and
// engine-agnostic, so both send paths in useChat — the pi_mono kernel door
// (tryKernelChat) and the legacy_sse `/v2/messages` fetch — apply the exact same
// policy off one source of truth.
//
// Why this exists: this account hits recurring api.omi.me 429 "storms" (see
// rateLimitDegraded.ts). Before this, a typed send that got a single 429 surfaced
// an error immediately, so the user had to manually re-send several times before
// one landed. A 429 is transient by definition (a rate limit, not a monthly cap —
// the monthly cap is a separate PRE-send gate, chatQuotaGate.ts, that never sends
// and so never 429s here), so the correct behavior is a short backoff-retry, the
// same posture apiClient already takes for its 429/503 responses. Only when the
// retries are exhausted does the friendly "servers are busy" copy show.

import { chatErrorStatus } from './chatErrorCopy'

/** How many times a rate-limited (429) send is auto-retried before the friendly
 *  "busy" copy shows. Small + bounded — a sustained limit still surfaces quickly,
 *  and the total added wait (see chatRateLimitBackoffMs) stays well under the chat
 *  watchdog. */
export const CHAT_RATE_LIMIT_RETRIES = 2

/** Interim line shown in the pending assistant bubble WHILE a rate-limited send is
 *  backing off to retry. Honest + non-blaming, consistent with DegradedModeNotice
 *  ("Omi’s servers are busy."). */
export const CHAT_BUSY_RETRY_INTERIM = 'Omi’s servers are busy. Retrying…'

/**
 * True when a failed send should be auto-retried: a transient backend rate limit
 * (HTTP 429). Keys off chatErrorStatus — the SAME parse friendlyChatError uses to
 * pick its copy — so the retry predicate and the shown message can never drift.
 * Any other failure (401/403 auth, 5xx, offline, a generic model error) is NOT
 * retried here and surfaces immediately as it does today.
 */
export function isRetryableChatRateLimit(raw: string | null | undefined): boolean {
  return chatErrorStatus(raw) === 429
}

/**
 * Backoff (ms) before the Nth (1-based) rate-limit retry: exponential with a small
 * cap plus jitter (1s, 2s, … capped at 4s), matching apiClient's 429 backoff shape.
 * (We deliberately retry only 429 here, not 503 — narrower than apiClient's set, a
 * conservative scope for this chat-send path.) The jitter avoids a thundering-herd
 * re-send when several surfaces retry at once.
 */
export function chatRateLimitBackoffMs(attempt: number): number {
  return Math.min(1000 * 2 ** (attempt - 1), 4000) + Math.floor(Math.random() * 300)
}

/**
 * Fixed-field fallback/telemetry properties for a chat-send rate-limit degrade
 * path, matching the shared `fallback_triggered` shape (AGENTS.md "Fallback /
 * resilience telemetry", same event the realtime hub emits). Pure — the caller
 * passes it to `trackEvent` — so silent UX healing stays visible to ops without a
 * one-off counter. Emitted at most once per send, ONLY when a 429 retry actually
 * happened: `recovered` when the send ultimately succeeded, `exhausted` when the
 * bounded retries ran out (the "servers are busy" copy shown). No provider/mode
 * change here, so from/to are `none`; the rate limit is the `reason`.
 */
export function chatRateLimitFallbackProps(
  outcome: 'recovered' | 'exhausted',
  engine: 'pi_mono' | 'legacy_sse',
  attempts: number
): Record<string, unknown> {
  return {
    component: 'chat_send',
    from: 'none',
    to: 'none',
    reason: 'rate_limited',
    outcome,
    engine,
    attempts
  }
}
