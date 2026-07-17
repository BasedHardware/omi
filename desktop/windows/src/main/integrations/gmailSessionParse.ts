// Pure parsers + URL builders for the Gmail "session" connector (Option B).
//
// This is a faithful TypeScript port of the macOS reference implementation in
// `desktop/macos/Desktop/Sources/GmailReaderService.swift` (the embedded Python
// `parse_atom` / `parse_bootstrap_page` / `fetch_atom_feed`). The Windows app owns
// its own Electron session partition and replays the SAME Gmail web endpoints Mac
// uses, so it must produce the SAME normalized shape. Keeping the parsers pure (no
// Electron / network imports) makes them unit-testable against fixtures.
//
// Do NOT log the parsed contents at call sites — email bodies/senders are PII.

import { createHash } from 'node:crypto'
import type { GmailSessionEmail } from '../../shared/types'

// The normalized email shape (mirrors Swift `GmailEmail`) is the wire contract, so it
// lives in shared/types.ts. Re-exported here for the reader + parser call sites.
export type { GmailSessionEmail }

export interface GmailParseResult {
  emails: GmailSessionEmail[]
  error?: string
}

/** ASCII unit separator (chr(31)) — matches the Python dedupe join. */
const ATOM_UNIT_SEPARATOR = '\u001f'

/** The Google auth cookies Mac looks for to decide a session is signed in. */
export const GOOGLE_AUTH_COOKIE_NAMES = [
  'SID',
  'HSID',
  'SSID',
  'APISID',
  'SAPISID',
  '__Secure-1PSID',
  '__Secure-3PSID'
] as const

function sha1Hex(input: string): string {
  return createHash('sha1').update(input, 'utf8').digest('hex')
}

/**
 * Format a millisecond epoch as `YYYY-MM-DDTHH:MM:SSZ` (UTC, no fractional seconds).
 * Mirrors Python `time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ms / 1000))`.
 * A null/undefined timestamp falls back to "now", exactly like the Swift port.
 */
function isoFromMillis(ms: number | null | undefined): string {
  const millis = ms == null ? Date.now() : ms
  return new Date(millis).toISOString().replace(/\.\d{3}Z$/, 'Z')
}

/** Minimal XML entity decode (ElementTree decodes these automatically). `&amp;` last. */
function xmlDecode(value: string): string {
  return value
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_m, hex: string) => codePoint(parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_m, dec: string) => codePoint(parseInt(dec, 10)))
    .replace(/&amp;/g, '&')
}

function codePoint(n: number): string {
  return Number.isFinite(n) && n >= 0 && n <= 0x10ffff ? String.fromCodePoint(n) : ''
}

/** Text of the first `<tag ...>text</tag>` inside a block (namespace-agnostic, unprefixed). */
function firstTagText(block: string, tag: string): string {
  const re = new RegExp(`<${tag}\\b[^>]*>([\\s\\S]*?)</${tag}>`, 'i')
  const m = re.exec(block)
  return m ? xmlDecode(m[1].trim()) : ''
}

/**
 * Build the Gmail Atom feed URL.
 * Mirrors `fetch_atom_feed` in GmailReaderService.swift:
 *   - default:   https://mail.google.com/mail/feed/atom?q=<query>
 *   - feedPath:  https://mail.google.com/mail/feed/<path>?q=<query>
 */
export function buildAtomFeedUrl(query: string, feedPath?: string | null): string {
  const base = 'https://mail.google.com/mail/feed'
  if (feedPath) {
    const trimmed = feedPath.replace(/^\/+/, '')
    let url = `${base}/${trimmed}`
    if (query) {
      const separator = url.includes('?') ? '&' : '?'
      url = `${url}${separator}q=${encodeURIComponent(query)}`
    }
    return url
  }
  return `${base}/atom?q=${encodeURIComponent(query)}`
}

/**
 * Parse a Gmail Atom feed into normalized emails.
 * Faithful port of `parse_atom` (GmailReaderService.swift). Atom entries are always
 * marked unread (matching Mac). The id derivation intentionally mirrors Mac's quirk:
 * it keys off the `<link href>` (`/message_id=` split, else a sha1 dedupe hash) and
 * never the `<id>` element.
 */
export function parseAtomFeed(xml: string, maxResults: number): GmailParseResult {
  if (!/<feed[\s>]/i.test(xml) && !/<entry[\s>]/i.test(xml)) {
    return { emails: [], error: 'XML parse error: response is not an Atom feed' }
  }

  const emails: GmailSessionEmail[] = []
  const entryRe = /<entry\b[^>]*>([\s\S]*?)<\/entry>/gi
  let match: RegExpExecArray | null
  while ((match = entryRe.exec(xml)) !== null) {
    if (emails.length >= maxResults) break
    const block = match[1]

    const title = firstTagText(block, 'title')
    const summary = firstTagText(block, 'summary')

    const authorBlock = /<author\b[^>]*>([\s\S]*?)<\/author>/i.exec(block)?.[1] ?? ''
    const authorName = authorBlock ? firstTagText(authorBlock, 'name') : ''
    const authorEmail = authorBlock ? firstTagText(authorBlock, 'email') : ''

    const issued = firstTagText(block, 'issued')

    const hasLink = /<link\b[^>]*>/i.test(block)
    let href = ''
    if (hasLink) {
      const hrefMatch = /<link\b[^>]*\bhref\s*=\s*["']([^"']*)["']/i.exec(block)
      href = hrefMatch ? xmlDecode(hrefMatch[1]) : ''
    }

    const id = computeAtomId({ hasLink, href, title, summary, authorName, authorEmail, issued })
    const from = authorEmail ? `${authorName} <${authorEmail}>` : authorName

    emails.push({
      id,
      from,
      subject: title || '(no subject)',
      snippet: summary || '',
      date: issued || '',
      isUnread: true
    })
  }

  return { emails }
}

function computeAtomId(parts: {
  hasLink: boolean
  href: string
  title: string
  summary: string
  authorName: string
  authorEmail: string
  issued: string
}): string {
  const { hasLink, href, title, summary, authorName, authorEmail, issued } = parts
  if (hasLink) {
    if (href.includes('/message_id=')) {
      return href.split('/message_id=').pop() ?? ''
    }
    return (
      'atom_' +
      sha1Hex([href, title, summary, authorName, authorEmail, issued].join(ATOM_UNIT_SEPARATOR))
    )
  }
  return (
    'atom_' + sha1Hex([title, summary, authorName, authorEmail, issued].join(ATOM_UNIT_SEPARATOR))
  )
}

/**
 * Parse Gmail's inbox "bootstrap" snapshot embedded in the `/mail/u/0/` HTML.
 * Faithful port of `parse_bootstrap_page` (GmailReaderService.swift): finds the
 * `"a6jdv":[["sils",...` needle, extracts the escaped JSON string, double-decodes it,
 * and walks the nested thread/message rows. Returns an error string (mirroring the
 * Python) so the reader can fall back to the Atom feed exactly like Mac does.
 */
export function parseBootstrapPage(html: string, maxResults: number): GmailParseResult {
  const needle = '"a6jdv":[["sils",null,"'
  const start = html.indexOf(needle)
  if (start < 0) {
    return { emails: [], error: 'Bootstrap inbox snapshot not found' }
  }

  // Walk the escaped JSON string char-by-char (mirrors the Python escape state machine).
  let i = start + needle.length
  let escaped = false
  const encodedChars: string[] = []
  while (i < html.length) {
    const ch = html[i]
    if (escaped) {
      encodedChars.push(ch)
      escaped = false
    } else if (ch === '\\') {
      encodedChars.push(ch)
      escaped = true
    } else if (ch === '"') {
      break
    } else {
      encodedChars.push(ch)
    }
    i += 1
  }

  let parsed: unknown
  try {
    const encoded = '"' + encodedChars.join('') + '"'
    const decoded = JSON.parse(encoded) as string
    parsed = JSON.parse(decoded)
  } catch (e) {
    return { emails: [], error: `Bootstrap JSON parse error: ${(e as Error).message}` }
  }

  if (!Array.isArray(parsed) || parsed.length === 0 || !Array.isArray(parsed[0])) {
    return { emails: [], error: 'Bootstrap inbox snapshot malformed' }
  }

  const rows: unknown[] =
    parsed[0].length > 0 && Array.isArray(parsed[0][0]) ? (parsed[0][0] as unknown[]) : []
  const emails: GmailSessionEmail[] = []
  const seen = new Set<string>()

  for (const row of rows) {
    if (!Array.isArray(row) || row.length < 5) continue

    const threadId = row.length > 1 && typeof row[1] === 'string' ? row[1] : ''
    const subject = row.length > 3 && typeof row[3] === 'string' ? row[3] : '(no subject)'
    const rowMeta = Array.isArray(row[4]) ? (row[4] as unknown[]) : []
    const rowSnippet = rowMeta.length > 1 && typeof rowMeta[1] === 'string' ? rowMeta[1] : ''
    const rowTimestamp = rowMeta.length > 2 && typeof rowMeta[2] === 'number' ? rowMeta[2] : null
    const messageRows =
      rowMeta.length > 4 && Array.isArray(rowMeta[4]) ? (rowMeta[4] as unknown[]) : []

    if (messageRows.length === 0) {
      if (threadId && !seen.has(threadId)) {
        seen.add(threadId)
        emails.push({
          id: threadId,
          from: '',
          subject,
          snippet: rowSnippet,
          date: isoFromMillis(rowTimestamp),
          isUnread: false
        })
      }
      continue
    }

    for (const message of messageRows) {
      if (!Array.isArray(message) || message.length === 0) continue

      const msgId = typeof message[0] === 'string' ? message[0] : threadId
      if (!msgId || seen.has(msgId)) continue
      seen.add(msgId)

      let sender = ''
      if (message.length > 1 && Array.isArray(message[1])) {
        const senderMeta = message[1] as unknown[]
        const senderName =
          senderMeta.length > 2 && typeof senderMeta[2] === 'string' ? senderMeta[2] : ''
        const senderEmail =
          senderMeta.length > 1 && typeof senderMeta[1] === 'string' ? senderMeta[1] : ''
        sender =
          senderName && senderEmail ? `${senderName} <${senderEmail}>` : senderName || senderEmail
      }

      const msgTimestamp =
        message.length > 6 && typeof message[6] === 'number' ? message[6] : rowTimestamp
      const snippet = message.length > 9 && typeof message[9] === 'string' ? message[9] : rowSnippet
      const labels =
        message.length > 10 && Array.isArray(message[10]) ? (message[10] as unknown[]) : []
      const isUnread = labels.includes('^u')

      emails.push({
        id: msgId,
        from: sender,
        subject: subject || '(no subject)',
        snippet: snippet || '',
        date: isoFromMillis(msgTimestamp),
        isUnread
      })

      if (emails.length >= maxResults) return { emails }
    }
  }

  return { emails: emails.slice(0, maxResults) }
}

/** True when the given cookie names include at least one Google auth cookie. */
export function hasGoogleAuthCookies(cookieNames: readonly string[]): boolean {
  const set = new Set(cookieNames)
  return GOOGLE_AUTH_COOKIE_NAMES.some((name) => set.has(name))
}
