// Hermetic end-to-end test of the sign-in flow: real loopback HTTP listener,
// a fake "browser" (plain http GET back to the redirect_uri), and a mocked
// token endpoint. No Electron, no network beyond 127.0.0.1.
import { describe, it, expect, vi } from 'vitest'
import {
  startGoogleSignIn,
  CANCELLED_MESSAGE,
  SUPERSEDED_MESSAGE,
  type GoogleSignInDeps
} from './googleSignInFlow'

function fakeJwt(payload: Record<string, unknown>): string {
  const b64url = (o: unknown): string =>
    Buffer.from(JSON.stringify(o))
      .toString('base64')
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '')
  return `${b64url({ alg: 'RS256' })}.${b64url(payload)}.sig`
}

const tokenOk = vi.fn(
  async () =>
    new Response(
      JSON.stringify({ custom_token: 'CT-1', id_token: fakeJwt({ email: 'ada@omi.me' }) }),
      { status: 200 }
    )
) as unknown as typeof fetch

/** A fake browser: follow the authorize URL only far enough to hit the loopback
 *  redirect_uri with the given query. Returns the loopback response body. */
function browserThatRedirects(query: (redirectUri: string, state: string) => string) {
  return async (authorizeUrl: string): Promise<void> => {
    const u = new URL(authorizeUrl)
    const redirectUri = u.searchParams.get('redirect_uri') as string
    const state = u.searchParams.get('state') as string
    const res = await fetch(`${redirectUri}?${query(redirectUri, state)}`)
    await res.text()
  }
}

function deps(overrides: Partial<GoogleSignInDeps>): GoogleSignInDeps {
  return {
    apiBase: 'https://api.omi.example',
    openExternal: () => {},
    fetchImpl: tokenOk,
    ...overrides
  }
}

describe('startGoogleSignIn', () => {
  it('completes the full loopback round-trip and token exchange', async () => {
    let capturedAuthorize = ''
    const fetchImpl = vi.fn(async (url: unknown, init?: RequestInit) => {
      const body = init?.body as URLSearchParams
      // The exchange must be bound to the SAME redirect_uri the authorize URL used.
      const authorizeRedirect = new URL(capturedAuthorize).searchParams.get('redirect_uri')
      expect(body.get('redirect_uri')).toBe(authorizeRedirect)
      expect(body.get('grant_type')).toBe('authorization_code')
      expect(body.get('use_custom_token')).toBe('true')
      expect(body.get('code')).toBe('CODE-9')
      expect(body.get('code_verifier')).toMatch(/^[A-Za-z0-9_-]{43,128}$/)
      expect(String(url)).toBe('https://api.omi.example/v1/auth/token')
      return new Response(
        JSON.stringify({ custom_token: 'CT-1', id_token: fakeJwt({ email: 'ada@omi.me' }) }),
        { status: 200 }
      )
    }) as unknown as typeof fetch

    const result = await startGoogleSignIn(
      deps({
        fetchImpl,
        openExternal: async (url) => {
          capturedAuthorize = url
          await browserThatRedirects(
            (_r, state) => `code=CODE-9&state=${encodeURIComponent(state)}`
          )(url)
        }
      })
    )
    expect(result).toEqual({
      ok: true,
      customToken: 'CT-1',
      email: 'ada@omi.me',
      givenName: undefined,
      familyName: undefined
    })
    expect(capturedAuthorize).toContain('/v1/auth/authorize?provider=google')
  })

  it('rejects a state mismatch without exchanging the code', async () => {
    const fetchImpl = vi.fn() as unknown as typeof fetch
    const result = await startGoogleSignIn(
      deps({
        fetchImpl,
        openExternal: browserThatRedirects(() => 'code=CODE&state=WRONG')
      })
    )
    expect(result).toEqual({ ok: false, error: expect.stringMatching(/state mismatch/) })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('surfaces a provider error from the callback', async () => {
    const result = await startGoogleSignIn(
      deps({ openExternal: browserThatRedirects(() => 'error=access_denied') })
    )
    expect(result).toEqual({
      ok: false,
      error: 'Google authorization failed: access_denied'
    })
  })

  it('times out as cancelled when the browser never comes back', async () => {
    const result = await startGoogleSignIn(deps({ timeoutMs: 30 }))
    expect(result).toEqual({ ok: false, error: CANCELLED_MESSAGE })
  })

  it('a second attempt supersedes the pending one, which frees its port', async () => {
    let firstRedirect = ''
    const first = startGoogleSignIn(
      deps({
        timeoutMs: 5_000,
        openExternal: (url) => {
          firstRedirect = new URL(url).searchParams.get('redirect_uri') as string
        }
      })
    )
    // Let the first flow get its listener up.
    await vi.waitFor(() => expect(firstRedirect).not.toBe(''))

    const second = await startGoogleSignIn(
      deps({
        openExternal: browserThatRedirects(
          (_r, state) => `code=C2&state=${encodeURIComponent(state)}`
        )
      })
    )
    expect(second.ok).toBe(true)
    expect(await first).toEqual({ ok: false, error: SUPERSEDED_MESSAGE })
    // The superseded flow's listener is closed — its port no longer answers.
    await expect(fetch(`${firstRedirect}?code=x&state=y`)).rejects.toThrow()
  })

  it('ignores stray requests (favicon) instead of failing the flow', async () => {
    const result = await startGoogleSignIn(
      deps({
        openExternal: async (url) => {
          const u = new URL(url)
          const redirectUri = u.searchParams.get('redirect_uri') as string
          const state = u.searchParams.get('state') as string
          const origin = new URL(redirectUri).origin
          const stray = await fetch(`${origin}/favicon.ico`)
          expect(stray.status).toBe(404)
          await fetch(`${redirectUri}?code=OK&state=${encodeURIComponent(state)}`)
        }
      })
    )
    expect(result.ok).toBe(true)
  })

  it('fails fast when the browser cannot be opened', async () => {
    const result = await startGoogleSignIn(
      deps({
        openExternal: () => {
          throw new Error('no handler')
        }
      })
    )
    expect(result).toEqual({ ok: false, error: 'Could not open the browser: no handler' })
  })
})
