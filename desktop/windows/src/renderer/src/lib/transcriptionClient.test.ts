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
