// Main-side VERIFICATION of a relayed Firebase ID token.
//
// WHY THIS EXISTS (security). The control-plane owner scopes every local kernel
// chat session/surface row to an account. On Windows the Firebase session lives
// ONLY in the renderer, which relays the ID token to main via `pimono:setSession`.
// A DECODE of that token (auth/omiAuth.ts `decodeUidFromIdToken`) is fine for
// display-only uses, but it trusts whatever `sub`/`user_id` the payload claims —
// a compromised renderer could push an UNSIGNED `{user_id: <victim>}` JWT and read
// another local account's kernel chat. Deriving the OWNER therefore requires a real
// signature check: this module returns the `sub` only when the token is a genuine,
// unexpired, Google-signed Firebase ID token for THIS project; otherwise null (the
// caller then fails closed to the default owner, which the cold-start gate refuses).
//
// Verification uses `jose` (RS256-only): correct signature verification against
// Google's rotating x509 certs, built-in exp/iss/aud checks, and — critically — an
// explicit `algorithms: ['RS256']` allow-list that blocks alg-confusion (alg:none,
// HS256-with-the-public-key-as-secret). Hand-rolling `crypto.verify` would require
// re-implementing all of that by hand; jose is a small, zero-dependency, audited
// JOSE implementation, so correctness wins.
//
// TRUST-CRITICAL: the expected project id comes from `import.meta.env`
// (`VITE_FIREBASE_PROJECT_ID`), which electron-vite freezes into the MAIN bundle at
// BUILD time from `.env` (VITE_ prefix → all processes; same mechanism auth.ts uses
// for VITE_OMI_API_BASE). It is NEVER read from the renderer `pimono:setSession`
// payload — a compromised renderer could otherwise supply a project id matching its
// forged token's `aud` and defeat the check. The project id is public config, not a
// secret; the trust requirement is only that its source be main-controlled.
//
// SECURITY: the token is a live ~1h credential — never logged here.
import { decodeProtectedHeader, importX509, jwtVerify } from 'jose'

/** Google's public x509 certs for Firebase ID tokens, keyed by the token's `kid`. */
const SECURETOKEN_CERTS_URL =
  'https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com'

/** Fallback cert TTL when the response carries no usable `Cache-Control: max-age`. */
const DEFAULT_CERT_TTL_MS = 60 * 60 * 1000

type CertMap = Record<string, string>

// Last-good certs kept in memory so hourly token refreshes don't hit the network
// every time, and so a transient blip fetching the cert CDN (while the backend —
// and thus chat — is still reachable) doesn't wrongly reject a real token. On a
// HARD failure with no cached certs we return null → the owner falls back to the
// default and chat fail-closes, which is correct: chat is managed-cloud, so no
// network to fetch certs generally means no network to chat either.
let certCache: { certs: CertMap; expiresAt: number } | null = null

/** The build-time project id this bundle trusts, or '' when unconfigured. */
function expectedProjectId(): string {
  const id = import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined
  return typeof id === 'string' ? id.trim() : ''
}

/** Seconds from a `Cache-Control` header's `max-age`, or the fallback TTL. */
function certTtlMs(cacheControl: string | null): number {
  if (!cacheControl) return DEFAULT_CERT_TTL_MS
  const match = /max-age\s*=\s*(\d+)/i.exec(cacheControl)
  if (!match) return DEFAULT_CERT_TTL_MS
  const seconds = Number(match[1])
  return Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_CERT_TTL_MS
}

/** Fetch + cache the certs, or null on any failure (network/non-2xx/bad body). */
async function fetchCerts(fetchImpl: typeof fetch): Promise<CertMap | null> {
  try {
    const res = await fetchImpl(SECURETOKEN_CERTS_URL)
    if (!res.ok) return null
    const body = (await res.json()) as unknown
    if (!body || typeof body !== 'object') return null
    const certs: CertMap = {}
    for (const [kid, pem] of Object.entries(body as Record<string, unknown>)) {
      if (typeof kid === 'string' && kid && typeof pem === 'string' && pem) certs[kid] = pem
    }
    if (Object.keys(certs).length === 0) return null
    certCache = { certs, expiresAt: Date.now() + certTtlMs(res.headers.get('cache-control')) }
    return certs
  } catch {
    return null
  }
}

/** Fresh-enough certs: the cache while valid, else a re-fetch, else last-good. */
async function signingCerts(fetchImpl: typeof fetch): Promise<CertMap | null> {
  if (certCache && Date.now() < certCache.expiresAt) return certCache.certs
  const fresh = await fetchCerts(fetchImpl)
  if (fresh) return fresh
  // Fetch failed: fall back to the last-good certs even if past max-age (Google
  // keeps rotated certs valid through a grace window), so a CDN blip doesn't reject
  // a real token. Only when we have never fetched any cert do we give up (→ null).
  return certCache?.certs ?? null
}

/**
 * The `sub` (Firebase uid) of a genuine, unexpired, Google-signed Firebase ID
 * token for THIS project, or null. Null on: wrong/absent signature, `alg` != RS256
 * (alg:none / HS256 / confusion), unknown `kid`, expired `exp`, wrong `aud`/`iss`,
 * empty `sub`, cert-fetch failure with no cached cert, or a misconfigured project
 * id. `fetchImpl` is injectable only for hermetic tests; production uses global
 * fetch — the public contract is `verifyFirebaseIdToken(token)`.
 */
export async function verifyFirebaseIdToken(
  token: string,
  fetchImpl: typeof fetch = fetch
): Promise<string | null> {
  const projectId = expectedProjectId()
  if (!projectId) return null

  // Read the header WITHOUT trusting it, only to pick the cert (`kid`) and to reject
  // any non-RS256 alg BEFORE touching a key. jwtVerify's `algorithms` re-checks this.
  let header: { alg?: string; kid?: string }
  try {
    header = decodeProtectedHeader(token)
  } catch {
    return null
  }
  if (header.alg !== 'RS256') return null
  const kid = header.kid
  if (typeof kid !== 'string' || !kid) return null

  const certs = await signingCerts(fetchImpl)
  if (!certs) return null
  const pem = certs[kid]
  if (!pem) return null

  try {
    const key = await importX509(pem, 'RS256')
    const { payload } = await jwtVerify(token, key, {
      algorithms: ['RS256'],
      issuer: `https://securetoken.google.com/${projectId}`,
      audience: projectId
    })
    return typeof payload.sub === 'string' && payload.sub ? payload.sub : null
  } catch {
    return null
  }
}

/** Test seam: drop the in-memory cert cache so each test starts clean. */
export function __resetFirebaseCertCacheForTests(): void {
  certCache = null
}
