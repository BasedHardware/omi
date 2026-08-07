import { describe, expect, it } from 'vitest'
import { conversationShareUrl, shareBaseUrl } from './shareLinks'

describe('shareLinks (#4339)', () => {
  it('defaults to production h.omi.me', () => {
    expect(shareBaseUrl('')).toBe('https://h.omi.me')
    expect(shareBaseUrl(undefined)).toBe('https://h.omi.me')
    expect(conversationShareUrl('abc', '')).toBe('https://h.omi.me/conversations/abc')
  })

  it('honors VITE_OMI_SHARE_BASE_URL overrides', () => {
    expect(shareBaseUrl('https://share.example.com/')).toBe('https://share.example.com')
    expect(shareBaseUrl('share.example.com')).toBe('https://share.example.com')
    expect(conversationShareUrl('abc', 'https://share.example.com')).toBe(
      'https://share.example.com/conversations/abc'
    )
  })
})
