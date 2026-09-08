import { describe, it, expect, vi } from 'vitest'
import {
  readRecentEmails,
  verifyConnection,
  parseNewerThanDays,
  type GmailHttpResponse,
  type GmailReaderDeps
} from './gmailSessionReader'

// The reader imports only pure modules (gmailSessionParse + types) — no Electron —
// so its whole cascade is testable by injecting httpGet + getAuthCookieNames.

const AUTH_COOKIES = ['SID', '__Secure-1PSID', 'HSID', 'NID']

function atomFeed(
  entries: Array<{ subject: string; from?: string; email?: string; date: string }>
): string {
  const body = entries
    .map(
      (e) => `<entry>
<title>${e.subject}</title>
<summary>snippet for ${e.subject}</summary>
<issued>${e.date}</issued>
<author><name>${e.from ?? 'Sender'}</name>${e.email ? `<email>${e.email}</email>` : ''}</author>
</entry>`
    )
    .join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<feed version="0.3" xmlns="http://purl.org/atom/ns#">\n${body}\n</feed>`
}

function ok(body: string): GmailHttpResponse {
  return { status: 200, body }
}

function mkDeps(
  routes: (url: string) => GmailHttpResponse,
  cookies: string[] = AUTH_COOKIES
): GmailReaderDeps {
  return {
    httpGet: vi.fn(async (url: string) => routes(url)),
    getAuthCookieNames: vi.fn(async () => cookies)
  }
}

describe('parseNewerThanDays', () => {
  it('extracts the day count', () => {
    expect(parseNewerThanDays('newer_than:365d')).toBe(365)
    expect(parseNewerThanDays('newer_than:1d')).toBe(1)
    expect(parseNewerThanDays('after:2026/01/01')).toBeNull()
  })
})

describe('readRecentEmails', () => {
  it('returns not_signed_in when the session has no Google auth cookies', async () => {
    const deps = mkDeps(() => ok(atomFeed([])), ['NID', 'CONSENT'])
    const out = await readRecentEmails(deps, { query: 'newer_than:1d' })
    expect(out.ok).toBe(false)
    expect(out.errorClass).toBe('not_signed_in')
    // Must not hit the network when unauthenticated.
    expect(deps.httpGet).not.toHaveBeenCalled()
  })

  it('reads via the Atom feed for a short window (no bootstrap match)', async () => {
    const deps = mkDeps((url) => {
      if (url.includes('/mail/u/0/')) return ok('<html>no snapshot here</html>')
      return ok(atomFeed([{ subject: 'Hello', email: 'a@x.com', date: '2026-07-16T10:00:00Z' }]))
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:2d', maxResults: 10 })
    expect(out.ok).toBe(true)
    expect(out.source).toBe('atom')
    expect(out.emails).toHaveLength(1)
    expect(out.emails[0].subject).toBe('Hello')
    expect(out.emails[0].from).toBe('Sender <a@x.com>')
  })

  it('prefers the bootstrap page when it yields emails', async () => {
    const bootstrap = buildBootstrapHtml([
      [
        [
          [
            null,
            't1',
            null,
            'Boot subject',
            [null, 'boot snippet', Date.UTC(2026, 6, 16), null, []]
          ]
        ]
      ]
    ])
    const deps = mkDeps((url) => {
      if (url.includes('/mail/u/0/')) return ok(bootstrap)
      return ok(atomFeed([{ subject: 'atom-should-not-be-used', date: '2026-07-16T10:00:00Z' }]))
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:2d' })
    expect(out.ok).toBe(true)
    expect(out.source).toBe('bootstrap')
    expect(out.emails[0].subject).toBe('Boot subject')
  })

  it('classifies a 401 as session_expired', async () => {
    const deps = mkDeps((url) => {
      if (url.includes('/mail/u/0/')) return { status: 401, body: '' }
      return { status: 401, body: '' }
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:2d' })
    expect(out.ok).toBe(false)
    expect(out.errorClass).toBe('session_expired')
  })

  it('classifies a 200 non-feed body (login HTML) as session_expired', async () => {
    const deps = mkDeps((url) => {
      if (url.includes('/mail/u/0/')) return ok('<html>login</html>')
      return ok('<!DOCTYPE html><html><body>Sign in to continue</body></html>')
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:2d' })
    expect(out.ok).toBe(false)
    expect(out.errorClass).toBe('session_expired')
  })

  it('classifies a transport error as network', async () => {
    const deps = mkDeps((url) => {
      if (url.includes('/mail/u/0/')) return { status: null, body: '', error: 'ECONNRESET' }
      return { status: null, body: '', error: 'ECONNRESET' }
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:2d' })
    expect(out.ok).toBe(false)
    expect(out.errorClass).toBe('network')
  })

  it('merges the primary query feed with per-label feeds for a long window (>20d)', async () => {
    const deps = mkDeps((url) => {
      if (url.includes('/feed/atom/inbox')) {
        return ok(
          atomFeed([{ subject: 'Inbox item', email: 'i@x.com', date: '2026-07-15T10:00:00Z' }])
        )
      }
      if (url.includes('/feed/atom/sent')) {
        return ok(
          atomFeed([{ subject: 'Sent item', email: 's@x.com', date: '2026-07-14T10:00:00Z' }])
        )
      }
      if (url.includes('/feed/atom?')) {
        return ok(
          atomFeed([{ subject: 'Query item', email: 'q@x.com', date: '2026-07-16T10:00:00Z' }])
        )
      }
      return ok(atomFeed([])) // other label feeds empty
    })
    const out = await readRecentEmails(deps, { query: 'newer_than:365d', maxResults: 300 })
    expect(out.ok).toBe(true)
    const subjects = out.emails.map((e) => e.subject)
    expect(subjects).toContain('Query item')
    expect(subjects).toContain('Inbox item')
    expect(subjects).toContain('Sent item')
    // Sorted newest first.
    expect(out.emails[0].subject).toBe('Query item')
    // A long window must not consult the bootstrap page.
    expect(
      (deps.httpGet as ReturnType<typeof vi.fn>).mock.calls.some((c) =>
        String(c[0]).includes('/mail/u/0/')
      )
    ).toBe(false)
  })

  it('fails the long-window read when the primary query feed fails', async () => {
    const deps = mkDeps(() => ({ status: 500, body: '' }))
    const out = await readRecentEmails(deps, { query: 'newer_than:365d' })
    expect(out.ok).toBe(false)
    expect(out.errorClass).toBe('network')
  })
})

describe('verifyConnection', () => {
  it('reports connected when the inbox feed reads', async () => {
    const deps = mkDeps(() => ok(atomFeed([{ subject: 'x', date: '2026-07-16T10:00:00Z' }])))
    const status = await verifyConnection(deps)
    expect(status.connected).toBe(true)
    expect(status.verifiedAt).toBeTypeOf('number')
  })

  it('reports not connected with a message when there are no auth cookies', async () => {
    const deps = mkDeps(() => ok(atomFeed([])), ['NID'])
    const status = await verifyConnection(deps)
    expect(status.connected).toBe(false)
    expect(status.message).toMatch(/not signed into gmail/i)
  })

  it('reports not connected on a stale (401) session', async () => {
    const deps = mkDeps(() => ({ status: 401, body: '' }))
    const status = await verifyConnection(deps)
    expect(status.connected).toBe(false)
    expect(status.message).toMatch(/expired/i)
  })
})

// Bootstrap HTML fixture builder (same technique as gmailSessionParse.test.ts).
function buildBootstrapHtml(parsed: unknown): string {
  const inner = JSON.stringify(parsed)
  const body = JSON.stringify(inner).slice(1)
  return `<html><head><script>window.data = {"a6jdv":[["sils",null,"${body}]];</script></head><body>Inbox</body></html>`
}
