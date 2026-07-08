// src/renderer/src/lib/screenRedact.test.ts
import { describe, it, expect } from 'vitest'
import { redact, isPrivateWindow, isDeniedContext, DEFAULT_DENYLIST, redactFrameFields } from './screenRedact'

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
