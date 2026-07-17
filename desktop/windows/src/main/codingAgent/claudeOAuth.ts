// Claude Code sign-in — the Windows port of macOS's agent/src/oauth-flow.ts.
// Implements the PKCE + loopback login flow of the Claude Code CLI, so a
// fresh-install user can authenticate the built-in Claude Code agent from
// inside Omi (no CLI install, no manual `claude /login`).
//
// GROUND TRUTH (2026-07-17): every constant and parameter below was extracted
// from the bundled real CLI (claude.exe v2.1.205, `buildAuthUrl`/`startOAuthFlow`
// in the binary's embedded JS) and confirmed at runtime by running
// `claude.exe auth login` and capturing the URL it prints. The authorize
// request must match the CLI byte-for-byte: earlier variants that omitted
// `code=true` or requested a smaller scope set rendered the consent screen
// fine but died on Authorize with "Invalid request format" at code-issuance.
// Note the request/grant asymmetry: we REQUEST the CLI's 6-scope union
// (including `org:create_api_key`), and claude.ai GRANTS the 5 `user:*`
// scopes for subscription accounts — the granted set lands in `scopes`.
//
// This module is deliberately Electron-free (node builtins + global `fetch`
// only) so the URL builder/validator, token-exchange request shape, and the
// credentials-file merge logic are all unit-testable under node Vitest. The
// browser-open + IPC glue lives in ../ipc/codingAgent.ts.
//
// Credential storage: the @anthropic-ai/claude-agent-sdk (pinned in
// node_modules) reads `<CLAUDE_CONFIG_DIR or ~/.claude>/.credentials.json` with
// the shape `{ claudeAiOauth: { accessToken, refreshToken, expiresAt, scopes } }`
// (verified against sdk.mjs, and against the real file the CLI writes on
// Windows) and self-refreshes from the stored refresh token — Omi never
// refreshes. We write that file directly (the SDK-native path, same as the
// Claude Code CLI itself on Windows), and we MERGE so any other top-level keys
// (e.g. `mcpOAuth`) and extra `claudeAiOauth` subkeys the SDK maintains
// (`subscriptionType`, `rateLimitTier`, `refreshTokenExpiresAt`) survive a
// re-sign-in. `expiresAt` is stored as epoch milliseconds (a NUMBER), matching
// the real on-disk file.

import { createServer, type Server, type IncomingMessage, type ServerResponse } from 'http'
import { readFileSync, writeFileSync, mkdirSync } from 'fs'
import { randomBytes } from 'crypto'
import { homedir } from 'os'
import { join, dirname } from 'path'
import { generateVerifier, challengeFromVerifier, base64url } from '../integrations/oauthPkce'

// --- Constants (extracted from claude.exe v2.1.205 and runtime-verified) ---

const CLIENT_ID = '9d1c250a-e61b-44d9-88ed-5944d1962f5e'
// CLAUDE_AI_AUTHORIZE_URL in the CLI — the subscription (claude.ai) login lane.
// It 307s to claude.ai's authorize page with the query preserved; the CLI links
// users to this claude.com host, so we do too.
const AUTHORIZE_URL = 'https://claude.com/cai/oauth/authorize'
const TOKEN_URL = 'https://platform.claude.com/v1/oauth/token'
// CLAUDEAI_SUCCESS_URL — where the CLI redirects the loopback response.
const SUCCESS_URL = 'https://platform.claude.com/oauth/code/success?app=claude-code'
// The EXACT scope string the CLI requests for a default login: the deduped
// union of its console scopes [org:create_api_key, user:profile] and claude.ai
// scopes [user:profile, user:inference, user:sessions:claude_code,
// user:mcp_servers, user:file_upload]. Requesting a subset (just
// `user:inference`, or the 5 `user:*` scopes without `org:create_api_key`)
// renders consent but fails code-issuance with "Invalid request format".
const SCOPES =
  'org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload'
const CALLBACK_TIMEOUT_MS = 2 * 60 * 1000

// --- Credential file location + shape ---

/** The Claude config dir the SDK reads — `CLAUDE_CONFIG_DIR` or `~/.claude`. */
export function claudeConfigDir(env: NodeJS.ProcessEnv = process.env): string {
  return env.CLAUDE_CONFIG_DIR ?? join(homedir(), '.claude')
}

/** Absolute path to the credentials file the SDK reads/writes. */
export function claudeCredentialsPath(env: NodeJS.ProcessEnv = process.env): string {
  return join(claudeConfigDir(env), '.credentials.json')
}

export interface ClaudeAiOauth {
  accessToken: string
  refreshToken?: string | null
  /** Epoch milliseconds (number), matching the SDK-native on-disk format. */
  expiresAt?: number | null
  scopes: string[]
  // The SDK may add subscriptionType / rateLimitTier / refreshTokenExpiresAt;
  // we never drop them (merge preserves unknown keys).
  [extra: string]: unknown
}

/** Parse the whole credentials file (all top-level keys), or null if absent. */
function readCredentialsFile(env: NodeJS.ProcessEnv): Record<string, unknown> | null {
  try {
    const raw = readFileSync(claudeCredentialsPath(env), 'utf-8')
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : null
  } catch {
    // Missing file / unreadable / malformed — treat as no credentials.
    return null
  }
}

/** The stored `claudeAiOauth` block, or null when not signed in. */
export function readClaudeOauth(env: NodeJS.ProcessEnv = process.env): ClaudeAiOauth | null {
  const file = readCredentialsFile(env)
  const oauth = file?.claudeAiOauth
  if (!oauth || typeof oauth !== 'object') return null
  const o = oauth as ClaudeAiOauth
  return typeof o.accessToken === 'string' && o.accessToken ? o : null
}

export interface ClaudeAuthStatus {
  connected: boolean
  /** Epoch ms of access-token expiry, when known. */
  expiresAt: number | null
}

/**
 * Whether Claude Code has usable credentials. A stored refresh token counts as
 * connected even past the access token's expiry, because the SDK self-refreshes;
 * we only report disconnected when there is no access token, or the access token
 * is expired with no refresh token to renew it.
 */
export function claudeAuthStatus(env: NodeJS.ProcessEnv = process.env): ClaudeAuthStatus {
  const oauth = readClaudeOauth(env)
  if (!oauth) return { connected: false, expiresAt: null }
  const expiresAt = typeof oauth.expiresAt === 'number' ? oauth.expiresAt : null
  const hasRefresh = typeof oauth.refreshToken === 'string' && oauth.refreshToken.length > 0
  const unexpired = expiresAt === null || expiresAt > Date.now()
  return { connected: hasRefresh || unexpired, expiresAt }
}

/**
 * Persist a `claudeAiOauth` block, preserving every other top-level key and any
 * extra subkeys the SDK maintains. Never clobbers `mcpOAuth` or other content.
 */
export function writeClaudeCredentials(
  oauth: ClaudeAiOauth,
  env: NodeJS.ProcessEnv = process.env
): void {
  const existing = readCredentialsFile(env) ?? {}
  const priorOauth =
    existing.claudeAiOauth && typeof existing.claudeAiOauth === 'object'
      ? (existing.claudeAiOauth as Record<string, unknown>)
      : {}
  const merged = { ...existing, claudeAiOauth: { ...priorOauth, ...oauth } }
  const path = claudeCredentialsPath(env)
  mkdirSync(dirname(path), { recursive: true })
  writeFileSync(path, JSON.stringify(merged, null, 2), { mode: 0o600 })
}

/**
 * Sign out: drop only the `claudeAiOauth` key, preserving the rest of the file
 * (e.g. `mcpOAuth`). No-op when there is no credentials file.
 */
export function removeClaudeCredentials(env: NodeJS.ProcessEnv = process.env): void {
  const existing = readCredentialsFile(env)
  if (!existing || !('claudeAiOauth' in existing)) return
  const next = { ...existing }
  delete next.claudeAiOauth
  writeFileSync(claudeCredentialsPath(env), JSON.stringify(next, null, 2), { mode: 0o600 })
}

// --- Authorization URL (build + validate) ---

/**
 * Build the authorize URL for a PKCE loopback attempt — an exact replica of
 * the CLI's `buildAuthUrl` (same params, same order, same URLSearchParams
 * encoding: spaces as `+`, colons as `%3A`).
 */
export function buildClaudeAuthUrl(params: {
  redirectUri: string
  challenge: string
  state: string
}): string {
  const url = new URL(AUTHORIZE_URL)
  // `code=true` is appended UNCONDITIONALLY by the real CLI, for both the
  // loopback and manual flows (it makes the success page display the code as a
  // copy-paste fallback). Omitting it was one of the "Invalid request format"
  // divergences.
  url.searchParams.append('code', 'true')
  url.searchParams.append('client_id', CLIENT_ID)
  url.searchParams.append('response_type', 'code')
  url.searchParams.append('redirect_uri', params.redirectUri)
  url.searchParams.append('scope', SCOPES)
  url.searchParams.append('code_challenge', params.challenge)
  url.searchParams.append('code_challenge_method', 'S256')
  url.searchParams.append('state', params.state)
  return url.toString()
}

/**
 * Validate a Claude OAuth authorize URL before opening it in the browser —
 * port of macOS ChatProvider.validatedClaudeOAuthURL. Returns the parsed URL
 * when it is exactly a claude.com/cai PKCE request with a localhost loopback
 * redirect, else null. Guards against opening an attacker-substituted URL.
 */
export function validateClaudeOAuthUrl(urlString: string | null | undefined): URL | null {
  if (!urlString) return null
  let url: URL
  try {
    url = new URL(urlString)
  } catch {
    return null
  }
  if (
    url.protocol !== 'https:' ||
    url.hostname.toLowerCase() !== 'claude.com' ||
    url.port !== '' ||
    url.pathname !== '/cai/oauth/authorize' ||
    url.username !== '' ||
    url.password !== '' ||
    url.hash !== ''
  ) {
    return null
  }

  // Exactly one non-empty value for each required query param.
  const singleValue = (name: string): string | null => {
    const all = url.searchParams.getAll(name)
    if (all.length !== 1) return null
    const value = all[0]
    return value && value.length > 0 ? value : null
  }
  if (
    singleValue('code') !== 'true' ||
    singleValue('response_type') !== 'code' ||
    singleValue('client_id') === null ||
    singleValue('state') === null ||
    singleValue('code_challenge') === null ||
    singleValue('code_challenge_method') !== 'S256'
  ) {
    return null
  }
  const redirect = singleValue('redirect_uri')
  if (!redirect) return null
  let redirectUrl: URL
  try {
    redirectUrl = new URL(redirect)
  } catch {
    return null
  }
  if (
    redirectUrl.protocol !== 'http:' ||
    redirectUrl.hostname.toLowerCase() !== 'localhost' ||
    redirectUrl.port === '' ||
    redirectUrl.pathname !== '/callback'
  ) {
    return null
  }
  return url
}

/**
 * A fresh bridge/flow-issued authorize URL represents a new OAuth attempt (e.g.
 * after the bounded callback timeout), so the one-launch-per-attempt browser
 * latch may reset. Same URL = same in-flight flow = do not relaunch.
 * Port of macOS ChatProvider.isNewClaudeOAuthAttempt.
 */
export function isNewClaudeOAuthAttempt(
  previousAuthUrl: string | null | undefined,
  nextAuthUrl: string | null | undefined
): boolean {
  return previousAuthUrl !== nextAuthUrl
}

// --- Token exchange ---

export interface ClaudeOAuthResult {
  accessToken: string
  refreshToken?: string | null
  /** Epoch milliseconds, when the token response carried an expiry. */
  expiresAt: number | null
  scopes: string[]
}

interface RawTokenResponse {
  access_token: string
  refresh_token?: string
  expires_in?: number
  scope?: string
}

/**
 * Exchange an authorization code for tokens at the Claude token endpoint. Body
 * shape matches the CLI's `exchangeCodeForTokens` exactly: a JSON body of
 * `{grant_type, code, redirect_uri, client_id, code_verifier, state}` — no
 * `expires_in` (the CLI only adds it for `setup-token` long-lived tokens; the
 * normal login omits it and the server picks the expiry). Uses global `fetch`
 * so it can be tested against a local mock.
 */
export async function exchangeClaudeCodeForToken(
  code: string,
  codeVerifier: string,
  state: string,
  redirectUri: string,
  tokenUrl: string = TOKEN_URL
): Promise<ClaudeOAuthResult> {
  const jsonBody = JSON.stringify({
    grant_type: 'authorization_code',
    code,
    redirect_uri: redirectUri,
    client_id: CLIENT_ID,
    code_verifier: codeVerifier,
    state
  })
  console.error(`[claudeOAuth][diag] POST ${tokenUrl} (json) code.len=${code.length}`)
  const res = await fetch(tokenUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: jsonBody
  })
  const respText = await res.text()
  // Diag keeps status + body head on failure; success bodies (tokens) are
  // never logged.
  console.error(
    `[claudeOAuth][diag] token response status=${res.status}${res.ok ? '' : ` body=${respText.slice(0, 600)}`}`
  )
  if (res.status === 401) {
    throw new Error('Authentication failed: invalid authorization code')
  }
  if (!res.ok) {
    throw new Error(`Token exchange failed (${res.status}): ${respText}`)
  }
  const data = JSON.parse(respText) as RawTokenResponse
  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
    expiresAt: typeof data.expires_in === 'number' ? Date.now() + data.expires_in * 1000 : null,
    scopes: (data.scope || SCOPES).split(' ')
  }
}

// --- Loopback flow ---

export interface ClaudeOAuthFlowHandle {
  /** URL to validate + open in the browser. */
  authUrl: string
  /** Resolves once the callback is received, code exchanged, and creds written. */
  complete: Promise<ClaudeOAuthResult>
  /** Cancel: close the callback server and reject `complete`. */
  cancel: () => void
}

function startCallbackServer(): Promise<{ server: Server; port: number }> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    // The CLI binds 127.0.0.1 while advertising `localhost` in redirect_uri;
    // match it (proven working on Windows by the real CLI).
    server.listen(0, '127.0.0.1', () => {
      const addr = server.address()
      if (!addr || typeof addr === 'string') {
        reject(new Error('Failed to get callback server address'))
        return
      }
      resolve({ server, port: addr.port })
    })
  })
}

interface CallbackHit {
  code: string
  /** Finish the browser's pending request: redirect to the success page (CLI behavior). */
  respondSuccess: () => void
  /** Finish the browser's pending request with a plain failure message. */
  respondFailure: () => void
}

function waitForCallback(
  server: Server,
  expectedState: string,
  logErr: (msg: string) => void
): Promise<CallbackHit> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      reject(new Error('Claude sign-in timed out (2 minutes). Try again.'))
      server.close()
    }, CALLBACK_TIMEOUT_MS)

    server.on('request', (req: IncomingMessage, res: ServerResponse) => {
      const parsed = new URL(req.url || '', 'http://localhost')
      if (parsed.pathname !== '/callback') {
        res.writeHead(404)
        res.end('Not Found')
        return
      }
      const code = parsed.searchParams.get('code')
      const state = parsed.searchParams.get('state')
      if (!code) {
        res.writeHead(400)
        res.end('Authorization code not found')
        clearTimeout(timeout)
        reject(new Error('No authorization code received'))
        return
      }
      if (state !== expectedState) {
        res.writeHead(400)
        res.end('Invalid state parameter')
        clearTimeout(timeout)
        reject(new Error('OAuth state mismatch'))
        return
      }
      logErr('Claude OAuth callback received with valid code')
      clearTimeout(timeout)
      // Hold the response pending (as the CLI does) so the browser only lands
      // on the success page after the token exchange actually succeeded.
      resolve({
        code,
        respondSuccess: () => {
          res.writeHead(302, { Location: SUCCESS_URL })
          res.end()
        },
        respondFailure: () => {
          res.writeHead(500)
          res.end('Sign-in failed. Return to Omi and try again.')
        }
      })
    })
  })
}

/**
 * Start the loopback OAuth flow. Returns the authorize URL for the caller to
 * validate + open, and a promise that resolves after the callback lands, the
 * code is exchanged, and credentials are written. The caller opens the browser
 * (mirrors macOS: the bridge builds the URL, the UI opens it).
 */
export async function startClaudeOAuthFlow(
  logErr: (msg: string) => void,
  env: NodeJS.ProcessEnv = process.env,
  tokenUrl: string = TOKEN_URL
): Promise<ClaudeOAuthFlowHandle> {
  const codeVerifier = generateVerifier()
  const codeChallenge = challengeFromVerifier(codeVerifier)
  // 32-byte state, matching the CLI's generator (same size as the verifier).
  const state = base64url(randomBytes(32))

  const { server, port } = await startCallbackServer()
  logErr(`Claude OAuth callback server listening on port ${port}`)
  const redirectUri = `http://localhost:${port}/callback`
  const authUrl = buildClaudeAuthUrl({ redirectUri, challenge: codeChallenge, state })
  logErr(`[diag] authorize scopes="${SCOPES}" url=${authUrl}`)

  let cancelled = false
  let cancelReject: ((err: Error) => void) | null = null

  const complete = new Promise<ClaudeOAuthResult>((resolve, reject) => {
    cancelReject = reject
    waitForCallback(server, state, logErr)
      .then(async (hit) => {
        if (cancelled) return
        logErr(`[diag] callback code received len=${hit.code.length}`)
        logErr('Exchanging Claude authorization code for tokens...')
        try {
          const tokens = await exchangeClaudeCodeForToken(
            hit.code,
            codeVerifier,
            state,
            redirectUri,
            tokenUrl
          )
          writeClaudeCredentials(
            {
              accessToken: tokens.accessToken,
              refreshToken: tokens.refreshToken ?? null,
              expiresAt: tokens.expiresAt,
              scopes: tokens.scopes
            },
            env
          )
          logErr('Claude credentials written')
          hit.respondSuccess()
          resolve(tokens)
        } catch (err) {
          hit.respondFailure()
          throw err
        }
      })
      .catch((err) => {
        if (!cancelled) reject(err)
      })
      .finally(() => {
        server.close()
      })
  })

  return {
    authUrl,
    complete,
    cancel: () => {
      cancelled = true
      server.close()
      cancelReject?.(new Error('Claude sign-in cancelled'))
    }
  }
}
