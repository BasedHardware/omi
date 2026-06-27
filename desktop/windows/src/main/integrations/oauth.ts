// Google OAuth 2.0 PKCE loopback flow + token lifecycle (main process).
// The access token lives only in memory for this process run; the refresh token
// is persisted (encrypted) via tokenStore.
import { app, shell, BrowserWindow } from 'electron'
import { createServer, type Server } from 'http'
import type { AddressInfo } from 'net'
import { appendFileSync } from 'fs'
import { join } from 'path'
import {
  generateVerifier,
  challengeFromVerifier,
  generateState,
  buildAuthUrl,
  isExpired
} from './oauthPkce'
import { saveRefreshToken, loadRefreshToken, clearRefreshToken } from './tokenStore'

const TOKEN_URL = 'https://oauth2.googleapis.com/token'
const GMAIL_PROFILE_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/profile'

// If the user never finishes the browser consent (e.g. stalls on Google's
// "unverified app" interstitial), Google never redirects to our loopback and
// the flow would otherwise hang forever. Fail loud after this long instead.
const LOOPBACK_TIMEOUT_MS = 5 * 60_000

// Diagnostics: main-process console.log only reaches the dev-server terminal,
// which is easy to miss. Also append to userData/google-oauth.log so the flow
// can be traced after the fact regardless of where the user is looking.
function oauthLog(msg: string, extra?: unknown): void {
  const line = `[${new Date().toISOString()}] ${msg}${extra !== undefined ? ' ' + JSON.stringify(extra) : ''}`
  console.log('[google-oauth]', line)
  try {
    appendFileSync(join(app.getPath('userData'), 'google-oauth.log'), line + '\n')
  } catch {
    /* best-effort logging only */
  }
}

// Bring the Omi window back to the foreground after the OAuth callback lands so
// the user doesn't have to alt-tab back from the browser themselves.
function focusOmi(): void {
  const win = BrowserWindow.getAllWindows()[0]
  if (!win) return
  if (win.isMinimized()) win.restore()
  // Windows blocks a background app from stealing foreground focus from the
  // browser — a plain focus() only flashes the taskbar. Briefly forcing the
  // window above all others makes show()/focus() actually surface it.
  win.setAlwaysOnTop(true)
  win.show()
  win.focus()
  win.setAlwaysOnTop(false)
  app.focus({ steal: true })
}

function clientId(): string {
  const id = import.meta.env.MAIN_VITE_GOOGLE_CLIENT_ID
  if (!id) throw new Error('Google client id not configured (set MAIN_VITE_GOOGLE_CLIENT_ID in .env)')
  return id
}

// Google's "Desktop app" OAuth clients are issued a client secret and require it
// at the token endpoint even with PKCE (omitting it yields invalid_client). The
// secret isn't truly confidential for an installed app; we keep it main-only and
// send it when configured. Left unset, the flow stays pure-PKCE for client types
// that don't need a secret.
function clientSecret(): string | undefined {
  return import.meta.env.MAIN_VITE_GOOGLE_CLIENT_SECRET || undefined
}

// Append client_secret to a token-request body when one is configured.
function withClientSecret(body: URLSearchParams): URLSearchParams {
  const secret = clientSecret()
  if (secret) body.set('client_secret', secret)
  return body
}

type TokenResponse = { access_token: string; refresh_token?: string; expires_in: number }

// In-memory access token cache for this process run.
let accessToken: string | null = null
let accessExpiryMs = 0

/** Run the full PKCE loopback flow. Resolves with the connected account email. */
export async function connect(): Promise<{ email: string }> {
  oauthLog('connect() invoked', { hasClientSecret: !!clientSecret() })
  const verifier = generateVerifier()
  const challenge = challengeFromVerifier(verifier)
  const state = generateState()

  const { code, redirectUri } = await runLoopback(state, challenge)
  const tokens = await exchangeCode(code, verifier, redirectUri)
  oauthLog('token exchange ok', { hasRefresh: !!tokens.refresh_token })
  if (!tokens.refresh_token) {
    throw new Error('Google did not return a refresh token — revoke prior access and retry')
  }
  accessToken = tokens.access_token
  accessExpiryMs = Date.now() + tokens.expires_in * 1000
  const email = await fetchEmail(tokens.access_token)
  saveRefreshToken(tokens.refresh_token, email)
  oauthLog('connected', { email: email || '(email unavailable)' })
  return { email }
}

function runLoopback(
  state: string,
  challenge: string
): Promise<{ code: string; redirectUri: string }> {
  return new Promise((resolve, reject) => {
    let settled = false
    let timer: NodeJS.Timeout
    const cleanup = (): void => {
      clearTimeout(timer)
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

    const server: Server = createServer((req, res) => {
      try {
        const url = new URL(req.url ?? '', 'http://127.0.0.1')
        if (!url.searchParams.has('code') && !url.searchParams.has('error')) {
          res.writeHead(404).end()
          return
        }
        const err = url.searchParams.get('error')
        const code = url.searchParams.get('code')
        const gotState = url.searchParams.get('state')
        res.writeHead(200, { 'Content-Type': 'text/html' })
        res.end(
          '<html><body style="font-family:sans-serif;padding:2rem">' +
            'Connected to Omi. You can close this tab.' +
            // Best-effort: browsers only honor this for script-opened tabs, so the
            // text above is the fallback when the close is ignored.
            '<script>window.close()</script></body></html>'
        )
        oauthLog('callback received', { hasCode: !!code, error: err ?? undefined })
        focusOmi()
        if (err) return fail(new Error(`Google authorization failed: ${err}`))
        if (gotState !== state) return fail(new Error('OAuth state mismatch'))
        if (!code) return fail(new Error('No authorization code returned'))
        const addr = server.address() as AddressInfo
        succeed({ code, redirectUri: `http://127.0.0.1:${addr.port}` })
      } catch (e) {
        fail(e as Error)
      }
    })
    server.on('error', fail)
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address() as AddressInfo
      const redirectUri = `http://127.0.0.1:${addr.port}`
      oauthLog('loopback listening, opening consent', { redirectUri })
      const authUrl = buildAuthUrl({ clientId: clientId(), redirectUri, challenge, state })
      void shell.openExternal(authUrl)
      timer = setTimeout(() => {
        oauthLog('timed out waiting for the OAuth callback')
        fail(
          new Error(
            'Timed out waiting for Google. In the browser, finish the consent: ' +
              'Advanced → Go to Omi (unsafe) → Allow, then reconnect.'
          )
        )
      }, LOOPBACK_TIMEOUT_MS)
    })
  })
}

async function exchangeCode(
  code: string,
  verifier: string,
  redirectUri: string
): Promise<TokenResponse> {
  const body = withClientSecret(
    new URLSearchParams({
      client_id: clientId(),
      code,
      code_verifier: verifier,
      grant_type: 'authorization_code',
      redirect_uri: redirectUri
    })
  )
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (!res.ok) throw new Error(`Token exchange failed: ${res.status} ${await res.text()}`)
  return (await res.json()) as TokenResponse
}

/** A valid access token, refreshing if necessary. Throws 'not_connected' when no
 *  refresh token is stored, 'invalid_grant' when the grant was revoked. */
export async function getAccessToken(): Promise<string> {
  if (accessToken && !isExpired(accessExpiryMs)) return accessToken
  const stored = loadRefreshToken()
  if (!stored) throw new Error('not_connected')
  const body = withClientSecret(
    new URLSearchParams({
      client_id: clientId(),
      refresh_token: stored.refreshToken,
      grant_type: 'refresh_token'
    })
  )
  const res = await fetch(TOKEN_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body
  })
  if (res.status === 400 || res.status === 401) {
    const text = await res.text()
    if (text.includes('invalid_grant')) {
      clearRefreshToken()
      accessToken = null
      accessExpiryMs = 0
      throw new Error('invalid_grant')
    }
    throw new Error(`Token refresh failed: ${res.status} ${text}`)
  }
  if (!res.ok) throw new Error(`Token refresh failed: ${res.status} ${await res.text()}`)
  const tokens = (await res.json()) as TokenResponse
  accessToken = tokens.access_token
  accessExpiryMs = Date.now() + tokens.expires_in * 1000
  return accessToken
}

/** Drop the cached access token so the next getAccessToken() forces a refresh. */
export function invalidateAccessToken(): void {
  accessToken = null
  accessExpiryMs = 0
}

// The account email comes from the Gmail profile endpoint (covered by
// gmail.readonly) so we don't need to request an extra userinfo/email scope.
async function fetchEmail(token: string): Promise<string> {
  try {
    const res = await fetch(GMAIL_PROFILE_URL, { headers: { Authorization: `Bearer ${token}` } })
    if (!res.ok) return ''
    const j = (await res.json()) as { emailAddress?: string }
    return j.emailAddress ?? ''
  } catch {
    return ''
  }
}

export function disconnect(): void {
  clearRefreshToken()
  invalidateAccessToken()
}

export function isConnected(): boolean {
  return loadRefreshToken() !== null
}

export function connectedEmail(): string | undefined {
  return loadRefreshToken()?.email
}
