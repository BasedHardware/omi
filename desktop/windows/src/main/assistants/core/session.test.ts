// Pull-based token freshness (the Windows main-process fix): the renderer relays a
// Firebase token, but a throttled hidden window can stop re-pushing, leaving main's
// cached token expired and every REST call 401ing. These tests pin the pull layer:
// exp-decode, pre-emptive refresh, 401 → pull + retry-once, coalescing, and the
// CRUX — a same-user refresh must PRESERVE the epoch (so the retry isn't doomed),
// while an account switch must MOVE it (so the caller's guard drops the result).
import { beforeEach, describe, expect, it, vi } from 'vitest'

const BASES = { apiBase: 'https://api.example', desktopApiBase: 'https://desktop.example' }

const nowSec = (): number => Math.floor(Date.now() / 1000)

/** A Firebase-ish JWT: only the payload segment matters (decoded, never verified). */
function makeToken(claims: Record<string, unknown>): string {
  return `h.${Buffer.from(JSON.stringify(claims)).toString('base64')}.s`
}

const sess = (token: string): { apiBase: string; desktopApiBase: string; token: string } => ({
  ...BASES,
  token
})

// user u1, valid for an hour; a nonce so two "fresh" tokens differ (retry needs a
// token distinct from the one that just 401'd).
const freshU1 = (n = 0): string => makeToken({ user_id: 'u1', exp: nowSec() + 3600, n })
const staleU1 = (): string => makeToken({ user_id: 'u1', exp: nowSec() - 10 })
const freshU2 = (): string => makeToken({ user_id: 'u2', exp: nowSec() + 3600 })

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

/** Module state (cached, epoch, refresher, in-flight pull) is module-scoped, so
 *  every test gets a fresh instance. */
async function freshSession(): Promise<typeof import('./session')> {
  vi.resetModules()
  return import('./session')
}

function resp(status: number): Response {
  return { status, ok: status >= 200 && status < 300 } as unknown as Response
}

beforeEach(() => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

describe('isSessionExpired', () => {
  it('is false with no session', async () => {
    const s = await freshSession()
    expect(s.isSessionExpired()).toBe(false)
  })

  it('is false for a token valid past the skew window', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1()))
    expect(s.isSessionExpired()).toBe(false)
  })

  it('is true for an already-expired token', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(staleU1()))
    expect(s.isSessionExpired()).toBe(true)
  })

  it('is true within the 30s skew before exp', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(makeToken({ user_id: 'u1', exp: nowSec() + 10 })))
    expect(s.isSessionExpired()).toBe(true)
  })

  it('is false for a token whose exp is undecodable (defers to the 401 path)', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(makeToken({ user_id: 'u1' }))) // no exp claim
    expect(s.isSessionExpired()).toBe(false)
  })
})

describe('fetchWithFreshToken', () => {
  it('pre-emptively pulls a fresh token before a request when the cached one is expired', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(staleU1()))
    const refreshed = freshU1(1)
    const refresher = vi.fn(async () => sess(refreshed))
    s.setTokenRefresher(refresher)

    const seen: string[] = []
    const res = await s.fetchWithFreshToken(async (session) => {
      seen.push(session.token)
      return resp(200)
    })

    expect(res.status).toBe(200)
    expect(refresher).toHaveBeenCalledTimes(1)
    // The request used the freshly pulled token, not the expired cached one.
    expect(seen).toEqual([refreshed])
  })

  it('on 401 pulls a fresh token and retries ONCE, preserving the epoch (same user)', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    const epochBefore = s.getSessionEpoch()
    const refreshed = freshU1(1)
    s.setTokenRefresher(async () => sess(refreshed))

    const seen: string[] = []
    const doFetch = vi.fn(async (session: { token: string }) => {
      seen.push(session.token)
      return resp(seen.length === 1 ? 401 : 200)
    })
    const res = await s.fetchWithFreshToken(doFetch)

    expect(doFetch).toHaveBeenCalledTimes(2)
    expect(res.status).toBe(200)
    expect(seen[1]).toBe(refreshed) // retry used the pulled token
    // CRUX: a same-user refresh must NOT bump the epoch, else the caller's own
    // epoch guard would discard the very result the retry just recovered.
    expect(s.getSessionEpoch()).toBe(epochBefore)
  })

  it('surfaces a persistent 401 (retries at most once — never a hot loop)', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    s.setTokenRefresher(async () => sess(freshU1(1)))

    const doFetch = vi.fn(async () => resp(401))
    const res = await s.fetchWithFreshToken(doFetch)

    expect(doFetch).toHaveBeenCalledTimes(2) // original + one retry, then give up
    expect(res.status).toBe(401)
  })

  it('does NOT retry when the pull was an account switch (epoch moved → result dropped)', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    const epochBefore = s.getSessionEpoch()
    s.setTokenRefresher(async () => sess(freshU2())) // different uid

    const doFetch = vi.fn(async () => resp(401))
    const res = await s.fetchWithFreshToken(doFetch)

    expect(doFetch).toHaveBeenCalledTimes(1) // no retry across an account switch
    expect(res.status).toBe(401)
    expect(s.getSessionEpoch()).toBeGreaterThan(epochBefore) // switch bumped the epoch
  })

  it('does NOT retry when the pulled token has an undecodable uid (treated as not-same-user)', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    const epochBefore = s.getSessionEpoch()
    // Token whose payload carries no user_id/sub → tokenUid() is null. A null uid
    // must NOT `null === null`-match the cached uid and swap in place; it is routed
    // through setBackendSession (epoch bumps), so the retry is skipped.
    s.setTokenRefresher(async () => sess(makeToken({ exp: nowSec() + 3600 })))

    const doFetch = vi.fn(async () => resp(401))
    const res = await s.fetchWithFreshToken(doFetch)

    expect(doFetch).toHaveBeenCalledTimes(1) // no retry — undecodable uid is not-same-user
    expect(res.status).toBe(401)
    expect(s.getSessionEpoch()).toBeGreaterThan(epochBefore)
  })

  it('returns the 401 unchanged when no refresher is wired', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    // no setTokenRefresher

    const doFetch = vi.fn(async () => resp(401))
    const res = await s.fetchWithFreshToken(doFetch)

    expect(doFetch).toHaveBeenCalledTimes(1)
    expect(res.status).toBe(401)
  })
})

describe('pullFreshSession coalescing', () => {
  it('collapses concurrent pulls onto a single renderer round-trip', async () => {
    const s = await freshSession()
    s.setBackendSession(sess(freshU1(0)))
    let resolve!: (v: { apiBase: string; desktopApiBase: string; token: string }) => void
    const refresher = vi.fn(
      () =>
        new Promise<{ apiBase: string; desktopApiBase: string; token: string }>(
          (r) => (resolve = r)
        )
    )
    s.setTokenRefresher(refresher)

    const a = s.pullFreshSession()
    const b = s.pullFreshSession()
    const c = s.pullFreshSession()
    await flush()
    resolve(sess(freshU1(1)))
    await Promise.all([a, b, c])

    expect(refresher).toHaveBeenCalledTimes(1)
  })
})
