import { app, safeStorage, shell, webContents } from 'electron'
import { randomUUID } from 'crypto'
import { readFileSync, writeFileSync, rmSync, mkdirSync, renameSync } from 'fs'
import { join } from 'path'
import { pythonBaseURL, FIREBASE_API_KEY, AUTH_REDIRECT_URI } from './env'
import { clearByokCache } from './secrets'
import type { AuthState } from '../shared/types'

// Same flow as AuthService.swift: browser OAuth via the Python backend, custom-token
// exchange against the Firebase REST API, refresh via securetoken.googleapis.com.

interface StoredAuth {
  idToken: string
  refreshToken: string
  /** epoch ms */
  expiry: number
  uid: string
  email?: string
  name?: string
}

let stored: StoredAuth | null = null
let pendingState: string | null = null
let refreshInFlight: Promise<string | null> | null = null
let authGen = 0 // bumped on sign-out so an in-flight refresh cannot resurrect the session

const authFile = () => join(app.getPath('userData'), 'auth.bin')

// Decodes the JWT payload WITHOUT verifying the signature. Used only for display
// fields (email/name) from Google-origin tokens, never for an auth decision: the
// session uid comes from the Firebase-issued idToken, re-verified server-side.
function decodeJwt(jwt: string): Record<string, any> | null {
  const parts = jwt.split('.')
  if (parts.length < 2) return null
  try {
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(Buffer.from(b64, 'base64').toString('utf8'))
  } catch {
    return null
  }
}

function persist(): void {
  if (!stored) {
    try {
      rmSync(authFile(), { force: true })
    } catch {}
    return
  }
  // Fail closed: the blob holds the long-lived refresh token, so it must never be
  // written to disk unencrypted. DPAPI is effectively always available on Windows
  // 10+; if it somehow is not, keep the session in memory only and clear any file.
  if (!safeStorage.isEncryptionAvailable()) {
    console.warn('auth: OS encryption unavailable, keeping tokens in memory only this session')
    try {
      rmSync(authFile(), { force: true })
    } catch {}
    return
  }
  mkdirSync(app.getPath('userData'), { recursive: true })
  const tmp = authFile() + '.tmp'
  writeFileSync(tmp, safeStorage.encryptString(JSON.stringify(stored)))
  renameSync(tmp, authFile())
}

export function restoreAuth(): void {
  try {
    const raw = readFileSync(authFile())
    // Only trust OS-encrypted blobs. A plaintext file (from an older build or a
    // tampered profile) is not trusted; the user simply signs in again.
    if (!safeStorage.isEncryptionAvailable()) {
      stored = null
      return
    }
    stored = JSON.parse(safeStorage.decryptString(raw))
  } catch {
    stored = null
  }
}

export function getAuthState(): AuthState {
  // Dev-only: OMI_FAKE_AUTH=1 renders the signed-in UI without a real login.
  // Backend calls still 401 (no token), so pages show empty/error states.
  if (!stored && process.env.OMI_FAKE_AUTH === '1') {
    return { signedIn: true, uid: 'dev-preview', email: 'preview@omi.me', name: 'Preview' }
  }
  if (!stored) return { signedIn: false }
  return { signedIn: true, uid: stored.uid, email: stored.email, name: stored.name }
}

function broadcast(): void {
  const state = getAuthState()
  for (const wc of webContents.getAllWebContents()) {
    wc.send('auth:changed', state)
  }
}

export function startSignIn(provider: 'google' | 'apple'): void {
  pendingState = randomUUID()
  const base = pythonBaseURL()
  const url =
    `${base}v1/auth/authorize?provider=${provider}` +
    `&redirect_uri=${encodeURIComponent(AUTH_REDIRECT_URI)}` +
    `&state=${pendingState}`
  shell.openExternal(url)
}

export async function handleAuthCallback(callbackUrl: string): Promise<boolean> {
  let parsed: URL
  try {
    parsed = new URL(callbackUrl)
  } catch {
    return false
  }
  const code = parsed.searchParams.get('code')
  const state = parsed.searchParams.get('state')
  if (!code) return false
  if (!pendingState || state !== pendingState) {
    console.error('auth: state mismatch or no sign-in in progress, rejecting callback')
    return false
  }
  pendingState = null

  const base = pythonBaseURL()
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    redirect_uri: AUTH_REDIRECT_URI,
    use_custom_token: 'true'
  })
  const tokenRes = await fetch(`${base}v1/auth/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString()
  })
  if (!tokenRes.ok) {
    console.error('auth: token exchange failed', tokenRes.status, await tokenRes.text())
    return false
  }
  const tokenJson = (await tokenRes.json()) as { custom_token?: string; id_token?: string }
  if (!tokenJson.custom_token) {
    console.error('auth: no custom_token in response')
    return false
  }

  let email: string | undefined
  let name: string | undefined
  if (tokenJson.id_token) {
    const claims = decodeJwt(tokenJson.id_token)
    email = claims?.email
    name = claims?.given_name || (typeof claims?.name === 'string' ? claims.name.split(' ')[0] : undefined)
  }

  const fbRes = await fetch(
    `https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key=${FIREBASE_API_KEY}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: tokenJson.custom_token, returnSecureToken: true })
    }
  )
  if (!fbRes.ok) {
    console.error('auth: signInWithCustomToken failed', fbRes.status, await fbRes.text())
    return false
  }
  const fb = (await fbRes.json()) as { idToken: string; refreshToken: string; expiresIn: string }
  const claims = decodeJwt(fb.idToken)
  const uid = claims?.user_id || claims?.sub
  if (!uid) {
    console.error('auth: could not extract uid from idToken')
    return false
  }

  stored = {
    idToken: fb.idToken,
    refreshToken: fb.refreshToken,
    expiry: Date.now() + (parseInt(fb.expiresIn, 10) || 3600) * 1000,
    uid,
    email,
    name
  }
  persist()
  broadcast()
  return true
}

async function refreshToken(): Promise<string | null> {
  if (!stored) return null
  const myGen = authGen
  const body = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: stored.refreshToken })
  const res = await fetch(`https://securetoken.googleapis.com/v1/token?key=${FIREBASE_API_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString()
  })
  // A sign-out (or other reset) during the request supersedes this refresh. Never
  // write tokens back over a session the user just signed out of.
  if (authGen !== myGen) return null
  if (!res.ok) {
    console.error('auth: refresh failed', res.status)
    if (res.status === 400) {
      stored = null
      persist()
      broadcast()
    }
    return null
  }
  const json = (await res.json()) as { id_token: string; refresh_token: string; expires_in: string }
  if (authGen !== myGen || !stored) return null
  stored = {
    ...stored,
    idToken: json.id_token,
    refreshToken: json.refresh_token,
    expiry: Date.now() + (parseInt(json.expires_in, 10) || 3600) * 1000
  }
  persist()
  return stored.idToken
}

export async function getValidToken(): Promise<string | null> {
  if (!stored) return null
  if (Date.now() < stored.expiry - 5 * 60 * 1000) return stored.idToken
  if (!refreshInFlight) {
    refreshInFlight = refreshToken().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

/** Force-refresh once after a 401, mirroring APIClient's retry. */
export async function forceRefreshToken(): Promise<string | null> {
  if (!stored) return null
  if (!refreshInFlight) {
    refreshInFlight = refreshToken().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

export function signOut(): void {
  authGen++
  stored = null
  persist()
  broadcast()
  clearByokCache()
}
