import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { BackendSession } from '../assistants/core/session'

const state = vi.hoisted(() => ({
  epoch: 1,
  session: null as BackendSession | null,
  reset: () => {},
  fetch: vi.fn(),
  candidates: vi.fn(),
  mark: vi.fn()
}))
vi.mock('electron', () => ({ net: { fetch: state.fetch } }))
vi.mock('../assistants/core/session', () => ({
  getBackendSession: () => state.session,
  getSessionEpoch: () => state.epoch,
  getAbortSignal: () => undefined,
  onSessionReset: (fn: () => void) => {
    state.reset = fn
  },
  fetchWithFreshToken: (fn: (session: BackendSession) => Promise<Response>) => fn(state.session!)
}))
vi.mock('../ipc/db', () => ({
  fetchScreenActivitySyncCandidates: state.candidates,
  markScreenActivitySyncCandidates: state.mark,
  getAppMeta: () => 'test-install',
  setAppMeta: vi.fn()
}))
vi.mock('./captureService', () => ({ getRewindSettings: () => ({ retentionDays: 2 }) }))

import { onBackendSessionChanged, stopScreenActivitySync } from './screenActivitySync'

const candidate = {
  id: 42,
  ts: 1_700_000_000_000,
  app: 'Code',
  windowTitle: 'file.ts',
  ocrText: 'saved words',
  priorState: 0,
  embedding: null
}
const reply = (body: unknown, status = 200): Response =>
  new Response(JSON.stringify(body), { status })
const ack = (): Response => reply({ synced: 1, last_id: 42 })

beforeEach(() => {
  vi.useFakeTimers()
  state.epoch++
  state.session = { apiBase: 'https://backend.test', desktopApiBase: '', token: 'test-token' }
  state.fetch
    .mockReset()
    .mockImplementation((url: string) =>
      Promise.resolve(url.endsWith('/control') ? reply({ account_generation: 7 }) : ack())
    )
  state.candidates.mockReset().mockReturnValue([candidate])
  state.mark.mockReset()
})
afterEach(() => {
  stopScreenActivitySync()
  vi.useRealTimers()
})

async function start(): Promise<void> {
  onBackendSessionChanged(state.session)
  await vi.advanceTimersByTimeAsync(0)
}

describe('screen activity sync lifecycle', () => {
  it('sends the backend contract and marks only an acknowledged batch', async () => {
    await start()
    const [url, init] = state.fetch.mock.calls[1]
    expect(url).toBe('https://backend.test/v1/screen-activity/sync')
    expect(init.headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(init.body)).toMatchObject({
      account_generation: 7,
      deviceRetentionSeconds: 172800,
      rows: [{ id: 42, ocrText: 'saved words' }]
    })
    expect(state.mark).toHaveBeenCalledWith([candidate])
  })

  it.each([{ synced: 0, last_id: 42 }, { synced: 1, last_id: 41 }, null])(
    'keeps rows pending on incomplete or malformed acknowledgement %j',
    async (body) => {
      state.fetch
        .mockResolvedValueOnce(reply({ account_generation: 7 }))
        .mockResolvedValueOnce(reply(body))
      await start()
      expect(state.mark).not.toHaveBeenCalled()
    }
  )

  it('retains paywalled rows and restores the normal interval after recovery', async () => {
    state.fetch
      .mockResolvedValueOnce(reply({ account_generation: 7 }))
      .mockResolvedValueOnce(reply({}, 402))
    await start()
    expect(state.mark).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(state.fetch).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(state.mark).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(state.mark).toHaveBeenCalledTimes(2)
  })

  it('keeps one request in flight and stops scheduling after session reset', async () => {
    let finish!: (response: Response) => void
    state.fetch.mockResolvedValueOnce(reply({ account_generation: 7 })).mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        })
    )
    await start()
    await vi.advanceTimersByTimeAsync(120_000)
    expect(state.fetch).toHaveBeenCalledTimes(2)
    state.epoch++
    state.session = null
    state.reset()
    finish(ack())
    await vi.advanceTimersByTimeAsync(120_000)
    expect(state.mark).not.toHaveBeenCalled()
    expect(state.fetch).toHaveBeenCalledTimes(2)
  })

  it('does not let a failed old-session request back off the new account', async () => {
    let finish!: (response: Response) => void
    state.fetch.mockResolvedValueOnce(reply({ account_generation: 7 })).mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve
        })
    )
    await start()
    state.epoch++
    state.reset()
    state.session = { ...state.session!, token: 'next-account' }
    onBackendSessionChanged(state.session)
    finish(reply({}, 500))
    await vi.advanceTimersByTimeAsync(0)
    expect(state.mark).not.toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(state.mark).toHaveBeenCalledTimes(1)
  })
})
