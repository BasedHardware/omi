// Maps a raw chat send/stream failure to friendly, plain-English copy for the
// assistant bubble — never the raw `Error: <technical string>`. Pure, and kept
// out of useChat so the hook file stays clean (mirrors detailErrors.ts).
//
// Mac parity: ChatErrorState.userFacingSummary — authRequired → "Please sign in
// to continue." The chat-send paths (legacy_sse catch, pi_mono generic/catch)
// feed the raw error/exception message through here so a technical string never
// reaches a bubble.
//
// Classifies by pattern on the raw string plus the live connectivity signal.
// Order matters: an explicit HTTP status wins over the offline heuristic — a 401
// means we reached the server (a sign-in problem), not that we're offline. When
// no class is recognized the copy is the friendly generic, so an unmatched error
// degrades to a safe message instead of leaking the raw text.
/**
 * Extract a structured HTTP status from a raw chat error string, or null when
 * none is present. legacy_sse throws `HTTP <status>`; a managed-cloud (pi_mono)
 * error may read `status code <n>`. Exported so the send-path retry policy
 * (chatRetry.ts) classifies a 429 off the EXACT same parse this copy does — the
 * two can never disagree about what is a rate limit.
 */
export function chatErrorStatus(raw: string | null | undefined): number | null {
  const statusMatch = (raw ?? '').match(/(?:HTTP|status(?:\s+code)?)\s+(\d{3})/i)
  return statusMatch ? Number(statusMatch[1]) : null
}

export function friendlyChatError(raw: string): string {
  const msg = raw ?? ''

  const status = chatErrorStatus(msg)

  if (status === 401 || status === 403) {
    // Mac authRequired parity — token expired / missing.
    return 'Please sign in to continue.'
  }
  if (status === 429) {
    // A 429 reaches this copy only AFTER the send path's bounded auto-retry is
    // exhausted (chatRetry.ts), so it means a sustained rate limit — not a fast
    // typer. Frame it as the server being busy (matching DegradedModeNotice),
    // NOT as the user sending "too quickly", which wrongly blamed the user on
    // their first message during one of this account's 429 storms.
    return 'Omi’s servers are busy. Try again in a moment.'
  }
  if (status !== null && status >= 500 && status <= 599) {
    return 'Omi couldn’t answer right now. Try again.'
  }

  // No usable status: an offline / transport failure has its own copy. Either the
  // browser reports offline, or the fetch rejected with a transport-level error
  // (`Failed to fetch` / `NetworkError`) before any HTTP response arrived.
  const offline =
    (typeof navigator !== 'undefined' && navigator.onLine === false) ||
    /failed to fetch|networkerror|network request failed/i.test(msg)
  if (offline) {
    return 'You’re offline. Check your connection and try again.'
  }

  // Anything else: the friendly generic — NEVER echo the raw technical string.
  return 'Omi couldn’t answer right now. Try again.'
}
