// Shared auth bootstrap for node-side harnesses (the diag probe and the PTT live
// E2E suite): .env parsing, Firebase refresh-token → ID-token exchange, and JWT
// payload decoding. One copy so env-var names and the exchange contract can't
// fork between scripts.
import fs from 'node:fs'

/** Parse desktop/windows/.env (CRLF-safe). Returns {} if the file is missing. */
export function readDotEnv(envPath) {
  const out = {}
  try {
    for (const line of fs.readFileSync(envPath, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^([A-Z0-9_]+)=(.*)$/)
      if (m) out[m[1]] = m[2].trim()
    }
  } catch {
    /* no .env — process env only */
  }
  return out
}

/** Decode (not verify) a JWT payload; null if malformed. */
export function decodeJwt(token) {
  try {
    return JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString('utf8'))
  } catch {
    return null
  }
}

/** Exchange a Firebase refresh token for a fresh ~1h ID token via the
 *  securetoken REST API. */
export async function exchangeRefreshToken(refreshToken, firebaseApiKey) {
  if (!firebaseApiKey) throw new Error('VITE_FIREBASE_API_KEY missing (needed for refresh-token exchange)')
  const res = await fetch(`https://securetoken.googleapis.com/v1/token?key=${firebaseApiKey}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: refreshToken.trim() })
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(`securetoken exchange failed: HTTP ${res.status} ${JSON.stringify(data).slice(0, 200)}`)
  }
  return data.id_token
}
