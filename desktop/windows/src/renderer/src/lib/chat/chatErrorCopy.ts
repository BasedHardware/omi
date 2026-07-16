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
export function friendlyChatError(raw: string): string {
  const msg = raw ?? ''

  // Prefer a structured HTTP status when the raw error carries one. legacy_sse
  // throws `HTTP <status>`; a managed-cloud error may read `status code <n>`.
  const statusMatch = msg.match(/(?:HTTP|status(?:\s+code)?)\s+(\d{3})/i)
  const status = statusMatch ? Number(statusMatch[1]) : null

  if (status === 401 || status === 403) {
    // Mac authRequired parity — token expired / missing.
    return 'Please sign in to continue.'
  }
  if (status === 429) {
    return 'You’re sending messages too quickly. Give it a moment and try again.'
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
