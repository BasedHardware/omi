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

    const server: Server = createServer((req, res) => {
      const outcome = parseLoopbackCallback(req.url ?? '', state)
      if (outcome.kind === 'ignore') {
        res.writeHead(404).end()
        return
      }
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      if (outcome.kind === 'error') {
        res.end(errorHtml(outcome.message))
        log('callback rejected', { error: outcome.message })
        fail(new Error(outcome.message))
        return
      }
      res.end(successHtml())
      const addr = server.address() as AddressInfo
      succeed({ code: outcome.code, redirectUri: `http://127.0.0.1:${addr.port}${CALLBACK_PATH}` })
    })
    server.on('error', fail)
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as AddressInfo
      const redirectUri = `http://127.0.0.1:${addr.port}${CALLBACK_PATH}`
      const authorizeUrl = buildAuthorizeUrl({
        apiBase: deps.apiBase,
        redirectUri,
        state,
        codeChallenge
      })
      log('loopback listening, opening system browser', { redirectUri })
      // Stable single-line marker so harnesses (scripts/verify-oauth-flow.mjs)
      // can grep the exact URL the browser was sent to.
      log(`authorize-url ${authorizeUrl}`)
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
