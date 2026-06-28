// Pure PKCE + auth-URL helpers for the Google OAuth loopback flow (parity 3d).
// No Electron/IO imports here so it's unit-testable under node Vitest.
import { createHash, randomBytes } from 'crypto'

const SCOPES = [
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/calendar.readonly'
]

const AUTH_ENDPOINT = 'https://accounts.google.com/o/oauth2/v2/auth'

export function base64url(buf: Buffer): string {
  return buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** 43-char (256-bit) high-entropy code verifier. */
export function generateVerifier(): string {
  return base64url(randomBytes(32))
}

export function challengeFromVerifier(verifier: string): string {
  return base64url(createHash('sha256').update(verifier).digest())
}

export function generateState(): string {
  return base64url(randomBytes(16))
}

export function buildAuthUrl(params: {
  clientId: string
  redirectUri: string
  challenge: string
  state: string
}): string {
  const q = new URLSearchParams({
    client_id: params.clientId,
    redirect_uri: params.redirectUri,
    response_type: 'code',
    scope: SCOPES.join(' '),
    access_type: 'offline',
    prompt: 'consent',
    code_challenge: params.challenge,
    code_challenge_method: 'S256',
    state: params.state
  })
  return `${AUTH_ENDPOINT}?${q.toString()}`
}

/** True when the access token is within 60s of expiry (so we refresh early). */
export function isExpired(expiryMs: number, now: number = Date.now()): boolean {
  return now >= expiryMs - 60_000
}
