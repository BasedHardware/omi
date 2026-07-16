// Close-code classification for the warm hub socket (Track 2 / A7c).
//
// A 1:1 port of the classification half of macOS `RealtimeHubCloseClassifier`
// (RealtimeHubController.swift:27-65). It answers the ONE question the resilience
// policy needs: was this socket close an EXPECTED idle teardown (Gemini idle-closes
// a warm session with WS 1008 after ~2.5 min of no input), or a real failure? The
// two are handled very differently by `HubController`:
//   * expected_idle_teardown → re-warm WITHOUT spending a reconnect strike (an idle
//     cycle must keep the socket coming back so the next press is warm, not cold).
//   * policy_fast / transient → a genuine failure: bounded re-warm capped by the
//     strike budget so a dead endpoint (revoked token, provider outage) isn't hammered.
//
// Provider auth/quota classification (Mac's `CredentialHealthManager` close path) is
// deliberately NOT ported here — it is the dependency for cross-provider failover
// (A7c "LATER" item D), which this MINIMAL slice does not implement. So every 1008
// that isn't an idle teardown is `policy_fast`, and every non-1008 close is
// `transient`. Pure + input-only, exercised hermetically.

/** A 1008 that arrives with no active turn after the socket has lived at least this
 *  long is the provider's expected idle-close, not a failure (Mac idleTeardownThreshold). */
export const HUB_IDLE_TEARDOWN_THRESHOLD_MS = 60_000

export type HubCloseCategory = 'expected_idle_teardown' | 'policy_fast' | 'transient'

export type HubCloseInput = {
  /** The `websocket closed (<code>) …` message BaseHubSession forwards. */
  readonly message: string
  /** The WS close code, threaded structurally from `BaseHubSession.onClose`. When
   *  absent (an OpenAI error frame, an audio-init failure) the code is parsed out of
   *  `message` as a fallback, matching Mac's string parse. */
  readonly closeCode?: number
  /** How long the socket had been connected before the close (0 if it never opened). */
  readonly aliveForMs: number
  /** Whether a PTT turn was in flight when the socket closed. */
  readonly hasActiveTurn: boolean
}

/** Parse the numeric close code out of a `websocket closed (1008) …` message — the
 *  fallback when a structured code wasn't threaded (Mac string-parses too). */
function parseCloseCode(message: string): number | undefined {
  const m = /websocket closed \((\d+)\)/.exec(message)
  return m ? Number(m[1]) : undefined
}

/** Classify a warm-socket close. See the module header for the policy each category
 *  drives. Mirrors `RealtimeHubCloseClassifier.category` (RealtimeHubController.swift:38-60),
 *  minus the auth/quota branch (deferred with failover). */
export function classifyHubClose(input: HubCloseInput): HubCloseCategory {
  const code = input.closeCode ?? parseCloseCode(input.message)
  // Only a 1008 policy close is ever an idle teardown (Mac :45). Any other code
  // (1006 abnormal, 1011, a transport drop) is a transient failure → bounded re-warm.
  if (code !== 1008) return 'transient'
  // Mac :58 — a 1008 with no active turn after the socket has lived a while is the
  // expected provider idle-close; a fast 1008 (or one during a turn) is a policy reject.
  if (!input.hasActiveTurn && input.aliveForMs >= HUB_IDLE_TEARDOWN_THRESHOLD_MS) {
    return 'expected_idle_teardown'
  }
  return 'policy_fast'
}

/** Whether a re-warm for this category spends a strike. An expected idle teardown is
 *  not a failure, so it re-warms freely (an idle user's socket keeps coming back warm);
 *  a real failure is capped by the strike budget so a dead endpoint isn't hammered. */
export function consumesStrike(category: HubCloseCategory): boolean {
  return category !== 'expected_idle_teardown'
}

// NOTE: Mac's classifier also gates Sentry reporting per category
// (`shouldReportToSentry` :62). Windows has no Sentry path on these closes — an idle
// close's `onError` no-ops at the driver (turnID is null) — so no logging-suppression
// helper is wired here. Add one (classify-gated) only if a real close-logging path is
// introduced; an unused mirror of Mac would just mislead.
