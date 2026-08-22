import { describe, it, expect } from 'vitest'
import {
  isBrowser,
  sanitizeDestination,
  siteHint,
  singleLine,
  destinationPromptFragment,
  DESTINATION_ABSTENTION
} from './destinationKey'

describe('isBrowser', () => {
  it('matches the exact browser-name set, trimmed and lowercased', () => {
    expect(isBrowser('Google Chrome')).toBe(true)
    expect(isBrowser('  microsoft edge ')).toBe(true)
    expect(isBrowser('Zen Browser')).toBe(true)
  })

  it('never substring-matches (the Ledger Live / Archive Utility trap)', () => {
    expect(isBrowser('Ledger Live')).toBe(false)
    expect(isBrowser('Archive Utility')).toBe(false)
    expect(isBrowser('Chrome Remote Desktop')).toBe(false)
  })
})

describe('sanitizeDestination', () => {
  const title = 'zach/context-director · Pull Request #1 · acme/omi — GitHub'

  it('accepts a grounded domain/section key and prefixes dest:', () => {
    expect(sanitizeDestination('github.com/acme/omi', title)).toBe('dest:github.com/acme/omi')
  })

  it('lowercases, collapses whitespace, and strips trailing slashes', () => {
    expect(sanitizeDestination('GitHub.com/acme/omi///', title)).toBe('dest:github.com/acme/omi')
  })

  it('rejects abstention and unknown-prefixed keys', () => {
    expect(sanitizeDestination(DESTINATION_ABSTENTION, title)).toBeNull()
    expect(sanitizeDestination('unknown/anything', title)).toBeNull()
  })

  it('rejects bare domains without a section', () => {
    expect(sanitizeDestination('github.com', title)).toBeNull()
    expect(sanitizeDestination('github.com/', title)).toBeNull()
  })

  it('rejects forbidden browser labels in any domain label position', () => {
    expect(
      sanitizeDestination('chrome.google.com/webstore', 'Chrome Web Store extensions')
    ).toBeNull()
    expect(sanitizeDestination('newtab.example.com/page', 'example page newtab')).toBeNull()
  })

  it('rejects messenger hosts by domain label and by title token', () => {
    expect(sanitizeDestination('app.slack.com/client', 'workspace slack client')).toBeNull()
    expect(sanitizeDestination('example.com/rooms', 'Team chat on Slack')).toBeNull()
  })

  it('requires grounding: >=4-char labels as substring, shorter as whole token', () => {
    // "x" grounds only as a whole title token (the x.com rule).
    expect(sanitizeDestination('x.com/feed', 'Home / X')).toBe('dest:x.com/feed')
    expect(sanitizeDestination('x.com/feed', 'Home / Example')).toBeNull()
    // Generic-only domains fall through to the section fallback.
    expect(sanitizeDestination('github.com/acme/omi', 'completely unrelated title')).toBeNull()
  })

  it('grounds via a non-generic section part longer than 3 chars', () => {
    expect(sanitizeDestination('app.example.com/projects', 'My projects overview')).toBe(
      'dest:app.example.com/projects'
    )
    // "feed" is generic and cannot ground on its own.
    expect(sanitizeDestination('app.example.com/feed', 'My feed overview')).toBeNull()
  })

  it('rejects keys outside the 3-120 length window', () => {
    expect(sanitizeDestination('a/', title)).toBeNull()
    expect(sanitizeDestination('a'.repeat(121) + '/x', title)).toBeNull()
  })
})

describe('siteHint', () => {
  it('takes the tail after the last separator, lowercased, at length 2-40', () => {
    expect(siteHint('Pull Request · GitHub')).toBe('github')
    expect(siteHint('Doc — Google Docs')).toBe('google docs')
    expect(siteHint('build | Codemagic')).toBe('codemagic')
  })

  it('returns null with no separator or an out-of-range tail', () => {
    expect(siteHint('no separators here')).toBeNull()
    expect(siteHint('tail too long · ' + 'x'.repeat(41))).toBeNull()
  })
})

describe('singleLine', () => {
  it('flattens control characters and collapses whitespace', () => {
    expect(singleLine('a\nb\tc')).toBe('a b c')
  })

  it('clamps to the limit', () => {
    expect(singleLine('abcdef', 3)).toBe('abc')
  })
})

describe('destinationPromptFragment', () => {
  it('carries the verbatim rules and appends the trailing site token when present', () => {
    const fragment = destinationPromptFragment('Inbox · Gmail')
    expect(fragment).toContain('Answer a key "<domain>/<section>", lowercase.')
    expect(fragment).toContain(
      '5. If you cannot confidently identify the website, answer exactly "unknown/".'
    )
    expect(fragment.endsWith('Trailing site token: gmail')).toBe(true)
  })

  it('omits the token line when no hint fires', () => {
    expect(destinationPromptFragment('plain title')).not.toContain('Trailing site token')
  })
})
