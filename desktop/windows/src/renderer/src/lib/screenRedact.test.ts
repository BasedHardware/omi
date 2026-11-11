// src/renderer/src/lib/screenRedact.test.ts
import { describe, it, expect } from 'vitest'
import {
  redact,
  isPrivateWindow,
  isDeniedContext,
  isUserDenied,
  DEFAULT_DENYLIST,
  redactFrameFields
} from './screenRedact'

describe('redact', () => {
  it('redacts emails, cards, ssn, tokens', () => {
    expect(redact('mail a@b.com')).toBe('mail [redacted]')
    expect(redact('card 4111 1111 1111 1111')).toBe('card [redacted]')
    expect(redact('ssn 123-45-6789')).toBe('ssn [redacted]')
    expect(redact('t eyJabc.def.ghi0000')).toContain('[redacted]')
  })
  it('leaves benign prose', () => {
    expect(redact('working on omi-windows')).toBe('working on omi-windows')
  })
})

describe('isPrivateWindow', () => {
  it('detects incognito/inprivate/private browsing', () => {
    expect(isPrivateWindow('x (Incognito)')).toBe(true)
    expect(isPrivateWindow('y [InPrivate]')).toBe(true)
    expect(isPrivateWindow('Inbox - Chrome')).toBe(false)
  })
})

describe('isDeniedContext', () => {
  it('denies built-in sensitive contexts (case-insensitive); allows normal', () => {
    expect(isDeniedContext({ app: '1Password', windowTitle: '', processName: '1password.exe' })).toBe(true)
    expect(isDeniedContext({ app: 'Chrome', windowTitle: 'Chase - Log in', processName: 'chrome.exe' })).toBe(true)
    expect(isDeniedContext({ app: 'Code', windowTitle: 'plan.md', processName: 'code.exe' })).toBe(false)
    expect(DEFAULT_DENYLIST.length).toBeGreaterThan(0)
  })
})

describe('isUserDenied', () => {
  const slackFrame = { app: 'Slack', windowTitle: 'general | Acme', processName: 'slack.exe' }

  it('excludes a frame whose app matches the user denylist (case-insensitive)', () => {
    expect(isUserDenied(slackFrame, ['Slack'])).toBe(true)
    expect(isUserDenied(slackFrame, ['slack'])).toBe(true)
    // matches windowTitle / processName too, mirroring isDeniedContext
    expect(isUserDenied({ app: 'Chrome', windowTitle: 'Notion — Roadmap', processName: 'chrome.exe' }, ['notion'])).toBe(
      true
    )
  })

  it('retains a frame when the user denylist is empty or has no real match (no false positive)', () => {
    expect(isUserDenied(slackFrame, [])).toBe(false)
    expect(isUserDenied({ app: 'Code', windowTitle: 'plan.md', processName: 'code.exe' }, ['slack'])).toBe(false)
    // blank / whitespace-only entries must not match everything
    expect(isUserDenied(slackFrame, ['', '   '])).toBe(false)
  })

  it('adds a leg, not a replacement: a builtin-denied frame stays excluded with an empty user denylist', () => {
    const pwFrame = { app: '1Password', windowTitle: '', processName: '1password.exe' }
    // The builtin leg still catches it independently of the (empty) user leg.
    expect(isDeniedContext(pwFrame)).toBe(true)
    expect(isUserDenied(pwFrame, [])).toBe(false)
  })
})

describe('redactFrameFields', () => {
  it('redacts both ocrText and windowTitle, preserving other fields', () => {
    const out = redactFrameFields({
      ocrText: 'email a@b.com',
      windowTitle: 'Re: salary jane@acme.com - Outlook',
      app: 'Outlook',
      ts: 5
    })
    expect(out.ocrText).toBe('email [redacted]')
    expect(out.windowTitle).toBe('Re: salary [redacted] - Outlook')
    expect(out.app).toBe('Outlook')
    expect(out.ts).toBe(5)
  })
})
