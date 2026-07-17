// Gmail reader for the Option B "session" connector (main process).
//
// Faithful port of the fetch/classify cascade in macOS `GmailReaderService.swift`:
// try the inbox "bootstrap" page first for recent mail, fall back to the Atom feed,
// and (for long look-back windows) fan out across the per-label Atom feeds. The only
// structural difference from macOS is the credential source: instead of decrypting a
// system browser's cookie store, the emails are fetched over an Omi-owned Electron
// session partition where the user has signed in (cookies auto-attach). All network
// + cookie I/O is injected so this logic is unit-testable without Electron.

import {
  parseAtomFeed,
  parseBootstrapPage,
  buildAtomFeedUrl,
  hasGoogleAuthCookies
} from './gmailSessionParse'
import type { GmailSessionEmail, GmailSessionStatus } from '../../shared/types'

/** Response shape from the injected HTTP getter. `status: null` means transport error. */
export interface GmailHttpResponse {
  status: number | null
  body: string
  error?: string
}

export type GmailHttpGet = (url: string) => Promise<GmailHttpResponse>
export type GmailAuthCookieNames = () => Promise<string[]>

export interface GmailReaderDeps {
  httpGet: GmailHttpGet
  getAuthCookieNames: GmailAuthCookieNames
}

export type GmailFailureClass = 'not_signed_in' | 'session_expired' | 'network' | 'unknown'

export interface GmailReadOutcome {
  ok: boolean
  emails: GmailSessionEmail[]
  source?: 'bootstrap' | 'atom'
  errorClass?: GmailFailureClass
  error?: string
}

const HOME_PAGE_URL = 'https://mail.google.com/mail/u/0/'

// Human-readable messages mirror the intent of macOS `GmailReaderError`.
const MESSAGES: Record<GmailFailureClass, string> = {
  not_signed_in: 'Not signed into Gmail. Click Connect and sign in, then try again.',
  session_expired: 'Your Gmail session expired. Reconnect Gmail to refresh it.',
  network: 'Could not reach Gmail. Check your connection and try again.',
  unknown: 'Unexpected error reading Gmail.'
}

/** Per-label Atom feeds macOS fans out across for long look-back windows. */
const LABEL_FEEDS = [
  'atom/all',
  'atom/inbox',
  'atom/sent',
  'atom/starred',
  'atom/important',
  'atom/trash',
  'atom/spam',
  'atom/unread',
  'atom/social',
  'atom/promotions',
  'atom/updates',
  'atom/forums',
  'atom/personal'
]

/** Extract N from a `newer_than:Nd` clause (mirrors macOS `parseNewerThanDays`). */
export function parseNewerThanDays(query: string): number | null {
  const m = /newer_than:(\d+)d/.exec(query)
  return m ? parseInt(m[1], 10) : null
}

function fail(errorClass: GmailFailureClass, detail?: string): GmailReadOutcome {
  return { ok: false, emails: [], errorClass, error: detail || MESSAGES[errorClass] }
}

/**
 * Fetch one atom/bootstrap "single" batch. Mirrors `fetchGmailViaAtomFeedSingle`:
 * optionally try the bootstrap inbox page first (recent mail), then the Atom feed;
 * classify by HTTP status. Assumes the caller already confirmed auth cookies exist.
 */
async function fetchAtomSingle(
  deps: GmailReaderDeps,
  opts: { maxResults: number; query: string; feedPath?: string | null; allowBootstrap?: boolean }
): Promise<GmailReadOutcome> {
  const { maxResults, query } = opts
  const feedPath = opts.feedPath ?? null
  const shouldBootstrap =
    opts.allowBootstrap ?? (feedPath === null && parseNewerThanDays(query) !== null)

  if (shouldBootstrap) {
    const home = await deps.httpGet(HOME_PAGE_URL)
    if (home.status === 200) {
      const parsed = parseBootstrapPage(home.body, maxResults)
      if (!parsed.error && parsed.emails.length > 0) {
        return { ok: true, emails: parsed.emails, source: 'bootstrap' }
      }
    }
    // Any other bootstrap outcome falls through to the Atom feed (matches macOS).
  }

  const feed = await deps.httpGet(buildAtomFeedUrl(query, feedPath))
  if (feed.status === 200) {
    const parsed = parseAtomFeed(feed.body, maxResults)
    if (!parsed.error) {
      return { ok: true, emails: parsed.emails, source: 'atom' }
    }
    // 200 but not an Atom feed => Google served login/interstitial HTML => stale session.
    // INTENTIONAL deviation from macOS (whose classifier only keys off HTTP 401/403 and
    // would surface this as a generic error): treating a 200 non-feed as session_expired
    // gives the user the correct "reconnect" action. Do not "fix" this back to a 401 check.
    return fail('session_expired', parsed.error)
  }
  if (feed.status === 401 || feed.status === 403) return fail('session_expired')
  if (feed.status === null) return fail('network', feed.error)
  return fail('network', `HTTP ${feed.status}`)
}

/** Dedupe by id (keeping the newest date), sort newest-first, cap at maxResults. */
function mergeByLatest(emails: GmailSessionEmail[], maxResults: number): GmailSessionEmail[] {
  const merged = new Map<string, GmailSessionEmail>()
  for (const email of emails) {
    const existing = merged.get(email.id)
    if (!existing || existing.date < email.date) merged.set(email.id, email)
  }
  // Sort newest-first. INTENTIONAL deviation from macOS (which sorts parsed Date objects):
  // all feed/bootstrap dates are ISO-8601 UTC strings, so lexicographic compare is
  // chronologically equivalent and avoids Date parsing. Do not "fix" to Date math.
  return [...merged.values()].sort((a, b) => b.date.localeCompare(a.date)).slice(0, maxResults)
}

/** Best-effort fan-out across per-label Atom feeds (a single failing feed is skipped). */
async function fetchLabelFeeds(
  deps: GmailReaderDeps,
  maxResults: number,
  query: string
): Promise<GmailSessionEmail[]> {
  const collected: GmailSessionEmail[] = []
  for (const feedPath of LABEL_FEEDS) {
    const out = await fetchAtomSingle(deps, {
      maxResults: Math.min(20, maxResults),
      query,
      feedPath,
      allowBootstrap: false
    })
    if (out.ok) collected.push(...out.emails) // best-effort: a stale/empty feed must not fail the batch
  }
  return mergeByLatest(collected, maxResults)
}

/**
 * Read recent emails via the persisted Gmail session. Mirrors macOS `readRecentEmails`:
 * long look-back windows (`newer_than:>20d`, e.g. the onboarding import) merge a query
 * Atom fetch with the per-label feeds; short windows use the bootstrap→atom cascade.
 */
export async function readRecentEmails(
  deps: GmailReaderDeps,
  opts: { maxResults?: number; query?: string } = {}
): Promise<GmailReadOutcome> {
  const maxResults = opts.maxResults ?? 50
  const query = opts.query ?? 'newer_than:1d'

  const cookieNames = await deps.getAuthCookieNames()
  if (!hasGoogleAuthCookies(cookieNames)) return fail('not_signed_in')

  const days = parseNewerThanDays(query)
  if (days !== null && days > 20) {
    const primary = await fetchAtomSingle(deps, {
      maxResults,
      query,
      feedPath: null,
      allowBootstrap: false
    })
    if (!primary.ok) return primary
    const labelEmails = await fetchLabelFeeds(deps, maxResults, query)
    const emails = mergeByLatest([...primary.emails, ...labelEmails], maxResults)
    return { ok: true, emails, source: primary.source }
  }

  const out = await fetchAtomSingle(deps, { maxResults, query })
  if (!out.ok) return out
  const emails = mergeByLatest(out.emails, maxResults)
  return { ok: true, emails, source: out.source }
}

/**
 * Verify the persisted session can still read Gmail. Mirrors macOS `verifyConnection`:
 * a single-result fetch of the inbox Atom feed, mapped to a connection status.
 */
export async function verifyConnection(deps: GmailReaderDeps): Promise<GmailSessionStatus> {
  const cookieNames = await deps.getAuthCookieNames()
  if (!hasGoogleAuthCookies(cookieNames)) {
    return { connected: false, message: MESSAGES.not_signed_in }
  }
  const out = await fetchAtomSingle(deps, {
    maxResults: 1,
    query: 'newer_than:1d',
    feedPath: 'atom/inbox',
    allowBootstrap: false
  })
  if (out.ok) return { connected: true, verifiedAt: Date.now() }
  return { connected: false, message: out.error || MESSAGES.unknown }
}
