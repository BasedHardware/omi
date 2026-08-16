// Shared scheme allow-list guard for handing a URL to the OS. A prompt-injected
// chat reply or a malformed checkout/portal URL could otherwise carry a file://,
// UNC, or custom-protocol URL; passing those to shell.openExternal enables
// NTLM-hash leak / protocol-handler abuse. The main window's window-open handler
// (http/https/mailto) and the billing customer-portal opener (http/https) both
// route through this one parser instead of hand-rolling their own.

/** True iff `url` parses and its scheme is one of `allowed` (bare, no trailing colon). */
export function isAllowedExternalScheme(url: string, allowed: string[]): boolean {
  try {
    const scheme = new URL(url).protocol // e.g. "https:"
    return allowed.some((a) => scheme === `${a}:`)
  } catch {
    return false
  }
}
