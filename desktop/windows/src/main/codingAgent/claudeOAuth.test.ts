import { describe, it, expect, afterEach } from 'vitest'
import { createServer, type Server } from 'http'
import { mkdtempSync, rmSync, readFileSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { once } from 'events'
import {
  buildClaudeAuthUrl,
  validateClaudeOAuthUrl,
  isNewClaudeOAuthAttempt,
  exchangeClaudeCodeForToken,
  startClaudeOAuthFlow,
  writeClaudeCredentials,
  removeClaudeCredentials,
  readClaudeOauth,
  claudeAuthStatus,
  claudeCredentialsPath
} from './claudeOAuth'

const tempDirs: string[] = []
function tempConfigEnv(): NodeJS.ProcessEnv {
  const dir = mkdtempSync(join(tmpdir(), 'omi-claude-oauth-'))
  tempDirs.push(dir)
  return { CLAUDE_CONFIG_DIR: dir } as NodeJS.ProcessEnv
}

afterEach(() => {
  while (tempDirs.length) rmSync(tempDirs.pop()!, { recursive: true, force: true })
})

// A valid loopback authorize URL, matching what buildClaudeAuthUrl emits.
const VALID_URL =
  'https://claude.com/cai/oauth/authorize?code=true&client_id=test-client&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&scope=user%3Ainference&code_challenge=test-challenge&code_challenge_method=S256&state=test-state'

describe('buildClaudeAuthUrl', () => {
  // GROUND-TRUTH REGRESSION: the real claude.exe v2.1.205 prints this exact
  // URL shape from `claude auth login` (captured 2026-07-17; the loopback
  // variant differs from the printed manual variant only in redirect_uri).
  // Drift from the CLI's byte encoding is what caused "Invalid request format"
  // at code-issuance, so this asserts the FULL serialized URL, not just params.
  it('byte-matches the captured real-CLI authorize URL (loopback variant)', () => {
    const url = buildClaudeAuthUrl({
      redirectUri: 'http://localhost:51000/callback',
      challenge: 'CHAL',
      state: 'STATE'
    })
    expect(url).toBe(
      'https://claude.com/cai/oauth/authorize' +
        '?code=true' +
        '&client_id=9d1c250a-e61b-44d9-88ed-5944d1962f5e' +
        '&response_type=code' +
        '&redirect_uri=http%3A%2F%2Flocalhost%3A51000%2Fcallback' +
        '&scope=org%3Acreate_api_key+user%3Aprofile+user%3Ainference+user%3Asessions%3Aclaude_code+user%3Amcp_servers+user%3Afile_upload' +
        '&code_challenge=CHAL' +
        '&code_challenge_method=S256' +
        '&state=STATE'
    )
    // Round-trips through the validator.
    expect(validateClaudeOAuthUrl(url)).not.toBeNull()
  })

  it('requests the 6-scope union including org:create_api_key (request ≠ grant)', () => {
    const u = new URL(
      buildClaudeAuthUrl({
        redirectUri: 'http://localhost:51000/callback',
        challenge: 'c',
        state: 's'
      })
    )
    expect(u.searchParams.get('scope')).toBe(
      'org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload'
    )
    expect(u.searchParams.get('code')).toBe('true')
  })
})

describe('validateClaudeOAuthUrl', () => {
  it('accepts the canonical claude.com/cai loopback authorize URL', () => {
    const url = validateClaudeOAuthUrl(VALID_URL)
    expect(url?.host).toBe('claude.com')
    expect(url?.pathname).toBe('/cai/oauth/authorize')
  })

  it('rejects unexpected hosts, paths, missing params, and non-loopback redirects', () => {
    const invalid = [
      null,
      undefined,
      'not a url',
      // wrong host
      'https://evil.example/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // legacy claude.ai host (no longer what we build)
      'https://claude.ai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // wrong path
      'https://claude.com/other?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // missing code=true (the CLI always sends it; we must too)
      'https://claude.com/cai/oauth/authorize?response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // missing code_challenge_method
      'https://claude.com/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c',
      // wrong code_challenge_method
      'https://claude.com/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=plain',
      // non-loopback redirect host
      'https://claude.com/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=https%3A%2F%2Fexample.com%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // http (not https) authorize
      'http://claude.com/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256',
      // explicit port on claude.com
      'https://claude.com:8443/cai/oauth/authorize?code=true&response_type=code&client_id=c&redirect_uri=http%3A%2F%2Flocalhost%3A43123%2Fcallback&state=s&code_challenge=c&code_challenge_method=S256'
    ]
    for (const u of invalid) {
      expect(validateClaudeOAuthUrl(u), `expected reject: ${u}`).toBeNull()
    }
  })
})

describe('isNewClaudeOAuthAttempt (one-launch latch reset)', () => {
  it('same URL is the same in-flight attempt; a different URL is a new attempt', () => {
    expect(
      isNewClaudeOAuthAttempt(
        'https://claude.com/cai/oauth/authorize?state=current',
        'https://claude.com/cai/oauth/authorize?state=current'
      )
    ).toBe(false)
    expect(
      isNewClaudeOAuthAttempt(
        'https://claude.com/cai/oauth/authorize?state=expired',
        'https://claude.com/cai/oauth/authorize?state=retry'
      )
    ).toBe(true)
  })
})

describe('credentials file (SDK-native shape, merge-preserving)', () => {
  it('writes the claudeAiOauth block with a numeric expiresAt', () => {
    const env = tempConfigEnv()
    writeClaudeCredentials(
      { accessToken: 'a1', refreshToken: 'r1', expiresAt: 123456, scopes: ['user:inference'] },
      env
    )
    const onDisk = JSON.parse(readFileSync(claudeCredentialsPath(env), 'utf-8'))
    expect(onDisk.claudeAiOauth.accessToken).toBe('a1')
    expect(typeof onDisk.claudeAiOauth.expiresAt).toBe('number')
    expect(onDisk.claudeAiOauth.expiresAt).toBe(123456)
    expect(readClaudeOauth(env)?.refreshToken).toBe('r1')
  })

  it('preserves other top-level keys and extra claudeAiOauth subkeys on re-write', () => {
    const env = tempConfigEnv()
    // Pre-seed a file the SDK/CLI might have written, with extra content.
    writeFileSync(
      claudeCredentialsPath(env),
      JSON.stringify({
        mcpOAuth: { some: 'server-token' },
        claudeAiOauth: {
          accessToken: 'old',
          refreshToken: 'oldR',
          expiresAt: 1,
          scopes: ['user:inference'],
          subscriptionType: 'pro',
          rateLimitTier: 'default'
        }
      })
    )
    writeClaudeCredentials(
      { accessToken: 'new', refreshToken: 'newR', expiresAt: 999, scopes: ['user:inference'] },
      env
    )
    const onDisk = JSON.parse(readFileSync(claudeCredentialsPath(env), 'utf-8'))
    // Untouched sibling key survives.
    expect(onDisk.mcpOAuth).toEqual({ some: 'server-token' })
    // New token fields applied.
    expect(onDisk.claudeAiOauth.accessToken).toBe('new')
    expect(onDisk.claudeAiOauth.expiresAt).toBe(999)
    // Extra SDK-maintained subkeys survive the merge.
    expect(onDisk.claudeAiOauth.subscriptionType).toBe('pro')
    expect(onDisk.claudeAiOauth.rateLimitTier).toBe('default')
  })

  it('sign-out drops only claudeAiOauth, keeping the rest of the file', () => {
    const env = tempConfigEnv()
    writeFileSync(
      claudeCredentialsPath(env),
      JSON.stringify({ mcpOAuth: { keep: 1 }, claudeAiOauth: { accessToken: 'x', scopes: [] } })
    )
    removeClaudeCredentials(env)
    const onDisk = JSON.parse(readFileSync(claudeCredentialsPath(env), 'utf-8'))
    expect(onDisk.mcpOAuth).toEqual({ keep: 1 })
    expect(onDisk.claudeAiOauth).toBeUndefined()
    expect(readClaudeOauth(env)).toBeNull()
  })
})

describe('claudeAuthStatus', () => {
  it('is disconnected on a fresh machine (no file)', () => {
    const env = tempConfigEnv()
    expect(claudeAuthStatus(env)).toEqual({ connected: false, expiresAt: null })
  })

  it('is connected with a refresh token even past access-token expiry (SDK self-refreshes)', () => {
    const env = tempConfigEnv()
    writeClaudeCredentials(
      { accessToken: 'a', refreshToken: 'r', expiresAt: Date.now() - 10_000, scopes: [] },
      env
    )
    expect(claudeAuthStatus(env).connected).toBe(true)
  })

  it('is disconnected when the access token is expired and there is no refresh token', () => {
    const env = tempConfigEnv()
    writeClaudeCredentials(
      { accessToken: 'a', refreshToken: null, expiresAt: Date.now() - 10_000, scopes: [] },
      env
    )
    expect(claudeAuthStatus(env).connected).toBe(false)
  })
})

describe('exchangeClaudeCodeForToken (request shape + response mapping)', () => {
  let server: Server | null = null
  afterEach(async () => {
    if (server) {
      server.close()
      await once(server, 'close').catch(() => {})
      server = null
    }
  })

  it('POSTs the CLI-exact JSON body (no expires_in) and maps the response to epoch-ms expiresAt', async () => {
    let seen: { headers: Record<string, unknown>; body: Record<string, unknown> } | null = null
    server = createServer((req, res) => {
      let raw = ''
      req.on('data', (c) => (raw += c))
      req.on('end', () => {
        seen = { headers: req.headers, body: JSON.parse(raw) }
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(
          JSON.stringify({
            access_token: 'AT',
            refresh_token: 'RT',
            expires_in: 3600,
            scope: 'user:inference'
          })
        )
      })
    })
    await new Promise<void>((r) => server!.listen(0, '127.0.0.1', r))
    const port = (server.address() as { port: number }).port
    const before = Date.now()

    const result = await exchangeClaudeCodeForToken(
      'the-code',
      'the-verifier',
      'the-state',
      'http://localhost:43123/callback',
      `http://127.0.0.1:${port}/token`
    )

    expect(seen).not.toBeNull()
    expect(seen!.headers['content-type']).toContain('application/json')
    // The CLI's exchangeCodeForTokens body, exactly — in particular NO
    // expires_in (that is a setup-token-only field).
    expect(seen!.body).toEqual({
      grant_type: 'authorization_code',
      code: 'the-code',
      redirect_uri: 'http://localhost:43123/callback',
      client_id: '9d1c250a-e61b-44d9-88ed-5944d1962f5e',
      code_verifier: 'the-verifier',
      state: 'the-state'
    })
    expect(result.accessToken).toBe('AT')
    expect(result.refreshToken).toBe('RT')
    expect(result.scopes).toEqual(['user:inference'])
    expect(typeof result.expiresAt).toBe('number')
    expect(result.expiresAt!).toBeGreaterThanOrEqual(before + 3600 * 1000)
  })

  it('throws on a non-2xx token response', async () => {
    server = createServer((_req, res) => {
      res.writeHead(400)
      res.end('invalid_grant')
    })
    await new Promise<void>((r) => server!.listen(0, '127.0.0.1', r))
    const port = (server.address() as { port: number }).port
    await expect(
      exchangeClaudeCodeForToken(
        'c',
        'v',
        's',
        'http://localhost:1/callback',
        `http://127.0.0.1:${port}/token`
      )
    ).rejects.toThrow(/Token exchange failed \(400\)/)
  })
})

describe('startClaudeOAuthFlow (full loopback round-trip against a mock token endpoint)', () => {
  let tokenServer: Server | null = null
  afterEach(async () => {
    if (tokenServer) {
      tokenServer.close()
      await once(tokenServer, 'close').catch(() => {})
      tokenServer = null
    }
  })

  it('receives the callback, exchanges the code, writes creds, then 302s to the success page', async () => {
    const env = tempConfigEnv()
    // Mock Anthropic token endpoint.
    let tokenBody: Record<string, unknown> | null = null
    tokenServer = createServer((req, res) => {
      let raw = ''
      req.on('data', (c) => (raw += c))
      req.on('end', () => {
        tokenBody = JSON.parse(raw)
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(
          JSON.stringify({
            access_token: 'AT-flow',
            refresh_token: 'RT-flow',
            expires_in: 3600,
            scope: 'user:profile user:inference'
          })
        )
      })
    })
    await new Promise<void>((r) => tokenServer!.listen(0, '127.0.0.1', r))
    const tokenPort = (tokenServer.address() as { port: number }).port

    const flow = await startClaudeOAuthFlow(() => {}, env, `http://127.0.0.1:${tokenPort}/token`)
    const authUrl = new URL(flow.authUrl)
    expect(validateClaudeOAuthUrl(flow.authUrl)).not.toBeNull()
    const redirectUri = new URL(authUrl.searchParams.get('redirect_uri')!)
    const state = authUrl.searchParams.get('state')!

    // Simulate the browser redirect from claude.ai to our loopback server.
    const cbRes = await fetch(
      `http://127.0.0.1:${redirectUri.port}/callback?code=test-code-123&state=${encodeURIComponent(state)}`,
      { redirect: 'manual' }
    )
    const tokens = await flow.complete

    // Browser response arrives only after the exchange: a 302 to the success page.
    expect(cbRes.status).toBe(302)
    expect(cbRes.headers.get('location')).toBe(
      'https://platform.claude.com/oauth/code/success?app=claude-code'
    )
    // Token exchange carried the callback's code + our state + loopback redirect.
    expect(tokenBody).toMatchObject({
      grant_type: 'authorization_code',
      code: 'test-code-123',
      state,
      redirect_uri: `http://localhost:${redirectUri.port}/callback`
    })
    // Credentials were written in the SDK-native shape (granted scopes stored).
    expect(tokens.accessToken).toBe('AT-flow')
    const onDisk = JSON.parse(readFileSync(claudeCredentialsPath(env), 'utf-8'))
    expect(onDisk.claudeAiOauth.accessToken).toBe('AT-flow')
    expect(onDisk.claudeAiOauth.scopes).toEqual(['user:profile', 'user:inference'])
  })

  it('rejects a callback with a mismatched state and fails the flow', async () => {
    const env = tempConfigEnv()
    const flow = await startClaudeOAuthFlow(() => {}, env, 'http://127.0.0.1:1/never')
    const redirectUri = new URL(new URL(flow.authUrl).searchParams.get('redirect_uri')!)
    // Attach the rejection handler BEFORE triggering the callback, so the
    // rejection is never momentarily unhandled.
    const completion = expect(flow.complete).rejects.toThrow(/state mismatch/)
    const cbRes = await fetch(`http://127.0.0.1:${redirectUri.port}/callback?code=x&state=WRONG`, {
      redirect: 'manual'
    })
    expect(cbRes.status).toBe(400)
    await completion
  })
})
