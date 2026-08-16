// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest'
import { friendlyChatError, chatErrorStatus } from './chatErrorCopy'

// PR-C: a failed chat send/stream must render friendly, plain-English copy —
// never a raw `Error: <technical string>`. Classify by pattern on the raw error
// message (plus the connectivity signal). Mirrors detailErrors.test.ts.
describe('friendlyChatError', () => {
  const GENERIC = 'Omi couldn’t answer right now. Try again.'

  it('maps HTTP 5xx to the generic try-again copy', () => {
    expect(friendlyChatError('HTTP 500')).toBe(GENERIC)
    expect(friendlyChatError('HTTP 503')).toBe(GENERIC)
    expect(friendlyChatError('HTTP 599')).toBe(GENERIC)
  })

  it('maps HTTP 401 / 403 to the sign-in copy (Mac authRequired parity)', () => {
    expect(friendlyChatError('HTTP 401')).toBe('Please sign in to continue.')
    expect(friendlyChatError('HTTP 403')).toBe('Please sign in to continue.')
  })

  it('maps HTTP 429 to the non-blaming "servers busy" copy (not "you\'re too quickly")', () => {
    // A 429 reaches this copy only after the send path's auto-retry is exhausted, so
    // it means a sustained rate limit — never a fast typer on their first message.
    const BUSY = 'Omi’s servers are busy. Try again in a moment.'
    expect(friendlyChatError('HTTP 429')).toBe(BUSY)
    // Regression: the old copy blamed the user; it must be gone.
    expect(friendlyChatError('HTTP 429')).not.toMatch(/too quickly/i)
  })

  it('maps a transport failure to the offline copy', () => {
    const OFFLINE = 'You’re offline. Check your connection and try again.'
    expect(friendlyChatError('Failed to fetch')).toBe(OFFLINE)
    expect(friendlyChatError('NetworkError when attempting to fetch resource.')).toBe(OFFLINE)
  })

  it('maps an unknown error to the friendly generic — never the raw string', () => {
    const raw = 'the model exploded'
    expect(friendlyChatError(raw)).toBe(GENERIC)
    expect(friendlyChatError(raw)).not.toContain(raw)
    expect(friendlyChatError('')).toBe(GENERIC)
    // No branch ever echoes the raw technical text or an `Error:` prefix.
    expect(friendlyChatError('HTTP 500')).not.toMatch(/HTTP|Error:/)
  })

  it('recognizes a status inside an axios-style message', () => {
    expect(friendlyChatError('Request failed with status code 429')).toBe(
      'Omi’s servers are busy. Try again in a moment.'
    )
  })

  it('chatErrorStatus extracts the HTTP status both wire formats carry (or null)', () => {
    // legacy_sse throws `HTTP <n>`; a managed-cloud (pi_mono) error reads `status code <n>`.
    expect(chatErrorStatus('HTTP 429')).toBe(429)
    expect(chatErrorStatus('Request failed with status code 429')).toBe(429)
    expect(chatErrorStatus('status 503')).toBe(503)
    expect(chatErrorStatus('the model exploded')).toBeNull()
    expect(chatErrorStatus('')).toBeNull()
    expect(chatErrorStatus(null)).toBeNull()
  })

  describe('with navigator.onLine === false', () => {
    afterEach(() => {
      Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
    })
    it('maps a status-less error to the offline copy when the browser is offline', () => {
      Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })
      expect(friendlyChatError('AbortError')).toBe(
        'You’re offline. Check your connection and try again.'
      )
    })
    it('still prefers an HTTP status over the offline signal (we reached the server)', () => {
      Object.defineProperty(navigator, 'onLine', { value: false, configurable: true })
      expect(friendlyChatError('HTTP 500')).toBe('Omi couldn’t answer right now. Try again.')
    })
  })
})
