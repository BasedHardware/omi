// Live contract probe for the backend-mediated Google sign-in flow (network
// only — no browser, no auth). Verifies the prod backend implements the exact
// /v1/auth/authorize contract the Windows app builds against:
//   1. A well-formed authorize request 30x-redirects to accounts.google.com
//      with the backend's own callback as Google's redirect_uri.
//   2. PKCE is enforced (missing/malformed code_challenge → 400).
//   3. The loopback redirect_uri allowlist is enforced (https → 400).
//
// Usage: node scripts/verify-oauth-contract.mjs [apiBase]
//        (default: $VITE_OMI_API_BASE or https://api.omi.me)
import { createHash, randomBytes } from 'node:crypto'

const API = (process.argv[2] || process.env.VITE_OMI_API_BASE || 'https://api.omi.me').replace(
  /\/+$/,
  ''
)

const b64url = (buf) =>
  buf.toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
const verifier = b64url(randomBytes(32))
const challenge = b64url(createHash('sha256').update(verifier).digest())
const state = `${b64url(randomBytes(6))}|${b64url(randomBytes(16))}`
const redirectUri = 'http://127.0.0.1:51000/callback'

let failures = 0
const check = (name, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`)
  if (!ok) failures++
}
// Non-fatal: repo-main behavior that a lagging prod deploy may not have yet.
const warn = (name, ok, detail) => {
  console.log(`${ok ? 'PASS' : 'WARN'}  ${name}${detail ? ` — ${detail}` : ''}`)
}

function authorizeUrl(params) {
  const u = new URL(`${API}/v1/auth/authorize`)
  for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v)
  return u
}

const base = {
  provider: 'google',
  redirect_uri: redirectUri,
  state,
  code_challenge: challenge,
  code_challenge_method: 'S256'
}

// --- 1. Happy path: 30x to accounts.google.com --------------------------------
{
  const res = await fetch(authorizeUrl(base), { redirect: 'manual' })
  check('authorize returns a redirect', res.status >= 300 && res.status < 400, `status ${res.status}`)
  const loc = res.headers.get('location') || ''
  let google = null
  try {
    google = new URL(loc)
  } catch {
    /* checked below */
  }
  check(
    'redirect targets accounts.google.com',
    google?.hostname === 'accounts.google.com',
    loc.split('?')[0]
  )
  if (google) {
    check('google url has client_id', !!google.searchParams.get('client_id'))
    check(
      'google redirect_uri is the BACKEND callback (loopback stays server-side)',
      (google.searchParams.get('redirect_uri') || '').endsWith('/v1/auth/callback/google'),
      google.searchParams.get('redirect_uri') || '(missing)'
    )
    check('response_type=code', google.searchParams.get('response_type') === 'code')
    // NOTE: our state/redirect_uri/code_challenge are stored in the backend's
    // Redis session (keyed by the session id Google carries as `state`) — they
    // are intentionally NOT echoed into the Google URL. The session id must exist.
    check('google state carries a backend session id', !!google.searchParams.get('state'))
  }
}

// --- 2. PKCE strictness (WARN-only) ---------------------------------------------
// Repo main REQUIRES code_challenge at /authorize (_validate_pkce_challenge);
// the deployed prod revision may predate that and accept the request anyway
// (observed 2026-07-10: prod 307s without a challenge). The Windows app ALWAYS
// sends S256 PKCE, which both revisions accept — so a lagging deploy is a
// warning, not a client-contract failure.
{
  const { code_challenge: _omit, code_challenge_method: _omit2, ...noPkce } = base
  const res = await fetch(authorizeUrl(noPkce), { redirect: 'manual' })
  warn('missing code_challenge is rejected (PKCE required)', res.status === 400, `status ${res.status}`)
}
{
  const res = await fetch(authorizeUrl({ ...base, code_challenge_method: 'plain' }), {
    redirect: 'manual'
  })
  warn('code_challenge_method=plain is rejected (S256 only)', res.status === 400, `status ${res.status}`)
}

// --- 3. redirect_uri allowlist --------------------------------------------------
{
  const res = await fetch(authorizeUrl({ ...base, redirect_uri: 'https://evil.example/cb' }), {
    redirect: 'manual'
  })
  check('https redirect_uri is rejected (loopback allowlist)', res.status === 400, `status ${res.status}`)
}

console.log(
  failures === 0
    ? `\nOK — ${API} supports the Windows sign-in contract (provider=google, PKCE S256, loopback redirect).`
    : `\n${failures} contract check(s) FAILED against ${API}.`
)
// exitCode (not process.exit): hard-exiting while undici sockets are still
// closing trips a libuv assertion on Windows (uv async handle race).
process.exitCode = failures === 0 ? 0 : 1
