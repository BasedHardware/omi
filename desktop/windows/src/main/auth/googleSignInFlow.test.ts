// Hermetic end-to-end test of the sign-in flow: real loopback HTTP listener,
// a fake "browser" (plain http GET back to the redirect_uri), and a mocked
// token endpoint. No Electron, no network beyond 127.0.0.1.
import { describe, it, expect, vi } from 'vitest'
import { connect as netConnect } from 'node:net'
import {
  startGoogleSignIn,
  redactAuthorizeUrl,
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

  it('surfaces a provider error that carries the matching state', async () => {
    const result = await startGoogleSignIn(
      deps({
        openExternal: browserThatRedirects(
          (_r, state) => `error=access_denied&state=${encodeURIComponent(state)}`
        )
      })
    )
    expect(result).toEqual({
      ok: false,
      error: 'Google authorization failed: access_denied'
    })
  })

  it('an error injection without the state cannot abort the pending flow', async () => {
    const result = await startGoogleSignIn(
      deps({
        openExternal: async (url) => {
          const u = new URL(url)
          const redirectUri = u.searchParams.get('redirect_uri') as string
          const state = u.searchParams.get('state') as string
          // Stateless local injection first — must be treated as noise…
          const inject = await fetch(`${redirectUri}?error=access_denied`)
          expect(inject.status).toBe(404)
          // …and the real callback still completes the flow afterwards.
          await fetch(`${redirectUri}?code=OK&state=${encodeURIComponent(state)}`)
        }
      })
    )
    expect(result.ok).toBe(true)
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

  it('a replayed callback on the same connection after success is a 404, not a crash', async () => {
    // Regression (audit M1): the request handler used to recompute
    // server.address() per request — null once the server is closing — so a
    // kept-alive replay of /callback after success threw a TypeError. Pipeline
    // TWO identical code-carrying requests on ONE socket: the first settles the
    // flow (and closes the server); the second is already in flight on the
    // still-open connection and must get a plain 404 with no state change.
    let transcript: Promise<string> = Promise.resolve('')
    const result = await startGoogleSignIn(
      deps({
        openExternal: (url) => {
          const u = new URL(url)
          const r = new URL(u.searchParams.get('redirect_uri') as string)
          const state = u.searchParams.get('state') as string
          const path = `${r.pathname}?code=OK&state=${encodeURIComponent(state)}`
          transcript = pipelinedRequests(Number(r.port), [path, path])
        }
      })
    )
    expect(result.ok).toBe(true) // first request won; replay changed nothing
    const raw = await transcript
    const statuses = [...raw.matchAll(/HTTP\/1\.1 (\d{3})/g)].map((m) => m[1])
    expect(statuses).toEqual(['200', '404'])
  })

  it('logs a redacted authorize URL (no full state or code_challenge on disk)', async () => {
    const lines: string[] = []
    let fullState = ''
    let fullChallenge = ''
    const result = await startGoogleSignIn(
      deps({
        log: (msg, extra) =>
          lines.push(`${msg}${extra !== undefined ? JSON.stringify(extra) : ''}`),
        openExternal: async (url) => {
          const u = new URL(url)
          fullState = u.searchParams.get('state') as string
          fullChallenge = u.searchParams.get('code_challenge') as string
          await browserThatRedirects((_r, state) => `code=OK&state=${encodeURIComponent(state)}`)(
            url
          )
        }
      })
    )
    expect(result.ok).toBe(true)
    const joined = lines.join('\n')
    expect(joined).toContain('authorize-url')
    // The flow-id prefix (8 chars, = backend auth_flow_id) stays for correlation…
    expect(joined).toContain(fullState.slice(0, 8))
    // …but neither the state's nonce half nor the challenge may hit the log.
    expect(joined).not.toContain(fullState.split('|')[1])
    expect(joined).not.toContain(fullChallenge)
  })
})

describe('redactAuthorizeUrl', () => {
  it('truncates state and code_challenge to an 8-char prefix', () => {
    const url =
      'https://api.omi.me/v1/auth/authorize?provider=google&redirect_uri=http%3A%2F%2F127.0.0.1%3A1%2Fcallback' +
      '&state=AAAABBBB%7Ccccccccccccccccccccccc&code_challenge=DDDDEEEEffffgggghhhhiiiijjjjkkkkllllmmmmnnn' +
      '&code_challenge_method=S256'
    const out = new URL(redactAuthorizeUrl(url))
    expect(out.searchParams.get('state')).toBe('AAAABBBB…')
    expect(out.searchParams.get('code_challenge')).toBe('DDDDEEEE…')
    // Everything else is untouched.
    expect(out.searchParams.get('provider')).toBe('google')
    expect(out.searchParams.get('redirect_uri')).toBe('http://127.0.0.1:1/callback')
    expect(out.searchParams.get('code_challenge_method')).toBe('S256')
  })
})

/** Write several raw HTTP/1.1 requests back-to-back on one socket (pipelining)
 *  and return the concatenated response bytes. Keeps the connection active so
 *  server.close() (Node ≥19 closes IDLE connections) can't sidestep the replay. */
function pipelinedRequests(port: number, paths: string[]): Promise<string> {
  return new Promise((resolve) => {
    const sock = netConnect(port, '127.0.0.1', () => {
      for (const p of paths) {
        sock.write(`GET ${p} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: keep-alive\r\n\r\n`)
      }
    })
    let buf = ''
    const timer = setTimeout(() => {
      sock.destroy()
      resolve(buf)
    }, 2000)
    sock.on('data', (d) => {
      buf += String(d)
    })
    sock.on('close', () => {
      clearTimeout(timer)
      resolve(buf)
    })
    // A reset AFTER the responses were read must not fail the test — resolve
    // with whatever arrived; the assertions on the transcript decide.
    sock.on('error', () => {
      clearTimeout(timer)
      resolve(buf)
    })
  })
}
