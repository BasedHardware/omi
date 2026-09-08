// Session/scheduling contract for service.ts — the wiring that decides WHEN a
// profile gets generated, and which session it is allowed to write for.
// (The generate flow itself is covered by service.test.ts against the real
// orchestrator core.)
//
// The renderer relays a Firebase session on sign-in and on every id-token
// refresh (~hourly). Pushing a session must re-run the due-check — that closes
// the startup race, where maybeGenerateOnStartup() runs before the user has
// signed in, defers, and nothing re-checks for up to 6h. But it must NOT
// generate on every push.
//
// NOTE: `./synthesis` is deliberately NOT mocked — these tests compose the REAL
// shouldGenerate (and its real 24h GENERATION_INTERVAL_MS) with the real trigger
// path, so the "hourly refresh stays ≤1 generation/day" claim is actually pinned
// rather than asserted against a stubbed constant. Only the impure edges
// (better-sqlite3 via ipc/db, the LLM/HTTP orchestrator, settings) are mocked, so
// this runs hermetically under plain-node vitest.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { OrchestratorDeps } from './orchestrate'

const h = vi.hoisted(() => ({
  getAppSettings: vi.fn(() => ({ aiProfileEnabled: true })),
  latestAiUserProfile: vi.fn((): { id: number; generatedAt: number } | undefined => undefined),
  listAiUserProfiles: vi.fn(() => [] as { id: number; profileText: string; generatedAt: number }[]),
  generateProfile: vi.fn(async (_deps: OrchestratorDeps) => ({
    id: 1,
    profileText: '- fact',
    generatedAt: 0
  })),
  // Never settles — a source fetch stays in flight so a sign-out can abort it.
  netFetch: vi.fn((_url: string, _init: { signal: AbortSignal }) => new Promise<Response>(() => {}))
}))

vi.mock('electron', () => ({ net: { fetch: h.netFetch } }))
vi.mock('../../appSettings', () => ({ getAppSettings: h.getAppSettings }))
vi.mock('../../ipc/db', () => ({
  latestAiUserProfile: h.latestAiUserProfile,
  listAiUserProfiles: h.listAiUserProfiles,
  insertAiUserProfile: vi.fn(() => 1),
  markAiUserProfileSynced: vi.fn(),
  updateAiUserProfileText: vi.fn(),
  deleteAiUserProfile: vi.fn(),
  deleteAllAiUserProfiles: vi.fn()
}))
vi.mock('./orchestrate', async (importOriginal) => {
  // Keep the REAL error classes (service.ts imports them) — swap only the flow.
  const actual = await importOriginal<typeof import('./orchestrate')>()
  return { ...actual, generateProfile: h.generateProfile }
})

const SESSION = {
  apiBase: 'https://api.example',
  desktopApiBase: 'https://desktop.example',
  token: 'tok-abc'
}

const HOUR = 60 * 60 * 1000
const NOW = 1_700_000_000_000

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

// service.ts holds module-scoped state (cachedSession, sessionEpoch, isGenerating,
// lastAttemptAt), so each test gets a fresh instance.
async function freshService(): Promise<typeof import('./service')> {
  vi.resetModules()
  return import('./service')
}

beforeEach(() => {
  vi.clearAllMocks()
  h.getAppSettings.mockReturnValue({ aiProfileEnabled: true })
  h.latestAiUserProfile.mockReturnValue(undefined) // no profile yet → always due
  h.generateProfile.mockResolvedValue({ id: 1, profileText: '- fact', generatedAt: 0 })
  vi.spyOn(Date, 'now').mockReturnValue(NOW)
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

afterEach(() => vi.restoreAllMocks())

describe('configureAiProfileSession', () => {
  it('runs the due-check on a non-null session, generating when due (closes the startup race)', async () => {
    const { configureAiProfileSession } = await freshService()

    configureAiProfileSession(SESSION)
    await flush()

    expect(h.generateProfile).toHaveBeenCalledTimes(1)
  })

  it('does not generate on a null (sign-out) session, and clears the cached one', async () => {
    const { configureAiProfileSession, generateNow } = await freshService()

    configureAiProfileSession(null)
    await flush()

    expect(h.generateProfile).not.toHaveBeenCalled()
    // The session really was cleared: a generate with no session now throws
    // rather than reusing the signed-out user's token.
    await expect(generateNow()).rejects.toThrow(/no backend session/)
  })

  it('does not generate when the aiProfileEnabled setting is off', async () => {
    const { configureAiProfileSession } = await freshService()
    h.getAppSettings.mockReturnValue({ aiProfileEnabled: false })

    configureAiProfileSession(SESSION)
    await flush()

    expect(h.generateProfile).not.toHaveBeenCalled()
  })
})

// M2: the headline cadence claim, composed against the REAL shouldGenerate.
describe('cadence (real synthesis.shouldGenerate)', () => {
  it('does NOT generate when the stored profile is 1h old', async () => {
    const { configureAiProfileSession } = await freshService()
    h.latestAiUserProfile.mockReturnValue({ id: 1, generatedAt: NOW - HOUR })

    configureAiProfileSession(SESSION)
    await flush()

    expect(h.generateProfile).not.toHaveBeenCalled()
  })

  it('DOES generate when the stored profile is 25h old', async () => {
    const { configureAiProfileSession } = await freshService()
    h.latestAiUserProfile.mockReturnValue({ id: 1, generatedAt: NOW - 25 * HOUR })

    configureAiProfileSession(SESSION)
    await flush()

    expect(h.generateProfile).toHaveBeenCalledTimes(1)
  })

  it('a full day of hourly token refreshes against a fresh profile yields ZERO generations', async () => {
    const { configureAiProfileSession } = await freshService()
    const generatedAt = NOW
    h.latestAiUserProfile.mockReturnValue({ id: 1, generatedAt })

    // 24 hourly id-token refreshes, each relaying a session.
    for (let i = 0; i < 24; i++) {
      vi.spyOn(Date, 'now').mockReturnValue(generatedAt + i * HOUR)
      configureAiProfileSession(SESSION)
      await flush()
    }

    // Every push re-checked; none was >24h past the stored profile.
    expect(h.generateProfile).not.toHaveBeenCalled()
  })
})

// M1: `generatedAt` only advances on SUCCESS, so a failing run stays "due".
// Without an attempt floor, the hourly session push would retry it ~24x/day.
describe('attempt floor (failure backoff)', () => {
  it('does not retry a FAILED generation on the next hourly push (≤4 attempts/day)', async () => {
    const { configureAiProfileSession } = await freshService()
    h.generateProfile.mockRejectedValue(new Error('backend down'))

    configureAiProfileSession(SESSION) // attempt #1 — fails
    await flush()
    expect(h.generateProfile).toHaveBeenCalledTimes(1)

    // Five hourly refreshes over the next 5h. Still "due" (nothing was stored),
    // but the attempt floor must hold them all off.
    for (let i = 1; i <= 5; i++) {
      vi.spyOn(Date, 'now').mockReturnValue(NOW + i * HOUR)
      configureAiProfileSession(SESSION)
      await flush()
    }
    expect(h.generateProfile).toHaveBeenCalledTimes(1)

    // Past the 6h floor, it retries.
    vi.spyOn(Date, 'now').mockReturnValue(NOW + 6 * HOUR + 1)
    configureAiProfileSession(SESSION)
    await flush()
    expect(h.generateProfile).toHaveBeenCalledTimes(2)
  })

  it('a deferred push (no session cached yet) does not consume an attempt', async () => {
    const { maybeGenerateOnStartup, configureAiProfileSession, stopAiProfileScheduler } =
      await freshService()

    // Startup with no session → soft no-op, must NOT burn the attempt budget.
    maybeGenerateOnStartup()
    stopAiProfileScheduler()
    expect(h.generateProfile).not.toHaveBeenCalled()

    // The renderer signs in moments later — this must generate immediately.
    configureAiProfileSession(SESSION)
    await flush()
    expect(h.generateProfile).toHaveBeenCalledTimes(1)
  })
})

describe('non-reentrancy guard', () => {
  it('a session push landing on an in-flight generation does not start a second one', async () => {
    const { configureAiProfileSession } = await freshService()
    let release!: () => void
    h.generateProfile.mockReturnValue(
      new Promise((resolve) => {
        release = (): void => resolve({ id: 1, profileText: '- fact', generatedAt: 0 })
      })
    )

    configureAiProfileSession(SESSION) // starts generation #1
    await flush()
    expect(h.generateProfile).toHaveBeenCalledTimes(1)

    // A token refresh (and a 6h timer tick) arriving mid-generation must no-op.
    configureAiProfileSession(SESSION)
    configureAiProfileSession(SESSION)
    await flush()
    expect(h.generateProfile).toHaveBeenCalledTimes(1)

    release()
    await flush()
  })
})

// C1: the epoch seam service.ts hands the orchestrator. (That the orchestrator
// HONOURS it — no insert, no sync — is pinned in service.test.ts.)
describe('session epoch (C1 staleness seam)', () => {
  /** The isStale predicate service.ts passed into the current generation. */
  function isStaleSeam(): () => boolean {
    const deps = h.generateProfile.mock.calls[0][0] as OrchestratorDeps
    return deps.isStale as () => boolean
  }

  it('reports stale once the user signs out mid-generation', async () => {
    const { configureAiProfileSession } = await freshService()
    h.generateProfile.mockReturnValue(new Promise(() => {})) // never settles

    configureAiProfileSession(SESSION)
    await flush()
    const isStale = isStaleSeam()

    expect(isStale()).toBe(false) // session still live

    configureAiProfileSession(null) // sign-out
    expect(isStale()).toBe(true) // → the run's writes are now blocked
  })

  it('reports stale when a DIFFERENT user signs in mid-generation', async () => {
    const { configureAiProfileSession } = await freshService()
    h.generateProfile.mockReturnValue(new Promise(() => {}))

    configureAiProfileSession(SESSION)
    await flush()
    const isStale = isStaleSeam()

    configureAiProfileSession({ ...SESSION, token: 'tok-user-B' })
    expect(isStale()).toBe(true)
  })

  it('is not stale while the same session stays current', async () => {
    const { configureAiProfileSession } = await freshService()
    h.generateProfile.mockReturnValue(new Promise(() => {}))

    configureAiProfileSession(SESSION)
    await flush()

    expect(isStaleSeam()()).toBe(false)
  })

  // The epoch guard blocks the WRITES; this abort makes the in-flight HTTP/LLM
  // work actually die on sign-out instead of running to completion for 10–90s
  // with the signed-out user's bearer token still attached.
  it('aborts the in-flight generation’s network work on sign-out', async () => {
    const { configureAiProfileSession } = await freshService()
    h.generateProfile.mockReturnValue(new Promise(() => {}))

    configureAiProfileSession(SESSION)
    await flush()

    // Drive a real source fetch through the fetchers service.ts wired, so we get
    // hold of the AbortSignal it hands to net.fetch.
    const deps = h.generateProfile.mock.calls[0][0] as OrchestratorDeps
    void deps.fetchers.memories().catch(() => {})
    await flush()

    const signal = h.netFetch.mock.calls[0][1].signal as AbortSignal
    expect(signal.aborted).toBe(false)

    configureAiProfileSession(null) // sign-out
    expect(signal.aborted).toBe(true)
  })
})
