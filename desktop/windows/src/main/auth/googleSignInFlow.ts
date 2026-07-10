// Backend-mediated Google sign-in (system browser + loopback callback), main
// process. Ports the macOS app's flow (AuthService.swift signIn(provider:)):
//   1. PKCE verifier/challenge + CSRF state
//   2. loopback HTTP listener on 127.0.0.1:<random port>/callback
//   3. system browser → {api}/v1/auth/authorize (backend drives Google OAuth)
//   4. loopback receives ?code&state → validate → branded page → close listener
//   5. POST {api}/v1/auth/token → Firebase custom token (renderer signs in)
//
// Electron-free by design: the browser opener, fetch, and logger are injected
// so the whole flow is exercisable in unit tests (src/main/auth/*.test.ts).
// Electron wiring lives in src/main/ipc/auth.ts.
import { createServer, type Server } from 'http'
import type { AddressInfo } from 'net'
import { generateVerifier, challengeFromVerifier } from '../integrations/oauthPkce'
import {
  CALLBACK_PATH,
  buildAuthorizeUrl,
  errorHtml,
  exchangeCodeForCustomToken,
  generateSignInState,
  parseLoopbackCallback,
  successHtml
} from './omiAuth'
import type { GoogleSignInResult } from '../../shared/types'

// If the user closes the browser tab / never finishes the consent, no callback
// ever arrives — fail loud after this long instead of hanging forever.
export const SIGN_IN_TIMEOUT_MS = 5 * 60_000

export const CANCELLED_MESSAGE = 'Sign-in was cancelled — the browser never completed it'
export const SUPERSEDED_MESSAGE = 'Superseded by a newer sign-in attempt'

export type GoogleSignInDeps = {
  apiBase: string
  openExternal: (url: string) => void | Promise<void>
  log?: (msg: string, extra?: unknown) => void
  timeoutMs?: number
  fetchImpl?: typeof fetch
}

// One flow at a time: starting a new sign-in supersedes (cancels) the pending
// one, so a stranded browser tab can't block a retry for five minutes.
let activeCancel: ((message: string) => void) | null = null

/** Truncate secrets in the authorize URL before it goes to a persistent log:
 *  the full state would let a log reader complete a pending callback, and the
 *  challenge is unnecessary noise. 8 chars keep debugging correlation (state's
 *  first segment is the flow id the backend logs as auth_flow_id). */
export function redactAuthorizeUrl(authorizeUrl: string): string {
  const u = new URL(authorizeUrl)
  for (const key of ['state', 'code_challenge']) {
    const v = u.searchParams.get(key)
    if (v) u.searchParams.set(key, `${v.slice(0, 8)}…`)
  }
  return u.toString()
}

/** Run the full sign-in flow. Never rejects — errors come back as {ok:false}. */
export async function startGoogleSignIn(deps: GoogleSignInDeps): Promise<GoogleSignInResult> {
  activeCancel?.(SUPERSEDED_MESSAGE)
  const log = deps.log ?? ((): void => {})

  const codeVerifier = generateVerifier()
  const codeChallenge = challengeFromVerifier(codeVerifier)
  const state = generateSignInState()

  let loopback: { code: string; redirectUri: string }
  try {
    loopback = await runLoopback({ state, codeChallenge, deps, log })
  } catch (e) {
    const error = (e as Error).message
    log('sign-in failed before token exchange', { error })
    return { ok: false, error }
  }

  log('callback validated — exchanging code for custom token')
  try {
    const token = await exchangeCodeForCustomToken(
      deps.apiBase,
      { code: loopback.code, redirectUri: loopback.redirectUri, codeVerifier },
      deps.fetchImpl ?? fetch
    )
    log('token exchange ok', { hasEmail: !!token.email })
    return {
      ok: true,
      customToken: token.customToken,
      email: token.email,
      givenName: token.givenName,
      familyName: token.familyName
    }
  } catch (e) {
    const error = (e as Error).message
    log('token exchange failed', { error })
    return { ok: false, error }
  }
}

function runLoopback(args: {
  state: string
  codeChallenge: string
  deps: GoogleSignInDeps
  log: (msg: string, extra?: unknown) => void
}): Promise<{ code: string; redirectUri: string }> {
  const { state, codeChallenge, deps, log } = args
  return new Promise((resolve, reject) => {
    let settled = false
    let timer: NodeJS.Timeout | undefined
    const cleanup = (): void => {
      if (timer) clearTimeout(timer)
      if (activeCancel === cancel) activeCancel = null
      server.close()
    }
    const succeed = (v: { code: string; redirectUri: string }): void => {
      if (settled) return
      settled = true
      cleanup()
      resolve(v)
    }
    const fail = (e: Error): void => {
      if (settled) return
      settled = true
      cleanup()
      reject(e)
    }
    const cancel = (message: string): void => fail(new Error(message))
    activeCancel = cancel

    // Captured once in the listen callback and closed over: server.address()
    // returns null once the server is closing, and a kept-alive connection can
    // still deliver requests after cleanup() — never recompute it per request.
    let redirectUri = ''
    const server: Server = createServer((req, res) => {
      // After the flow settles the server is closing, but a kept-alive
      // connection can still replay the callback (F5 on the leftover tab):
      // never re-enter flow logic — answer 404 and move on.
      if (settled) {
        res.writeHead(404).end()
        return
      }
      const outcome = parseLoopbackCallback(req.url ?? '', state)
      if (outcome.kind === 'ignore') {
        res.writeHead(404).end()
        return
      }
      // 200 (not 4xx) for the human-facing error page is deliberate — the
      // browser renders it either way (audit-accepted cosmetic).
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      if (outcome.kind === 'error') {
        res.end(errorHtml(outcome.message))
        log('callback rejected', { error: outcome.message })
        fail(new Error(outcome.message))
        return
      }
      res.end(successHtml())
      succeed({ code: outcome.code, redirectUri })
    })
    server.on('error', fail)
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as AddressInfo
      redirectUri = `http://127.0.0.1:${addr.port}${CALLBACK_PATH}`
      const authorizeUrl = buildAuthorizeUrl({
        apiBase: deps.apiBase,
        redirectUri,
        state,
        codeChallenge
      })
      log('loopback listening, opening system browser', { redirectUri })
      // Stable single-line marker so harnesses (scripts/verify-oauth-flow.mjs)
      // can grep the URL the browser was sent to. Log hygiene: the on-disk log
      // must not hold a usable state or the challenge — keep an 8-char prefix
      // (state's prefix IS the flow id, matching the backend's auth_flow_id).
      log(`authorize-url ${redactAuthorizeUrl(authorizeUrl)}`)
      timer = setTimeout(
        () => fail(new Error(CANCELLED_MESSAGE)),
        deps.timeoutMs ?? SIGN_IN_TIMEOUT_MS
      )
      // async wrapper so a synchronous throw from openExternal is caught too.
      void (async () => deps.openExternal(authorizeUrl))().catch((e) =>
        fail(new Error(`Could not open the browser: ${(e as Error).message}`))
      )
    })
  })
}
