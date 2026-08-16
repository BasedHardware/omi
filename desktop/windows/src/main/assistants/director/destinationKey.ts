/**
 * Port of macOS ContextDestinationKey (ContextDestinationKey.swift).
 *
 * Browser tabs of one site collapse into a single `dest:<domain>/<section>`
 * bucket: the extraction model proposes the key once per novel browser title,
 * and this deterministic sanitizer decides whether the proposal is storable.
 * A nil result always means "stay per-title" — the safe direction.
 */

export const DESTINATION_SUBJECT_PREFIX = 'dest:'
export const DESTINATION_DERIVATION_SOURCE = 'derived_destination:v1'
export const DESTINATION_ABSTENTION = 'unknown/'

/** Exact-match browser names (lowercased, trimmed). Substring matching is a
 *  known trap: it classified "Ledger Live" as edge and "Archive Utility" as arc. */
const BROWSER_APP_NAMES = new Set([
  'google chrome',
  'google chrome canary',
  'google chrome beta',
  'chromium',
  'safari',
  'safari technology preview',
  'firefox',
  'firefox developer edition',
  'arc',
  'microsoft edge',
  'brave browser',
  'vivaldi',
  'opera',
  'opera gx',
  'orion',
  'zen browser'
])

const FORBIDDEN_DOMAIN_LABELS = new Set([
  'chrome',
  'chromium',
  'browser',
  'safari',
  'firefox',
  'arc',
  'edge',
  'brave',
  'vivaldi',
  'opera',
  'orion',
  'unknown',
  'localhost',
  'newtab',
  'about',
  'file'
])

const MESSENGER_HOSTS = new Set([
  'slack',
  'discord',
  'telegram',
  'whatsapp',
  'messenger',
  'teams',
  'signal',
  'matrix',
  'element',
  'chat',
  'imessage',
  'zulip',
  'mattermost'
])

const GENERIC_DOMAIN_PARTS = new Set([
  'com',
  'org',
  'io',
  'net',
  'co',
  'www',
  'app',
  'apps',
  'google',
  'web',
  'html'
])

const GENERIC_SECTION_WORDS = new Set([
  'feed',
  'inbox',
  'home',
  'mail',
  'builds',
  'build',
  'search',
  'news',
  'chat',
  'threads',
  'posts',
  'notifications',
  'dashboard',
  'settings',
  'profile',
  'explore',
  'timeline',
  'messages',
  'main',
  'index',
  'overview',
  'start'
])

export function isBrowser(appName: string): boolean {
  return BROWSER_APP_NAMES.has(appName.trim().toLowerCase())
}

/** Flatten to one line: newlines/control chars become spaces, whitespace runs
 *  collapse, then trim and clamp. */
export function singleLine(value: string, limit = 60): string {
  let out = ''
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0
    out += code < 0x20 || code === 0x7f ? ' ' : ch
  }
  out = out.replace(/\s+/g, ' ').trim()
  return out.length > limit ? [...out].slice(0, limit).join('') : out
}

/** Trailing site token: the segment after the last occurrence of a separator,
 *  separators tried in this order; accepted at trimmed length 2-40, lowercased. */
export function siteHint(title: string): string | null {
  const separators = ['·', '—', '–', ' - ', '|']
  for (const sep of separators) {
    const idx = title.lastIndexOf(sep)
    if (idx < 0) continue
    const tail = title.slice(idx + sep.length).trim()
    if (tail.length >= 2 && tail.length <= 40) return tail.toLowerCase()
    return null
  }
  return null
}

function titleTokens(title: string): Set<string> {
  return new Set(
    title
      .toLowerCase()
      .split(/[^a-z0-9]+/)
      .filter((t) => t.length > 0)
  )
}

function titleLooksLikeMessenger(title: string): boolean {
  for (const token of titleTokens(title)) {
    if (MESSENGER_HOSTS.has(token)) return true
  }
  return false
}

/** Grounding: at least one non-generic domain label must be evidenced by the
 *  title (>=4 chars: substring; shorter: whole-token equality, the x.com rule),
 *  with a non-generic >3-char section-part substring fallback. */
function isGrounded(domain: string, section: string, title: string): boolean {
  const loweredTitle = title.toLowerCase()
  const tokens = titleTokens(title)
  const domainParts = domain
    .split(/[.-]/)
    .filter((p) => p.length > 0 && !GENERIC_DOMAIN_PARTS.has(p))
  if (domainParts.length === 0) return false
  for (const part of domainParts) {
    if (part.length >= 4) {
      if (loweredTitle.includes(part)) return true
    } else if (tokens.has(part)) {
      return true
    }
  }
  const sectionParts = section
    .split(/[/\-_ ]+/)
    .filter((p) => p.length > 3 && !GENERIC_SECTION_WORDS.has(p))
  for (const part of sectionParts) {
    if (loweredTitle.includes(part)) return true
  }
  return false
}

/** Sanitize a model-proposed destination against the live title. Returns the
 *  storable subjectID (`dest:<domain>/<section>`) or null (= stay per-title). */
export function sanitizeDestination(proposed: string, title: string): string | null {
  let key = proposed.trim().toLowerCase().replace(/\s+/g, ' ')
  while (key.endsWith('/')) key = key.slice(0, -1)
  if (key.length < 3 || key.length > 120) return null
  if (key.startsWith('unknown')) return null

  const slash = key.indexOf('/')
  if (slash <= 0) return null
  const domain = key.slice(0, slash)
  const section = key.slice(slash + 1)
  if (domain.length === 0 || section.length === 0) return null

  const domainLabels = domain.split(/[.-]/)
  for (const label of domainLabels) {
    if (FORBIDDEN_DOMAIN_LABELS.has(label)) return null
  }
  for (const label of domainLabels) {
    if (MESSENGER_HOSTS.has(label)) return null
  }
  if (titleLooksLikeMessenger(title)) return null
  if (!isGrounded(domain, section, title)) return null

  return DESTINATION_SUBJECT_PREFIX + key
}

/** The browser-tab prompt fragment, verbatim from mac (DestKey:186-210). */
export function destinationPromptFragment(title: string): string {
  const base = `Also identify which website page-group this tab belongs to, as "destination".

Answer a key "<domain>/<section>", lowercase. Examples:
  x.com/feed   github.com/acme/repo   mail.google.com/inbox   app.codemagic.io/builds

Rules, in order of importance:
1. Never answer with the browser's name. "chrome", "safari", "browser" are forbidden.
2. Infer the domain from the title's site suffix or wording. Titles are truncated
   with "…", so the trailing part after the last separator is usually the site.
3. <section> is the durable area of that site — feed, inbox, builds, the repository
   path — never the individual post, message, issue or document currently open.
4. Different websites, repositories, mailboxes and chat workspaces are ALWAYS
   different keys.
5. If you cannot confidently identify the website, answer exactly "unknown/".
   Never guess a domain you are unsure of.`
  const hint = siteHint(title)
  if (hint === null) return base
  return `${base}\n\nTrailing site token: ${singleLine(hint)}`
}
