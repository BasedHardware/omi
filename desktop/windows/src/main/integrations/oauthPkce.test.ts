import { describe, it, expect } from 'vitest'
import {
  base64url,
  challengeFromVerifier,
  buildAuthUrl,
  isExpired,
  generateVerifier
} from './oauthPkce'

describe('oauthPkce', () => {
  it('base64url has no +, /, or = padding', () => {
    const s = base64url(Buffer.from([0xfb, 0xff, 0xfe, 0x00]))
    expect(s).not.toMatch(/[+/=]/)
  })

  it('challengeFromVerifier matches the RFC 7636 test vector', () => {
    // RFC 7636 Appendix B
    const verifier = 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
    expect(challengeFromVerifier(verifier)).toBe('E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM')
  })

  it('generateVerifier is 43+ chars, url-safe', () => {
    const v = generateVerifier()
    expect(v.length).toBeGreaterThanOrEqual(43)
    expect(v).not.toMatch(/[+/=]/)
  })

  it('buildAuthUrl includes required params and both scopes', () => {
    const url = buildAuthUrl({
      clientId: 'abc.apps.googleusercontent.com',
      redirectUri: 'http://127.0.0.1:51000',
      challenge: 'CHAL',
      state: 'STATE'
    })
    const u = new URL(url)
    expect(u.origin + u.pathname).toBe('https://accounts.google.com/o/oauth2/v2/auth')
    expect(u.searchParams.get('client_id')).toBe('abc.apps.googleusercontent.com')
    expect(u.searchParams.get('redirect_uri')).toBe('http://127.0.0.1:51000')
    expect(u.searchParams.get('response_type')).toBe('code')
    expect(u.searchParams.get('access_type')).toBe('offline')
    expect(u.searchParams.get('prompt')).toBe('consent')
    expect(u.searchParams.get('code_challenge')).toBe('CHAL')
    expect(u.searchParams.get('code_challenge_method')).toBe('S256')
    expect(u.searchParams.get('state')).toBe('STATE')
    expect(u.searchParams.get('scope')).toContain('gmail.readonly')
    expect(u.searchParams.get('scope')).toContain('calendar.readonly')
  })

  it('isExpired is true within the 60s skew window and false outside', () => {
    const now = 1_000_000
    expect(isExpired(now + 30_000, now)).toBe(true) // 30s left → refresh
    expect(isExpired(now + 120_000, now)).toBe(false) // 2m left → ok
  })
})
