// Main side of the token PULL channel. The renderer boundary (ipcMain / a window's
// webContents) is mocked; these pin the correlation + the fail-safe contract that
// session.ts depends on: a no-window / timeout / malformed reply resolves NULL
// (which session.ts treats as "no refresh", never as a sign-out), and a well-formed
// reply resolves the matching request.
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({ on: vi.fn() }))

vi.mock('electron', () => ({ ipcMain: { on: h.on } }))

type Reply = (event: unknown, requestId: unknown, session: unknown) => void

const SESSION = {
  apiBase: 'https://api.example',
  desktopApiBase: 'https://desktop.example',
  token: 'tok'
}

/** The ipcMain 'session:tokenResponse' handler the module registered on first use. */
function replyHandler(): Reply {
  const call = h.on.mock.calls.find((c) => c[0] === 'session:tokenResponse')
  if (!call) throw new Error('session:tokenResponse handler was never registered')
  return call[1] as Reply
}

async function freshModule(): Promise<typeof import('./tokenPull')> {
  vi.resetModules()
  h.on.mockClear()
  return import('./tokenPull')
}

function fakeWc(): { send: ReturnType<typeof vi.fn>; isDestroyed: () => boolean } {
  return { send: vi.fn(), isDestroyed: () => false }
}

beforeEach(() => {
  vi.useRealTimers()
})

describe('makeRendererTokenRefresher', () => {
  it('sends a correlated request and resolves the matching reply', async () => {
    const { makeRendererTokenRefresher } = await freshModule()
    const wc = fakeWc()
    const refresher = makeRendererTokenRefresher(() => wc as never)

    const p = refresher()
    await Promise.resolve()
    expect(wc.send).toHaveBeenCalledWith('session:tokenRequest', expect.any(Number))
    const requestId = wc.send.mock.calls[0][1] as number

    replyHandler()({}, requestId, SESSION)
    await expect(p).resolves.toEqual(SESSION)
  })

  it('resolves null when there is no window to ask', async () => {
    const { makeRendererTokenRefresher } = await freshModule()
    const refresher = makeRendererTokenRefresher(() => null)
    await expect(refresher()).resolves.toBeNull()
  })

  it('ignores a reply whose requestId does not match (stale/late reply)', async () => {
    const { makeRendererTokenRefresher } = await freshModule()
    const wc = fakeWc()
    const refresher = makeRendererTokenRefresher(() => wc as never)

    const p = refresher()
    await Promise.resolve()
    const requestId = wc.send.mock.calls[0][1] as number

    replyHandler()({}, requestId + 999, SESSION) // wrong id → must not resolve p
    replyHandler()({}, requestId, SESSION) // correct id → resolves
    await expect(p).resolves.toEqual(SESSION)
  })

  it('resolves null on a malformed reply (never hands session.ts a bad session)', async () => {
    const { makeRendererTokenRefresher } = await freshModule()
    const wc = fakeWc()
    const refresher = makeRendererTokenRefresher(() => wc as never)

    const p = refresher()
    await Promise.resolve()
    const requestId = wc.send.mock.calls[0][1] as number

    replyHandler()({}, requestId, { token: 'tok' }) // missing bases
    await expect(p).resolves.toBeNull()
  })

  it('resolves null when the renderer never replies (timeout)', async () => {
    vi.useFakeTimers()
    const { makeRendererTokenRefresher } = await freshModule()
    const wc = fakeWc()
    const refresher = makeRendererTokenRefresher(() => wc as never)

    const p = refresher()
    await vi.advanceTimersByTimeAsync(8_000)
    await expect(p).resolves.toBeNull()
  })
})
