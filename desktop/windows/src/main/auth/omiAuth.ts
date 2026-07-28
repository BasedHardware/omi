// Pure helpers for the backend-mediated Omi sign-in flow (Google via
// /v1/auth/authorize + /v1/auth/token, PKCE S256, loopback callback).
// No Electron/IO imports so everything here is unit-testable under node Vitest.
//
// Backend contract (backend/routers/auth.py, mirrored from the macOS app's
// AuthService.swift buildAuthorizationURL / exchangeCodeForToken):
//   GET  {api}/v1/auth/authorize?provider=google&redirect_uri=…&state=…
//        &code_challenge=…&code_challenge_method=S256
//        → 302 to accounts.google.com; Google returns to the BACKEND's own
//        /v1/auth/callback/google, which serves an HTML page that navigates the
//        browser to {redirect_uri}?code=<omi auth code>&state=<our state>.
//   POST {api}/v1/auth/token  (application/x-www-form-urlencoded)
//        grant_type=authorization_code & code & redirect_uri & use_custom_token=true
//        & code_verifier → JSON { custom_token, id_token, … }.
// The PKCE verifier/challenge must be 43–128 chars of [A-Za-z0-9-._~]
// (backend _is_valid_pkce_value); oauthPkce.generateVerifier satisfies this.
import { randomBytes } from 'crypto'
import { base64url } from '../integrations/oauthPkce'

/** Loopback path the backend's callback page redirects to (macOS parity). */
export const CALLBACK_PATH = '/callback'

/** CSRF state in the backend's `<flow_id>|<nonce>` shape — the backend logs
 *  the first segment as auth_flow_id (see _auth_flow_id_from_state). */
export function generateSignInState(): string {
  return `${base64url(randomBytes(6))}|${base64url(randomBytes(16))}`
}

export function buildAuthorizeUrl(args: {
  apiBase: string
  redirectUri: string
  state: string
  codeChallenge: string
}): string {
  const u = new URL(`${args.apiBase.replace(/\/+$/, '')}/v1/auth/authorize`)
  u.searchParams.set('provider', 'google')
  u.searchParams.set('redirect_uri', args.redirectUri)
  u.searchParams.set('state', args.state)
  u.searchParams.set('code_challenge', args.codeChallenge)
  u.searchParams.set('code_challenge_method', 'S256')
  return u.toString()
}

export type LoopbackCallback =
  | { kind: 'ignore' } // not the OAuth callback (favicon probe etc.) → 404
  | { kind: 'error'; message: string } // terminal failure for this flow
  | { kind: 'code'; code: string }

/** Classify a request that hit the loopback listener. `rawUrl` is req.url. */
export function parseLoopbackCallback(rawUrl: string, expectedState: string): LoopbackCallback {
  let url: URL
  try {
    url = new URL(rawUrl, 'http://127.0.0.1')
  } catch {
    return { kind: 'ignore' }
  }
  if (url.pathname !== CALLBACK_PATH) return { kind: 'ignore' }
  const error = url.searchParams.get('error')
  const code = url.searchParams.get('code')
  if (!error && !code) return { kind: 'ignore' }
  const stateMatches = url.searchParams.get('state') === expectedState
  if (error) {
    // State-gate error callbacks too: anything on this machine can hit
    // 127.0.0.1, and without the flow's state a stray local request must not
    // be able to abort a pending sign-in or inject display text — noise, not
    // a flow outcome.
    if (!stateMatches) return { kind: 'ignore' }
    return { kind: 'error', message: `Google authorization failed: ${error}` }
  }
  if (!stateMatches) {
    // A CODE with the wrong state is a real CSRF signal — fail the flow loudly
    // (macOS parity) rather than silently ignoring it.
    return { kind: 'error', message: 'Sign-in rejected: OAuth state mismatch' }
  }
  return { kind: 'code', code: code as string }
}

/** Form body for POST /v1/auth/token — exact field set the backend expects. */
export function buildTokenExchangeBody(args: {
  code: string
  redirectUri: string
  codeVerifier: string
}): URLSearchParams {
  return new URLSearchParams({
    grant_type: 'authorization_code',
    code: args.code,
    redirect_uri: args.redirectUri,
    use_custom_token: 'true',
    code_verifier: args.codeVerifier
  })
}

/** Decode a JWT payload WITHOUT verification — display-only claims (name/email)
 *  from the backend-returned Google id_token. Returns null on any malformation. */
export function decodeJwtClaims(jwt: string): Record<string, unknown> | null {
  const parts = jwt.split('.')
  if (parts.length !== 3) return null
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const parsed = JSON.parse(Buffer.from(b64, 'base64').toString('utf8'))
    return typeof parsed === 'object' && parsed !== null ? parsed : null
  } catch {
    return null
  }
}

/**
 * The Firebase uid from an ID token's `user_id`/`sub` claim (decode, NOT verify).
 *
 * Host-authoritative: the uid comes from the credential ITSELF, not from a
 * separate caller-asserted field a renderer could forge. Returns '' when the
 * token is absent or undecodable — callers treat '' as "no known owner" and must
 * fail closed (never fall back to a shared default identity). Shared by every
 * main-side uid-from-token site (omiListen, pi-mono owner wiring).
 */
export function decodeUidFromIdToken(token: string): string {
  const claims = decodeJwtClaims(token)
  if (!claims) return ''
  const uid = claims.user_id ?? claims.sub
  return typeof uid === 'string' ? uid : ''
}

export type TokenExchangeSuccess = {
  customToken: string
  email?: string
  givenName?: string
  familyName?: string
}

/** Exchange the Omi auth code for a Firebase custom token (+ profile claims). */
export async function exchangeCodeForCustomToken(
  apiBase: string,
  args: { code: string; redirectUri: string; codeVerifier: string },
  fetchImpl: typeof fetch = fetch
): Promise<TokenExchangeSuccess> {
  const res = await fetchImpl(`${apiBase.replace(/\/+$/, '')}/v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: buildTokenExchangeBody(args)
  })
  if (!res.ok) {
    // The backend returns {"detail": "..."} on 4xx — surface that, not raw HTML.
    let detail = ''
    try {
      detail = String(((await res.json()) as { detail?: unknown }).detail ?? '')
    } catch {
      /* non-JSON body */
    }
    throw new Error(`Token exchange failed (${res.status})${detail ? `: ${detail}` : ''}`)
  }
  const json = (await res.json()) as { custom_token?: string; id_token?: string }
  if (!json.custom_token) throw new Error('Token exchange response had no custom_token')

  let email: string | undefined
  let givenName: string | undefined
  let familyName: string | undefined
  const claims = json.id_token ? decodeJwtClaims(json.id_token) : null
  if (claims) {
    email = typeof claims.email === 'string' ? claims.email : undefined
    givenName = typeof claims.given_name === 'string' ? claims.given_name : undefined
    familyName = typeof claims.family_name === 'string' ? claims.family_name : undefined
    // macOS parity: fall back to splitting "name" when given_name is absent.
    if (!givenName && typeof claims.name === 'string' && claims.name.trim()) {
      const parts = claims.name.trim().split(/\s+/)
      givenName = parts[0]
      familyName = parts.length > 1 ? parts.slice(1).join(' ') : undefined
    }
  }
  return { customToken: json.custom_token, email, givenName, familyName }
}

// Minimal branded page shown in the browser tab after the loopback callback.
// Dark, neutral — no purple (brand invariant INV-UI-1).
function callbackHtml(title: string, body: string): string {
  return (
    '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">' +
    '<title>Omi</title></head>' +
    '<body style="margin:0;display:flex;align-items:center;justify-content:center;' +
    'min-height:100vh;background:#121212;color:#fff;' +
    "font-family:'Segoe UI',system-ui,sans-serif\">" +
    '<div style="text-align:center;max-width:420px;padding:2rem">' +
    '<div style="font-size:28px;font-weight:600;letter-spacing:-0.02em;margin-bottom:16px">omi</div>' +
    `<div style="font-size:17px;margin-bottom:8px">${title}</div>` +
    `<div style="font-size:14px;color:rgba(255,255,255,0.6)">${body}</div>` +
    '</div>' +
    // Best-effort: browsers only honor close() for script-opened tabs; the text
    // above is the fallback when it's ignored.
    '<script>window.close()</script></body></html>'
  )
}

export function successHtml(): string {
  return callbackHtml('You&rsquo;re signed in', 'Return to Omi — you can close this tab.')
}

export function errorHtml(message: string): string {
  const safe = message.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  return callbackHtml('Sign-in didn&rsquo;t complete', `${safe}. You can close this tab.`)
}
