import { describe, it, expect, vi } from 'vitest'
import {
  CALLBACK_PATH,
  buildAuthorizeUrl,
  buildTokenExchangeBody,
  decodeJwtClaims,
  decodeUidFromIdToken,
  errorHtml,
  exchangeCodeForCustomToken,
  generateSignInState,
  parseLoopbackCallback,
  successHtml
} from './omiAuth'

function fakeJwt(payload: Record<string, unknown>): string {
  const b64url = (o: unknown): string =>
    Buffer.from(JSON.stringify(o))
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
  return `${b64url({ alg: 'RS256' })}.${b64url(payload)}.sig`
}

describe('buildAuthorizeUrl', () => {
  // Exact backend contract: backend/routers/auth.py auth_authorize (and macOS
  // AuthService.swift buildAuthorizationURL) — provider, redirect_uri, state,
  // code_challenge, code_challenge_method=S256.
  it('matches the /v1/auth/authorize contract', () => {
    const url = buildAuthorizeUrl({
      apiBase: 'https://api.omi.me',
      redirectUri: 'http://127.0.0.1:51000/callback',
      state: 'flow|nonce',
      codeChallenge: 'CHAL'
    })
    const u = new URL(url)
    expect(u.origin + u.pathname).toBe('https://api.omi.me/v1/auth/authorize')
    expect(u.searchParams.get('provider')).toBe('google')
    expect(u.searchParams.get('redirect_uri')).toBe('http://127.0.0.1:51000/callback')
    expect(u.searchParams.get('state')).toBe('flow|nonce')
    expect(u.searchParams.get('code_challenge')).toBe('CHAL')
    expect(u.searchParams.get('code_challenge_method')).toBe('S256')
    expect([...u.searchParams.keys()]).toHaveLength(5)
  })

  it('tolerates a trailing slash on the api base', () => {
    const url = buildAuthorizeUrl({
      apiBase: 'https://api.omi.me/',
      redirectUri: 'http://127.0.0.1:1/callback',
      state: 's',
      codeChallenge: 'c'
    })
    expect(url.startsWith('https://api.omi.me/v1/auth/authorize?')).toBe(true)
  })
})

describe('generateSignInState', () => {
  it('is flow_id|nonce shaped (backend logs the first segment) and unique', () => {
    const a = generateSignInState()
    const b = generateSignInState()
    expect(a).toMatch(/^[A-Za-z0-9_-]{8}\|[A-Za-z0-9_-]{22}$/)
    expect(a).not.toBe(b)
  })
})

describe('parseLoopbackCallback', () => {
  const state = 'flow|nonce'

  it('ignores non-callback paths (favicon probes)', () => {
    expect(parseLoopbackCallback('/favicon.ico', state)).toEqual({ kind: 'ignore' })
    expect(
      parseLoopbackCallback(`/other?code=x&state=${encodeURIComponent(state)}`, state)
    ).toEqual({
      kind: 'ignore'
    })
  })

  it('ignores a bare /callback with neither code nor error', () => {
    expect(parseLoopbackCallback(CALLBACK_PATH, state)).toEqual({ kind: 'ignore' })
  })

  it('accepts a valid code + matching state', () => {
    expect(
      parseLoopbackCallback(`/callback?code=abc123&state=${encodeURIComponent(state)}`, state)
    ).toEqual({ kind: 'code', code: 'abc123' })
  })

  it('rejects a state mismatch (CSRF)', () => {
    const out = parseLoopbackCallback('/callback?code=abc&state=evil', state)
    expect(out.kind).toBe('error')
    expect((out as { message: string }).message).toMatch(/state mismatch/)
  })

  it('rejects a missing state even with a code', () => {
    expect(parseLoopbackCallback('/callback?code=abc', state).kind).toBe('error')
  })

  it('surfaces provider errors that carry the matching state', () => {
    const out = parseLoopbackCallback(
      `/callback?error=access_denied&state=${encodeURIComponent(state)}`,
      state
    )
    expect(out).toEqual({ kind: 'error', message: 'Google authorization failed: access_denied' })
  })

  it('ignores error injections without the matching state (local-DoS guard)', () => {
    // Any local process can hit 127.0.0.1 — without the state it must not be
    // able to abort a pending sign-in or inject display text.
    expect(parseLoopbackCallback('/callback?error=access_denied', state)).toEqual({
      kind: 'ignore'
    })
    expect(parseLoopbackCallback('/callback?error=<b>evil</b>&state=WRONG', state)).toEqual({
      kind: 'ignore'
    })
  })
})

describe('buildTokenExchangeBody', () => {
  // Exact backend contract: POST /v1/auth/token is Form(...) — form-encoded,
  // grant_type=authorization_code, use_custom_token=true (macOS parity).
  it('matches the /v1/auth/token form contract', () => {
    const body = buildTokenExchangeBody({
      code: 'CODE',
      redirectUri: 'http://127.0.0.1:51000/callback',
      codeVerifier: 'VERIFIER'
    })
    expect(body.get('grant_type')).toBe('authorization_code')
    expect(body.get('code')).toBe('CODE')
    expect(body.get('redirect_uri')).toBe('http://127.0.0.1:51000/callback')
    expect(body.get('use_custom_token')).toBe('true')
    expect(body.get('code_verifier')).toBe('VERIFIER')
    expect([...body.keys()]).toHaveLength(5)
  })
})

describe('decodeJwtClaims', () => {
  it('decodes the payload without verification', () => {
    expect(decodeJwtClaims(fakeJwt({ email: 'a@b.c', given_name: 'Ada' }))).toMatchObject({
      email: 'a@b.c',
      given_name: 'Ada'
    })
  })

  it('returns null on malformed input', () => {
    expect(decodeJwtClaims('not-a-jwt')).toBeNull()
    expect(decodeJwtClaims('a.!!!.c')).toBeNull()
  })
})

describe('decodeUidFromIdToken', () => {
  it('reads the uid from the user_id claim', () => {
    expect(decodeUidFromIdToken(fakeJwt({ user_id: 'uid-A' }))).toBe('uid-A')
  })

  it('falls back to the sub claim when user_id is absent', () => {
    expect(decodeUidFromIdToken(fakeJwt({ sub: 'uid-B' }))).toBe('uid-B')
  })

  it('prefers user_id over sub (Firebase ID tokens carry both)', () => {
    expect(decodeUidFromIdToken(fakeJwt({ user_id: 'uid-A', sub: 'uid-B' }))).toBe('uid-A')
  })

  it('returns "" for an undecodable / forged token — never guesses an identity', () => {
    expect(decodeUidFromIdToken('not-a-jwt')).toBe('')
    expect(decodeUidFromIdToken('a.!!!.c')).toBe('')
    expect(decodeUidFromIdToken('')).toBe('')
    // A well-formed JWT with no uid claim is still "no owner", not a partial one.
    expect(decodeUidFromIdToken(fakeJwt({ email: 'a@b.c' }))).toBe('')
    // A non-string claim must not be coerced into an owner id.
    expect(decodeUidFromIdToken(fakeJwt({ user_id: 42 }))).toBe('')
  })
})

describe('exchangeCodeForCustomToken', () => {
  const args = { code: 'C', redirectUri: 'http://127.0.0.1:1/callback', codeVerifier: 'V' }

  it('POSTs form-encoded and returns token + id_token claims', async () => {
    const fetchImpl = vi.fn(async (url: unknown, init?: RequestInit) => {
      expect(String(url)).toBe('https://api.omi.me/v1/auth/token')
      expect(init?.method).toBe('POST')
      expect((init?.headers as Record<string, string>)['Content-Type']).toBe(
        'application/x-www-form-urlencoded'
      )
      expect(init?.body).toBeInstanceOf(URLSearchParams)
      return new Response(
        JSON.stringify({
          custom_token: 'CT',
          id_token: fakeJwt({ email: 'ada@omi.me', given_name: 'Ada', family_name: 'Lovelace' })
        }),
        { status: 200 }
      )
    }) as unknown as typeof fetch
    const out = await exchangeCodeForCustomToken('https://api.omi.me', args, fetchImpl)
    expect(out).toEqual({
      customToken: 'CT',
      email: 'ada@omi.me',
      givenName: 'Ada',
      familyName: 'Lovelace'
    })
  })

  it('falls back to splitting the "name" claim (macOS parity)', async () => {
    const fetchImpl = (async () =>
      new Response(
        JSON.stringify({ custom_token: 'CT', id_token: fakeJwt({ name: 'Ada King Lovelace' }) }),
        { status: 200 }
      )) as unknown as typeof fetch
    const out = await exchangeCodeForCustomToken('https://api.omi.me', args, fetchImpl)
    expect(out.givenName).toBe('Ada')
    expect(out.familyName).toBe('King Lovelace')
  })

  it('surfaces the backend detail on 4xx', async () => {
    const fetchImpl = (async () =>
      new Response(JSON.stringify({ detail: 'Invalid or expired code' }), {
        status: 400
      })) as unknown as typeof fetch
    await expect(exchangeCodeForCustomToken('https://api.omi.me', args, fetchImpl)).rejects.toThrow(
      /Token exchange failed \(400\): Invalid or expired code/
    )
  })

  it('rejects a 200 with no custom_token', async () => {
    const fetchImpl = (async () =>
      new Response(JSON.stringify({ id_token: 'x' }), { status: 200 })) as unknown as typeof fetch
    await expect(exchangeCodeForCustomToken('https://api.omi.me', args, fetchImpl)).rejects.toThrow(
      /no custom_token/
    )
  })
})

describe('callback pages', () => {
  it('are dark, branded, and purple-free (INV-UI-1)', () => {
    for (const html of [successHtml(), errorHtml('Nope <script>')]) {
      expect(html).toContain('#121212')
      expect(html).toContain('omi')
      expect(html.toLowerCase()).not.toMatch(/purple|#a855f7|#8b5cf6|#7c3aed/)
    }
  })

  it('escapes error text', () => {
    expect(errorHtml('<img onerror=x>')).not.toContain('<img')
  })
})
