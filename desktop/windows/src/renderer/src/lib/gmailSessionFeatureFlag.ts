// Whether the Gmail "session" connector (Option B) is surfaced in this build.
//
// This is the verification-free Gmail lane: the user signs into Google once inside an
// Omi-owned persistent session partition and we replay Gmail's web endpoints against
// that own-session cookie jar (mirrors macOS, which harvests the system browser's
// cookies — an approach Windows can't take because of Chrome App-Bound Encryption).
//
// It now ships ON by default. Set VITE_ENABLE_GMAIL_SESSION=0 at build time to disable
// it (the escape hatch); in dev you can also turn it off locally by setting localStorage
// 'omi.gmailSession.enabled' = '0'.
export const GMAIL_SESSION_ENABLED =
  import.meta.env.VITE_ENABLE_GMAIL_SESSION !== '0' &&
  !(import.meta.env.DEV && localStorage.getItem('omi.gmailSession.enabled') === '0')
