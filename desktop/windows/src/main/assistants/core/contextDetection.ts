// Context-switch detection — pure. Port of macOS `ContextDetection.swift`.
//
// The signal is window-manager metadata only (app name + window title), never
// pixels. The whole point of the normalization below is that a title which keeps
// re-rendering itself — a build spinner, a ticking call timer, a terminal that
// prints its dimensions, an unread badge counting up — is NOT a context switch.
// Without it the user sitting still in one window would look like a switch every
// few seconds, and every switch re-triggers the assistants' analysis cycle.

// Braille glyphs (U+2800–U+28FF) are the standard CLI spinner alphabet.
const BRAILLE = /[⠀-⣿]/g
// Non-braille spinner / progress characters (Mac's set). Deliberately excludes
// `| / \ -` : those cycle in ASCII spinners but are also ordinary title
// separators and path characters, and stripping them would mangle real titles.
const SPINNER_CHARS = /[✳↻◐◑◒◓◴◵◶◷▖▘▝▗▙▛▜▟]/g
// Clock-ish counters: "12:34", "1:23:45".
const TIMER = /\b\d{1,2}:\d{2}(:\d{2})?\b/g
// Terminal dimensions: "80×24", "80x24".
const TERMINAL_DIMS = /\b\d+[×x]\d+\b/g
// Unread / item counts: "(3)", "[12]".
const UNREAD_COUNT = /(\(\d+\)|\[\d+\])/g

/** Strip cosmetic churn from a window title. Returns null when nothing of
 *  substance is left (a title that was ONLY a spinner carries no context). */
export function normalizeWindowTitle(title: string | null | undefined): string | null {
  if (!title) return null
  const cleaned = title
    .replace(BRAILLE, '')
    .replace(SPINNER_CHARS, '')
    .replace(TIMER, '')
    .replace(TERMINAL_DIMS, '')
    .replace(UNREAD_COUNT, '')
    .replace(/\s+/g, ' ')
    .trim()
  return cleaned.length > 0 ? cleaned : null
}

/** True when the user moved to a different app, or to a materially different
 *  window within the same app. */
export function didContextChange(
  fromApp: string | null | undefined,
  fromWindowTitle: string | null | undefined,
  toApp: string | null | undefined,
  toWindowTitle: string | null | undefined
): boolean {
  if (fromApp !== toApp) return true
  return normalizeWindowTitle(fromWindowTitle) !== normalizeWindowTitle(toWindowTitle)
}
