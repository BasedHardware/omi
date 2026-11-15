// Contract for the AI-profile cloud reader (service.ts). The backend owns the
// profile; this client must only GET it (cached for prompt consumers), POST
// refresh, PATCH a user edit with source=user_edit, and DELETE — never generate
// locally, never call /synthesize, never write a local history.
//
// Only electron's net.fetch is mocked; the real core/session (epoch, abort,
// sign-out reset, uid decode) runs, so the account-isolation claims are pinned
// against the real session module.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  netFetch: vi.fn<(url: string, init: RequestInit) => Promise<Response>>()
}))

vi.mock('electron', () => ({ net: { fetch: h.netFetch } }))

const API = 'https://api.example'

/** A JWT-shaped token whose payload carries `uid` (signature is never checked). */
function jwt(uid: string): string {
  const payload = Buffer.from(
    JSON.stringify({ user_id: uid, exp: Math.floor(Date.now() / 1000) + 3600 })
  ).toString('base64url')
  return `h.${payload}.s`
}

const session = (uid = 'user-a'): { apiBase: string; desktopApiBase: string; token: string } => ({
  apiBase: API,
  desktopApiBase: 'https://desktop.example',
  token: jwt(uid)
})

const wire = (text: string, extra: Record<string, unknown> = {}): Record<string, unknown> => ({
  profile_text: text,
  generated_at: '2026-11-15T10:00:00Z',
  data_sources_used: 12,
  source: 'backend',
  refreshed_at: '2026-11-15T10:00:00Z',
  ...extra
})

const json = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

const flush = async (): Promise<void> => {
  for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0))
}

type Service = typeof import('./service')
type Session = typeof import('../core/session')

// service.ts and core/session.ts hold module state, so each test gets fresh copies.
async function fresh(): Promise<{ svc: Service; core: Session }> {
  vi.resetModules()
  const core = await import('../core/session')
  const svc = await import('./service')
  return { svc, core }
}

function calls(): { url: string; method: string; body: unknown; auth: string | null }[] {
  return h.netFetch.mock.calls.map(([url, init]) => ({
    url,
    method: init.method ?? 'GET',
    body: init.body ? JSON.parse(init.body as string) : undefined,
    auth: new Headers(init.headers).get('Authorization')
  }))
}

beforeEach(() => {
  h.netFetch.mockReset()
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'log').mockImplementation(() => {})
})

afterEach(() => vi.restoreAllMocks())

describe('parseProfile', () => {
  it('maps the API shape, including the new source / refreshed_at fields', async () => {
    const { svc } = await fresh()
    expect(svc.parseProfile(wire('- Ada builds compilers', { source: 'user_edit' }))).toEqual({
      profileText: '- Ada builds compilers',
      generatedAt: Date.parse('2026-11-15T10:00:00Z'),
      dataSourcesUsed: 12,
      source: 'user_edit',
      refreshedAt: Date.parse('2026-11-15T10:00:00Z')
    })
  })

  it('treats null, a blank profile_text, and legacy rows without the new fields sanely', async () => {
    const { svc } = await fresh()
    expect(svc.parseProfile(null)).toBeNull()
    expect(svc.parseProfile({ profile_text: '   ' })).toBeNull()
    expect(svc.parseProfile({ profile_text: 'x', source: 'mystery' })).toEqual({
      profileText: 'x',
      generatedAt: null,
      dataSourcesUsed: 0,
      source: null,
      refreshedAt: null
    })
  })
})

describe('codeForStatus', () => {
  it('maps the refresh error statuses to distinct renderer codes', async () => {
    const { svc } = await fresh()
    expect(svc.codeForStatus(402)).toBe('usage_exhausted')
    expect(svc.codeForStatus(409)).toBe('in_progress')
    expect(svc.codeForStatus(422)).toBe('insufficient_data')
    expect(svc.codeForStatus(502)).toBe('synthesis_failed')
    expect(svc.codeForStatus(429)).toBe('rate_limited')
    expect(svc.codeForStatus(403)).toBe('auth_expired')
    expect(svc.codeForStatus(500)).toBe('unknown')
  })
})

describe('reading the profile', () => {
  it('without a session: no network, null text, not_signed_in', async () => {
    const { svc } = await fresh()
    expect(svc.getLatestProfileText()).toBeNull()
    expect(await svc.loadProfile()).toEqual({ ok: false, code: 'not_signed_in' })
    expect(h.netFetch).not.toHaveBeenCalled()
  })

  it('a session push warms the cache with one authed GET', async () => {
    h.netFetch.mockResolvedValue(json(wire('- Ada builds compilers')))
    const { svc } = await fresh()
    const s = session()
    svc.configureAiProfileSession(s)
    await flush()

    expect(calls()).toEqual([
      {
        url: `${API}/v1/users/ai-profile`,
        method: 'GET',
        body: undefined,
        auth: `Bearer ${s.token}`
      }
    ])
    expect(svc.getLatestProfileText()).toBe('- Ada builds compilers')
    // Fresh cache: reading again costs nothing.
    expect(h.netFetch).toHaveBeenCalledTimes(1)
  })

  it('GET null means no profile', async () => {
    h.netFetch.mockResolvedValue(json(null))
    const { svc } = await fresh()
    svc.configureAiProfileSession(session())
    expect(await svc.loadProfile()).toEqual({ ok: true, value: null })
    expect(svc.getLatestProfileText()).toBeNull()
  })

  it('a stale cache answers immediately and refetches in the background', async () => {
    h.netFetch.mockResolvedValueOnce(json(wire('old')))
    const { svc } = await fresh()
    svc.configureAiProfileSession(session())
    await flush()

    const realNow = Date.now()
    vi.spyOn(Date, 'now').mockReturnValue(realNow + svc.CACHE_TTL_MS + 1)
    h.netFetch.mockResolvedValueOnce(json(wire('new')))
    expect(svc.getLatestProfileText()).toBe('old')
    await flush()
    expect(h.netFetch).toHaveBeenCalledTimes(2)
    expect(svc.getLatestProfileText()).toBe('new')
  })

  it('a failed read keeps serving the last fetched profile', async () => {
    h.netFetch.mockResolvedValueOnce(json(wire('kept')))
    const { svc } = await fresh()
    svc.configureAiProfileSession(session())
    await flush()

    h.netFetch.mockResolvedValueOnce(json({ detail: 'boom' }, 503))
    const r = await svc.loadProfile()
    expect(r.ok && r.value?.profileText).toBe('kept')
  })

  it('concurrent reads share one request', async () => {
    h.netFetch.mockResolvedValue(json(wire('x')))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    await Promise.all([svc.loadProfile(), svc.loadProfile(), svc.loadProfile()])
    expect(h.netFetch).toHaveBeenCalledTimes(1)
  })
})

describe('account isolation', () => {
  it('sign-out drops the cached profile', async () => {
    h.netFetch.mockResolvedValue(json(wire('A secrets')))
    const { svc } = await fresh()
    svc.configureAiProfileSession(session('user-a'))
    await flush()
    expect(svc.getLatestProfileText()).toBe('A secrets')

    svc.configureAiProfileSession(null)
    expect(svc.getLatestProfileText()).toBeNull()
  })

  it("never serves user A's profile once user B's session is current", async () => {
    h.netFetch.mockResolvedValueOnce(json(wire('A secrets')))
    const { svc, core } = await fresh()
    svc.configureAiProfileSession(session('user-a'))
    await flush()

    // A direct switch (e.g. a pulled session for another account) with no
    // sign-out in between, and B's GET still pending.
    h.netFetch.mockImplementationOnce(() => new Promise<Response>(() => {}))
    core.setBackendSession(session('user-b'))
    expect(svc.getLatestProfileText()).toBeNull()
  })

  it('drops a read that lands after the account changed', async () => {
    let resolveA: (r: Response) => void = () => {}
    h.netFetch.mockImplementationOnce(() => new Promise<Response>((r) => (resolveA = r)))
    const { svc, core } = await fresh()
    core.setBackendSession(session('user-a'))
    const pending = svc.loadProfile()
    h.netFetch.mockImplementationOnce(() => new Promise<Response>(() => {}))
    core.setBackendSession(session('user-b'))
    resolveA(json(wire('A secrets')))
    await pending
    expect(svc.getLatestProfileText()).toBeNull()
  })
})

describe('refresh', () => {
  it('POSTs /refresh with no body and caches the result', async () => {
    h.netFetch.mockResolvedValue(json(wire('- regenerated')))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    const r = await svc.refreshProfile()

    expect(r.ok && r.value.profileText).toBe('- regenerated')
    expect(calls()).toEqual([
      expect.objectContaining({
        url: `${API}/v1/users/ai-profile/refresh`,
        method: 'POST',
        body: undefined
      })
    ])
    expect(svc.getLatestProfileText()).toBe('- regenerated')
  })

  it.each([
    [402, 'usage_exhausted'],
    [409, 'in_progress'],
    [422, 'insufficient_data'],
    [502, 'synthesis_failed']
  ] as const)('HTTP %i → %s', async (status, code) => {
    h.netFetch.mockResolvedValue(json({ detail: 'x' }, status))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    expect(await svc.refreshProfile()).toEqual({ ok: false, code })
  })

  it('a double click joins the running refresh instead of drawing a 409', async () => {
    h.netFetch.mockResolvedValue(json(wire('once')))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    await Promise.all([svc.refreshProfile(), svc.refreshProfile()])
    expect(h.netFetch).toHaveBeenCalledTimes(1)
  })

  it('never calls the legacy /synthesize endpoint', async () => {
    h.netFetch.mockResolvedValue(json(wire('x')))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    await svc.refreshProfile()
    await svc.loadProfile()
    expect(calls().some((c) => c.url.includes('synthesize'))).toBe(false)
  })
})

describe('edit and delete', () => {
  it('PATCHes the text with source=user_edit and caches the saved profile', async () => {
    h.netFetch.mockResolvedValue(json(wire('edited', { source: 'user_edit' })))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    const r = await svc.editProfile('edited')

    expect(r.ok && r.value.source).toBe('user_edit')
    expect(calls()).toEqual([
      expect.objectContaining({
        url: `${API}/v1/users/ai-profile`,
        method: 'PATCH',
        body: { profile_text: 'edited', source: 'user_edit' }
      })
    ])
    expect(svc.getLatestProfileText()).toBe('edited')
  })

  it('DELETE clears the cached profile', async () => {
    h.netFetch.mockResolvedValueOnce(json(wire('to delete')))
    const { svc } = await fresh()
    svc.configureAiProfileSession(session())
    await flush()

    h.netFetch.mockResolvedValueOnce(new Response(null, { status: 204 }))
    expect(await svc.deleteProfile()).toEqual({ ok: true, value: null })
    expect(calls()[1]).toEqual(
      expect.objectContaining({ url: `${API}/v1/users/ai-profile`, method: 'DELETE' })
    )
    expect(svc.getLatestProfileText()).toBeNull()
  })

  it('a network failure is reported as network, not as a raw message', async () => {
    h.netFetch.mockRejectedValue(new TypeError('fetch failed: secret body'))
    const { svc, core } = await fresh()
    core.setBackendSession(session())
    expect(await svc.editProfile('x')).toEqual({ ok: false, code: 'network' })
  })
})
