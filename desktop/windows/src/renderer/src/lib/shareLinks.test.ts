import { describe, expect, it } from 'vitest'
import { conversationShareUrl, shareBaseUrl } from './shareLinks'

describe('shareLinks (#4339)', () => {
  it('defaults to production h.omi.me', () => {
    expect(shareBaseUrl('')).toBe('https://h.omi.me')
    expect(shareBaseUrl(undefined)).toBe('https://h.omi.me')
    expect(conversationShareUrl('abc', '', 'sid12345')).toBe(
      'https://h.omi.me/conversations/abc?sid=sid12345&s=win'
    )
  })

  it('honors VITE_OMI_SHARE_BASE_URL overrides', () => {
    expect(shareBaseUrl('https://share.example.com/')).toBe('https://share.example.com')
    expect(shareBaseUrl('share.example.com')).toBe('https://share.example.com')
    expect(conversationShareUrl('abc', 'https://share.example.com', 'sid12345')).toBe(
      'https://share.example.com/conversations/abc?sid=sid12345&s=win'
    )
  })

  it('falls back for malformed or unsupported overrides', () => {
    expect(shareBaseUrl('ftp://share.example.com')).toBe('https://h.omi.me')
    expect(shareBaseUrl('not a url')).toBe('https://h.omi.me')
  })

  it('mints a random share id per link', () => {
    const first = new URL(conversationShareUrl('abc')).searchParams.get('sid')
    const second = new URL(conversationShareUrl('abc')).searchParams.get('sid')
    expect(first).toMatch(/^[0-9a-f]{32}$/)
    expect(first).not.toBe(second)
  })
})
