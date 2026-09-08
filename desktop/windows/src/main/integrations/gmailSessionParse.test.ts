import { describe, it, expect } from 'vitest'
import {
  buildAtomFeedUrl,
  buildGmailLoginUrl,
  parseAtomFeed,
  parseBootstrapPage,
  hasGoogleAuthCookies,
  type GmailSessionEmail
} from './gmailSessionParse'

describe('buildAtomFeedUrl', () => {
  it('builds the default atom feed url with an encoded query', () => {
    expect(buildAtomFeedUrl('newer_than:365d')).toBe(
      'https://mail.google.com/mail/feed/atom?q=newer_than%3A365d'
    )
  })

  it('builds a per-label feed url', () => {
    expect(buildAtomFeedUrl('newer_than:1d', 'atom/inbox')).toBe(
      'https://mail.google.com/mail/feed/atom/inbox?q=newer_than%3A1d'
    )
  })

  it('strips leading slashes from feedPath', () => {
    expect(buildAtomFeedUrl('', '/atom/sent')).toBe('https://mail.google.com/mail/feed/atom/sent')
  })

  it('omits the query param when the query is empty', () => {
    expect(buildAtomFeedUrl('', 'atom/starred')).toBe(
      'https://mail.google.com/mail/feed/atom/starred'
    )
  })
})

describe('buildGmailLoginUrl', () => {
  const CONTINUE = 'continue=' + encodeURIComponent('https://mail.google.com/mail/')

  it('opens the plain sign-in (no login_hint) when no email is given', () => {
    const url = buildGmailLoginUrl()
    expect(url).toBe(`https://accounts.google.com/ServiceLogin?${CONTINUE}`)
    expect(url).not.toContain('login_hint')
  })

  it('adds an encoded login_hint when an email is given', () => {
    const url = buildGmailLoginUrl('user@gmail.com')
    expect(url).toBe(
      `https://accounts.google.com/ServiceLogin?${CONTINUE}&login_hint=user%40gmail.com`
    )
  })

  it('percent-encodes a plus-addressed email', () => {
    expect(buildGmailLoginUrl('a+b@gmail.com')).toContain('login_hint=a%2Bb%40gmail.com')
  })

  it('omits login_hint for an empty or whitespace email', () => {
    expect(buildGmailLoginUrl('')).not.toContain('login_hint')
    expect(buildGmailLoginUrl('   ')).not.toContain('login_hint')
    expect(buildGmailLoginUrl(null)).not.toContain('login_hint')
  })
})

describe('hasGoogleAuthCookies', () => {
  it('is true when a Google auth cookie is present', () => {
    expect(hasGoogleAuthCookies(['NID', 'SID', 'foo'])).toBe(true)
    expect(hasGoogleAuthCookies(['__Secure-1PSID'])).toBe(true)
  })

  it('is false when no auth cookies are present', () => {
    expect(hasGoogleAuthCookies(['NID', 'CONSENT'])).toBe(false)
    expect(hasGoogleAuthCookies([])).toBe(false)
  })
})

const ATOM_FIXTURE = `<?xml version="1.0" encoding="UTF-8"?>
<feed version="0.3" xmlns="http://purl.org/atom/ns#">
<title>Gmail - Inbox for test@gmail.com</title>
<fullcount>3</fullcount>
<entry>
<title>Lunch tomorrow?</title>
<summary>Hey, are you free for lunch tomorrow at noon?</summary>
<link rel="alternate" href="https://mail.google.com/mail?account_id=test@gmail.com&amp;message_id=abc123&amp;view=conv" type="text/html" />
<modified>2026-07-16T12:00:00Z</modified>
<issued>2026-07-16T12:00:00Z</issued>
<id>tag:gmail.google.com,2004:1799</id>
<author><name>Alice Example</name><email>alice@example.com</email></author>
</entry>
<entry>
<title>Deploy &amp; ship</title>
<summary>Ready to go &lt;3</summary>
<link rel="alternate" href="https://mail.google.com/mail/message_id=DEADBEEF" type="text/html" />
<issued>2026-07-15T09:30:00Z</issued>
<author><name>Bob</name><email>bob@example.com</email></author>
</entry>
<entry>
<title>No sender email here</title>
<summary>anon</summary>
<issued>2026-07-14T08:00:00Z</issued>
<author><name>System</name></author>
</entry>
</feed>`

describe('parseAtomFeed', () => {
  it('parses entries into the normalized shape', () => {
    const { emails, error } = parseAtomFeed(ATOM_FIXTURE, 50)
    expect(error).toBeUndefined()
    expect(emails).toHaveLength(3)

    const first = emails[0]
    expect(first.subject).toBe('Lunch tomorrow?')
    expect(first.snippet).toBe('Hey, are you free for lunch tomorrow at noon?')
    expect(first.from).toBe('Alice Example <alice@example.com>')
    expect(first.date).toBe('2026-07-16T12:00:00Z')
    expect(first.isUnread).toBe(true)
    // href has &message_id= (not /message_id=), so Mac's port falls back to a sha1 dedupe id.
    expect(first.id).toMatch(/^atom_[0-9a-f]{40}$/)
  })

  it('decodes XML entities in subject/snippet', () => {
    const { emails } = parseAtomFeed(ATOM_FIXTURE, 50)
    expect(emails[1].subject).toBe('Deploy & ship')
    expect(emails[1].snippet).toBe('Ready to go <3')
  })

  it('uses the /message_id= tail as the id when the link matches that form', () => {
    const { emails } = parseAtomFeed(ATOM_FIXTURE, 50)
    expect(emails[1].id).toBe('DEADBEEF')
  })

  it('formats "from" as just the name when there is no author email', () => {
    const { emails } = parseAtomFeed(ATOM_FIXTURE, 50)
    expect(emails[2].from).toBe('System')
    // No link element at all -> still a stable atom_ id.
    expect(emails[2].id).toMatch(/^atom_[0-9a-f]{40}$/)
  })

  it('honors maxResults', () => {
    const { emails } = parseAtomFeed(ATOM_FIXTURE, 1)
    expect(emails).toHaveLength(1)
    expect(emails[0].subject).toBe('Lunch tomorrow?')
  })

  it('returns an error when the body is not an atom feed (e.g. an HTML login page)', () => {
    const { emails, error } = parseAtomFeed('<!DOCTYPE html><html><body>Sign in</body></html>', 50)
    expect(emails).toHaveLength(0)
    expect(error).toMatch(/not an Atom feed/i)
  })

  it('returns an empty list (no error) for a feed with no entries', () => {
    const empty =
      '<?xml version="1.0"?><feed xmlns="http://purl.org/atom/ns#"><fullcount>0</fullcount></feed>'
    const { emails, error } = parseAtomFeed(empty, 50)
    expect(emails).toHaveLength(0)
    expect(error).toBeUndefined()
  })
})

// --- Bootstrap page fixture ---------------------------------------------------
// Mirrors the nested snapshot structure the Swift/Python parser walks:
//   parsed[0][0] = rows
//   row          = [_, threadId, _, subject, rowMeta]
//   rowMeta      = [_, rowSnippet, rowTimestampMs, _, messageRows]
//   message      = [msgId, [_, senderEmail, senderName], _, _, _, _, msgTimestampMs, _, _, snippet, labels]
function buildBootstrapHtml(parsed: unknown): string {
  const inner = JSON.stringify(parsed)
  // The needle already supplies the opening quote of the escaped JSON string; the
  // reader collects up to the next UNescaped quote. slice(1) drops the leading quote
  // and keeps the trailing quote as the terminator.
  const body = JSON.stringify(inner).slice(1)
  return `<html><head><script>window.data = {"a6jdv":[["sils",null,"${body}]];</script></head><body>Inbox</body></html>`
}

const MSG_TS = Date.UTC(2026, 6, 16, 12, 0, 0) // 2026-07-16T12:00:00Z
const THREAD_TS = Date.UTC(2026, 6, 15, 9, 30, 0) // 2026-07-15T09:30:00Z

const BOOTSTRAP_PARSED = [
  [
    [
      // Row 0: a thread with one unread message
      [
        null,
        'thread-1',
        null,
        'Project kickoff',
        [
          null,
          'Row-level snippet',
          THREAD_TS,
          null,
          [
            [
              'msg-1',
              [null, 'carol@example.com', 'Carol'],
              null,
              null,
              null,
              null,
              MSG_TS,
              null,
              null,
              'Message-level snippet',
              ['^u', '^i']
            ]
          ]
        ]
      ],
      // Row 1: a thread with no message rows -> falls back to thread-level fields (read)
      [
        null,
        'thread-2',
        null,
        'Standalone thread',
        [null, 'Thread only snippet', THREAD_TS, null, []]
      ]
    ]
  ]
]

describe('parseBootstrapPage', () => {
  it('parses thread/message rows into the normalized shape', () => {
    const html = buildBootstrapHtml(BOOTSTRAP_PARSED)
    const { emails, error } = parseBootstrapPage(html, 50)
    expect(error).toBeUndefined()
    expect(emails).toHaveLength(2)

    const msg = emails.find((e: GmailSessionEmail) => e.id === 'msg-1')!
    expect(msg.subject).toBe('Project kickoff')
    expect(msg.from).toBe('Carol <carol@example.com>')
    expect(msg.snippet).toBe('Message-level snippet')
    expect(msg.date).toBe('2026-07-16T12:00:00Z')
    expect(msg.isUnread).toBe(true)

    const thread = emails.find((e: GmailSessionEmail) => e.id === 'thread-2')!
    expect(thread.subject).toBe('Standalone thread')
    expect(thread.from).toBe('')
    expect(thread.snippet).toBe('Thread only snippet')
    expect(thread.isUnread).toBe(false)
    expect(thread.date).toBe('2026-07-15T09:30:00Z')
  })

  it('honors maxResults', () => {
    const html = buildBootstrapHtml(BOOTSTRAP_PARSED)
    const { emails } = parseBootstrapPage(html, 1)
    expect(emails).toHaveLength(1)
    expect(emails[0].id).toBe('msg-1')
  })

  it('returns an error when the bootstrap needle is missing', () => {
    const { emails, error } = parseBootstrapPage('<html><body>no snapshot here</body></html>', 50)
    expect(emails).toHaveLength(0)
    expect(error).toMatch(/not found/i)
  })

  it('returns an error when the snapshot JSON is malformed', () => {
    const html = '<html>{"a6jdv":[["sils",null,"not-valid-json"]];</html>'
    const { emails, error } = parseBootstrapPage(html, 50)
    expect(emails).toHaveLength(0)
    expect(error).toBeTruthy()
  })
})
