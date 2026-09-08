// The pi-mono auth host is a pure session relay: it forwards the Firebase
// session to the main-side pi-mono session store (inert without one) and clears
// it on sign-out. It must NEVER spawn or drive pi — that lifecycle lives in
// main. These tests pin exactly that contract, including the C2 stale-push race.
import { beforeEach, describe, expect, it, vi } from 'vitest'

// Hoisted so the vi.mock factories below can close over them.
const h = vi.hoisted(() => ({
  onIdTokenChanged: vi.fn(),
  auth: { currentUser: null as FakeUser | null }
}))

vi.mock('firebase/auth', () => ({ onIdTokenChanged: h.onIdTokenChanged }))
vi.mock('./firebase', () => ({ auth: h.auth }))

type FakeUser = { getIdToken: () => Promise<string> }
type AuthCallback = (user: FakeUser | null) => void

/** The callback startPiMonoAuthHost registered with onIdTokenChanged. */
function authCallback(): AuthCallback {
  return h.onIdTokenChanged.mock.calls[0][1] as AuthCallback
}

/** Fire a sign-in the way Firebase would: currentUser is already set. */
function signIn(token: string): FakeUser {
  const user: FakeUser = { getIdToken: async () => token }
  h.auth.currentUser = user
  authCallback()(user)
  return user
}

const flush = (): Promise<void> => new Promise((r) => setTimeout(r, 0))

function installWindowOmi(): { pimonoSetSession: ReturnType<typeof vi.fn> } {
  const pimonoSetSession = vi.fn(async () => undefined)
  ;(globalThis as unknown as { window: unknown }).window = { omi: { pimonoSetSession } }
  return { pimonoSetSession }
}

// `started` is module-scoped, so every test needs a fresh module instance.
async function freshHost(): Promise<typeof import('./piMonoAuthHost')> {
  vi.resetModules()
  return import('./piMonoAuthHost')
}

beforeEach(() => {
  h.onIdTokenChanged.mockClear()
  h.auth.currentUser = null
  vi.spyOn(console, 'log').mockImplementation(() => {})
  vi.spyOn(console, 'warn').mockImplementation(() => {})
})

describe('startPiMonoAuthHost (session relay)', () => {
  it('pushes a fresh session (token + desktop base) to main on sign-in', async () => {
    const { pimonoSetSession } = installWindowOmi()
    const { startPiMonoAuthHost } = await freshHost()

    startPiMonoAuthHost()
    signIn('tok-abc')
    await flush()

    expect(pimonoSetSession).toHaveBeenCalledTimes(1)
    const session = pimonoSetSession.mock.calls[0][0] as Record<string, unknown>
    expect(session).toMatchObject({ token: 'tok-abc' })
    expect(session).toHaveProperty('desktopApiBase')
  })

  it('relays again with the refreshed token when Firebase rotates the id token', async () => {
    const { pimonoSetSession } = installWindowOmi()
    const { startPiMonoAuthHost } = await freshHost()

    startPiMonoAuthHost()
    signIn('tok-1')
    await flush()
    signIn('tok-2')
    await flush()

    expect(pimonoSetSession).toHaveBeenCalledTimes(2)
    expect(pimonoSetSession.mock.calls[1][0]).toMatchObject({ token: 'tok-2' })
  })

  it('clears the session on sign-out', async () => {
    const { pimonoSetSession } = installWindowOmi()
    const { startPiMonoAuthHost } = await freshHost()

    startPiMonoAuthHost()
    authCallback()(null)
    await flush()

    expect(pimonoSetSession).toHaveBeenCalledWith(null)
  })

  // C2: getIdToken() can be a real network refresh. If the user signs out during
  // that await, the resolved token must NOT overtake the clear and re-arm main
  // with the signed-out user's credentials.
  it('(C2) drops a slow session push that a sign-out overtook', async () => {
    const { pimonoSetSession } = installWindowOmi()
    const { startPiMonoAuthHost } = await freshHost()
    startPiMonoAuthHost()

    let resolveToken!: (t: string) => void
    const user: FakeUser = { getIdToken: () => new Promise<string>((r) => (resolveToken = r)) }
    h.auth.currentUser = user
    authCallback()(user)
    await flush()
    expect(pimonoSetSession).not.toHaveBeenCalled() // still awaiting the token

    h.auth.currentUser = null
    authCallback()(null)
    await flush()
    expect(pimonoSetSession).toHaveBeenCalledWith(null)

    resolveToken('tok-signed-out-user')
    await flush()

    expect(pimonoSetSession).toHaveBeenCalledTimes(1)
    expect(pimonoSetSession).toHaveBeenLastCalledWith(null)
    expect(pimonoSetSession).not.toHaveBeenCalledWith(
      expect.objectContaining({ token: 'tok-signed-out-user' })
    )
  })

  it('is idempotent — repeated starts register only one auth listener', async () => {
    installWindowOmi()
    const { startPiMonoAuthHost } = await freshHost()

    startPiMonoAuthHost()
    startPiMonoAuthHost()
    startPiMonoAuthHost()

    expect(h.onIdTokenChanged).toHaveBeenCalledTimes(1)
  })

  it('swallows a failing session push (an auth listener must never reject)', async () => {
    const { pimonoSetSession } = installWindowOmi()
    pimonoSetSession.mockRejectedValueOnce(new Error('ipc down'))
    const { startPiMonoAuthHost } = await freshHost()

    startPiMonoAuthHost()
    expect(() => signIn('tok-abc')).not.toThrow()
    await flush()

    expect(console.warn).toHaveBeenCalledWith(
      '[pi-mono-auth-host] session push failed',
      expect.any(Error)
    )
  })
})
