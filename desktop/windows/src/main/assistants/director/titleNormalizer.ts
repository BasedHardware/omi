/**
 * Port of macOS ContextTitleNormalizer (ContextTitleNormalizer.swift:6-77).
 *
 * Bucket identity is keyed by sha256(app::normalizedTitle), so these rules are
 * identity-defining: any deviation splits or merges buckets relative to mac.
 * The rules run in this exact order, and every regex is case-insensitive.
 *
 * This is deliberately NOT core/contextDetection's normalizeWindowTitle: that
 * coarser normalizer decides when the coordinator reports a context switch and
 * is shared by the existing assistants; changing it would shift their cadence.
 * Visit identity uses this mac-faithful normalizer instead.
 */

const PROGRESS_CHARS = new Set([
  '✳', // ✳
  '↻', // ↻
  '◐', // ◐
  '◑', // ◑
  '◒', // ◒
  '◓', // ◓
  '◴', // ◴
  '◷', // ◷
  '◶', // ◶
  '◵', // ◵
  '◰', // ◰
  '◳', // ◳
  '◲', // ◲
  '◱', // ◱
  '▖', // ▖
  '▘', // ▘
  '▝', // ▝
  '▗' // ▗
])

const CLOCK_RE = /\b\d{1,2}:\d{2}(:\d{2})?\b/gi
const DIMENSIONS_RE = /\b\d+[×x]\d+\b/gi
const LEADING_PAREN_BADGE_RE = /^\s*\(\d+\)\s*/i
const LEADING_BRACKET_BADGE_RE = /^\s*\[\d+\]\s*/i
const TRAILING_PAREN_COUNT_RE = /\s*\(\d+\)\s*$/i
const TRAILING_BRACKET_COUNT_RE = /\s*\[\d+\]\s*$/i
const TRAILING_NEW_ITEMS_RE = /\s*[-–—]\s*\d+\s+(new\s+)?(messages?|items?)\s*$/i
const TRAILING_SHELL_RE = /\s+[-–—]\s+(zsh|bash|fish)\s*$/i

function isMessagingApp(appName: string): boolean {
  const app = appName.toLowerCase()
  return app.includes('telegram') || app.includes('slack') || app.includes('discord')
}

function isBrowserApp(appName: string): boolean {
  const app = appName.toLowerCase()
  return (
    app.includes('chrome') ||
    app.includes('safari') ||
    app.includes('firefox') ||
    app.includes('arc') ||
    app.includes('edge') ||
    app.includes('brave') ||
    app.includes('vivaldi') ||
    app.includes('opera')
  )
}

function isTerminalApp(appName: string): boolean {
  const app = appName.toLowerCase()
  return app.includes('terminal') || app.includes('iterm') || app.includes('warp')
}

/** Normalize a window title for bucket identity; null when nothing survives. */
export function normalizeTitleForIdentity(
  windowTitle: string | null,
  appName: string
): string | null {
  if (windowTitle === null) return null
  let title = windowTitle.trim()
  if (title.length === 0) return null

  // Braille spinner animations (U+2800-U+28FF) and progress glyphs.
  let stripped = ''
  for (const ch of title) {
    const code = ch.codePointAt(0) ?? 0
    if (code >= 0x2800 && code <= 0x28ff) continue
    if (PROGRESS_CHARS.has(ch)) continue
    stripped += ch
  }
  title = stripped

  title = title.replace(CLOCK_RE, '')
  title = title.replace(DIMENSIONS_RE, '')

  const messaging = isMessagingApp(appName)
  const browser = isBrowserApp(appName)

  if (messaging || browser) {
    title = title.replace(LEADING_PAREN_BADGE_RE, '')
    title = title.replace(LEADING_BRACKET_BADGE_RE, '')
  }
  if (messaging) {
    title = title.replace(TRAILING_PAREN_COUNT_RE, '')
    title = title.replace(TRAILING_BRACKET_COUNT_RE, '')
    title = title.replace(TRAILING_NEW_ITEMS_RE, '')
  }
  if (isTerminalApp(appName)) {
    title = title.replace(TRAILING_SHELL_RE, '')
  }

  title = title.replace(/\s+/g, ' ').trim()
  return title.length === 0 ? null : title
}

/** `app::title`, both lowercased — the pre-hash bucket identity key. */
export function identityKey(appName: string, windowTitle: string | null): string | null {
  const normalized = normalizeTitleForIdentity(windowTitle, appName)
  if (normalized === null) return null
  return `${appName.toLowerCase()}::${normalized.toLowerCase()}`
}
