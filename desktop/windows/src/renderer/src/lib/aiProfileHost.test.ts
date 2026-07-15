// The AI-profile renderer host is a pure session relay: it forwards the Firebase
// session to the main-process profile service (which is inert without one) and
// clears it on sign-out. It must NEVER drive generation — cadence lives in main.
// These tests pin exactly that contract.
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Hoisted so the vi.mock factories below (which are hoisted above the imports)
// can close over them.
const h = vi.hoisted(() => ({
  onIdTokenChanged: vi.fn(),
  // Stands in for the Firebase Auth instance; `currentUser` is what the host
  // re-checks after awaiting getIdToken().
  auth: { currentUser: null as FakeUser | null }
}))

vi.mock('firebase/auth', () => ({ onIdTokenChanged: h.onIdTokenChanged }))
vi.mock('./firebase', () => ({ auth: h.auth }))

type FakeUser = { getIdToken: () => Promise<string> }
type AuthCallback = (user: FakeUser | null) => void

/** The callback startAiProfileHost registered with onIdTokenChanged. */
function authCallback(): AuthCallback {
  return h.onIdTokenChanged.mock.calls[0][1] as AuthCallback
}

/** Fire a sign-in event the way Firebase would: currentUser is already set by the
 *  time the listener runs. */
function signIn(token: string): FakeUser {
  const user: FakeUser = { getIdToken: async () => token }
  h.auth.currentUser = user
  authCallback()(user)
  return user
}

/** Let the listener's fire-and-forget promise chain settle. */
const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

function installWindowOmi(): { aiProfileSetSession: ReturnType<typeof vi.fn> } {
  const aiProfileSetSession = vi.fn(async () => undefined)
  // setSession is the only member the host should ever touch; the other two are
  // stubbed purely so a test can assert the host never calls them.
  ;(globalThis as unknown as { window: unknown }).window = {
    omi: { aiProfileSetSession, aiProfileGenerateNow: vi.fn(), aiProfileGetLatest: vi.fn() }
  }
  return { aiProfileSetSession }
}

// `started` is module-scoped, so every test needs a fresh module instance.
async function freshHost(): Promise<typeof import('./aiProfileHost')> {
  vi.resetModules()
  return import('./aiProfileHost')
}

beforeEach(() => {
  h.onIdTokenChanged.mockClear()
  h.auth.currentUser = null
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

describe('startAiProfileHost (session relay)', () => {
  it('pushes a fresh session (bases + token) to main on sign-in', async () => {
    const { aiProfileSetSession } = installWindowOmi()
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    signIn('tok-abc')
    await flush()

    expect(aiProfileSetSession).toHaveBeenCalledTimes(1)
    expect(aiProfileSetSession).toHaveBeenCalledWith(expect.objectContaining({ token: 'tok-abc' }))
    // The relayed session carries both API bases the main service needs.
    const session = aiProfileSetSession.mock.calls[0][0] as Record<string, unknown>
    expect(session).toHaveProperty('apiBase')
    expect(session).toHaveProperty('desktopApiBase')
  })

  it('relays again with the refreshed token when Firebase rotates the id token', async () => {
    const { aiProfileSetSession } = installWindowOmi()
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    // Firebase re-fires this listener ~hourly; each fire must refresh main's
    // cached token (otherwise main's backend calls start 401ing).
    signIn('tok-1')
    await flush()
    signIn('tok-2')
    await flush()

    expect(aiProfileSetSession).toHaveBeenCalledTimes(2)
    expect(aiProfileSetSession.mock.calls[1][0]).toMatchObject({ token: 'tok-2' })
  })

  it('clears the session on sign-out', async () => {
    const { aiProfileSetSession } = installWindowOmi()
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    authCallback()(null)
    await flush()

    expect(aiProfileSetSession).toHaveBeenCalledWith(null)
  })

  it('never drives generation itself (cadence belongs to main)', async () => {
    installWindowOmi()
    const omi = (
      globalThis as unknown as { window: { omi: Record<string, ReturnType<typeof vi.fn>> } }
    ).window.omi
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    signIn('tok-abc')
    await flush()

    expect(omi.aiProfileGenerateNow).not.toHaveBeenCalled()
    expect(omi.aiProfileGetLatest).not.toHaveBeenCalled()
  })

  // C2. getIdToken() can be a real network refresh (hundreds of ms). If the user
  // signs out during that await, the resolved token must NOT overtake
  // clearSession() and re-arm main with the signed-out user's credentials —
  // which would leave main holding their token for its full lifetime.
  it('(C2) drops a slow session push that a sign-out overtook', async () => {
    const { aiProfileSetSession } = installWindowOmi()
    const { startAiProfileHost } = await freshHost()
    startAiProfileHost()

    // A sign-in whose token refresh hangs.
    let resolveToken!: (t: string) => void
    const user: FakeUser = { getIdToken: () => new Promise<string>((r) => (resolveToken = r)) }
    h.auth.currentUser = user
    authCallback()(user)
    await flush()
    expect(aiProfileSetSession).not.toHaveBeenCalled() // still awaiting the token

    // User signs out while that token is still in flight.
    h.auth.currentUser = null
    authCallback()(null)
    await flush()
    expect(aiProfileSetSession).toHaveBeenCalledWith(null)

    // NOW the stale token resolves. It must be dropped, not relayed.
    resolveToken('tok-signed-out-user')
    await flush()

    expect(aiProfileSetSession).toHaveBeenCalledTimes(1)
    expect(aiProfileSetSession).toHaveBeenLastCalledWith(null)
    expect(aiProfileSetSession).not.toHaveBeenCalledWith(
      expect.objectContaining({ token: 'tok-signed-out-user' })
    )
  })

  it('is idempotent — repeated starts register only one auth listener', async () => {
    installWindowOmi()
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    startAiProfileHost()
    startAiProfileHost()

    expect(h.onIdTokenChanged).toHaveBeenCalledTimes(1)
  })

  it('swallows a failing session push (an auth listener must never reject)', async () => {
    const { aiProfileSetSession } = installWindowOmi()
    aiProfileSetSession.mockRejectedValueOnce(new Error('ipc down'))
    const { startAiProfileHost } = await freshHost()

    startAiProfileHost()
    expect(() => signIn('tok-abc')).not.toThrow()
    await flush()

    expect(console.warn).toHaveBeenCalledWith(
      '[ai-profile-host] session push failed',
      expect.any(Error)
    )
  })
})
