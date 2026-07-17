// Whether the Gmail "session" connector (Option B) is surfaced in this build.
//
// This is the verification-free Gmail lane: the user signs into Google once inside an
// Omi-owned persistent session partition and we replay Gmail's web endpoints against
// that own-session cookie jar (mirrors macOS, which harvests the system browser's
// cookies — an approach Windows can't take because of Chrome App-Bound Encryption).
//
// It ships OFF by default (a new, experimental credential path) and is opt-in via the
// build flag, or via localStorage in dev — same shape as GOOGLE_ENABLED.
export const GMAIL_SESSION_ENABLED =
  import.meta.env.VITE_ENABLE_GMAIL_SESSION === '1' ||
  (import.meta.env.DEV && localStorage.getItem('omi.gmailSession.enabled') === '1')
