import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  auth: { currentUser: null as null | { uid: string } },
  startOmiListen: vi.fn()
}))

vi.mock('./firebase', () => ({ auth: h.auth }))
vi.mock('./omiListenClient', () => ({ startOmiListen: h.startOmiListen }))

import { startTranscription, type TranscriptionCallbacks } from './transcriptionClient'

function callbacks(): TranscriptionCallbacks {
  return {
    onLine: vi.fn(),
    onInterim: vi.fn(),
    onBackend: vi.fn(),
    onError: vi.fn()
  }
}

beforeEach(() => {
  h.auth.currentUser = null
  h.startOmiListen.mockReset()
})

describe('startTranscription startup contract', () => {
  it('rejects instead of returning an empty handle when the user is not signed in', async () => {
    const cb = callbacks()

    await expect(startTranscription('system', cb, 'transcribe')).rejects.toThrow(
      'Omi transcription unavailable (not signed in)'
    )
    expect(cb.onError).toHaveBeenCalledOnce()
    expect(h.startOmiListen).not.toHaveBeenCalled()
  })

  it('rejects when the source or transport fails before readiness', async () => {
    h.auth.currentUser = { uid: 'user-1' }
    const stop = vi.fn()
    h.startOmiListen.mockImplementation(
      async (_source: string, listener: { onError: (error: Error, fatal: boolean) => void }) => {
        const error = new Error('loopback unavailable')
        error.name = 'NotAllowedError'
        setTimeout(() => listener.onError(error, true), 0)
        return { stop, finalize: vi.fn() }
      }
    )
    const cb = callbacks()

    await expect(startTranscription('system', cb, 'transcribe')).rejects.toMatchObject({
      name: 'NotAllowedError',
      message: 'loopback unavailable'
    })
    expect(cb.onError).toHaveBeenCalledOnce()
    expect(stop).toHaveBeenCalledOnce()
  })

  it('aborts and tears down an in-flight startup immediately', async () => {
    h.auth.currentUser = { uid: 'user-1' }
    const stop = vi.fn()
    h.startOmiListen.mockResolvedValue({ stop, finalize: vi.fn() })
    const cb = callbacks()
    const controller = new AbortController()

    const startup = startTranscription('system', cb, 'transcribe', undefined, controller.signal)
    await Promise.resolve()
    controller.abort()

    await expect(startup).rejects.toMatchObject({ name: 'AbortError' })
    expect(stop).toHaveBeenCalledOnce()
    expect(cb.onError).toHaveBeenCalledOnce()
  })
})

describe('startTranscription post-connect close reasons', () => {
  // Connect a lane, then close it the way the backend did; return the surfaced error.
  async function closeWith(code: number, reason: string): Promise<string> {
    h.auth.currentUser = { uid: 'user-1' }
    let listener: {
      onConnected: () => void
      onClosed: (code: number, reason: string) => void
    } | null = null
    h.startOmiListen.mockImplementation(async (_source: string, l: typeof listener) => {
      listener = l
      setTimeout(() => l?.onConnected(), 0)
      return { stop: vi.fn(), finalize: vi.fn() }
    })
    const cb = callbacks()
    await startTranscription('system', cb, 'transcribe')
    listener!.onClosed(code, reason)
    expect(cb.onError).toHaveBeenCalledOnce()
    return (vi.mocked(cb.onError).mock.calls[0][0] as Error).message
  }

  it('reports a 1008 idle timeout as an ordinary close, not "quota used up"', async () => {
    // Live bug: this exact close was surfaced as "free Omi transcription quota is
    // used up", which stopped the meeting capture instead of reconnecting.
    const message = await closeWith(1008, 'Idle timeout: no audio for 60s')
    expect(message).toBe(
      'Omi transcription stopped: Omi transcribe-stream closed (1008) Idle timeout: no audio for 60s'
    )
    expect(message).not.toMatch(/quota/i)
  })

  it('reports a spent daily budget as the daily limit, without offering a subscription', async () => {
    const message = await closeWith(1008, 'Daily transcription budget exhausted')
    expect(message).toMatch(/daily voice transcription limit is used up/)
    expect(message).not.toMatch(/subscription/i)
  })

  it('still reports a trial_expired close as the quota/entitlement stop', async () => {
    const message = await closeWith(1008, 'trial_expired')
    expect(message).toMatch(/free Omi transcription quota is used up/)
  })
})
