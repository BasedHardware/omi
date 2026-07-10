import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  getIdToken: vi.fn(async (_force?: boolean) => 'test-token'),
  listen: {
    start: vi.fn(async (_args: Record<string, unknown>) => {}),
    feed: vi.fn(),
    finalize: vi.fn(),
    stop: vi.fn(async () => {}),
    handlers: [] as Array<(msg: unknown) => void>
  }
}))

vi.mock('../apiClient', () => ({ omiApi: { post: h.post } }))
vi.mock('../firebase', () => ({ auth: { currentUser: { getIdToken: h.getIdToken } } }))
vi.mock('../preferences', () => ({ getPreferences: () => ({ language: 'en' }) }))

import { startPttStream, batchTranscribe, batchErrorMessage } from './transport'

function axiosErrorWithStatus(status: number): AxiosError {
  return new AxiosError('boom', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data: {},
    headers: {},
    config: { headers: new AxiosHeaders() }
  })
}

function emit(msg: Record<string, unknown>): void {
  for (const fn of [...h.listen.handlers]) fn(msg)
}

beforeEach(() => {
  vi.clearAllMocks()
  h.listen.handlers = []
  h.getIdToken.mockResolvedValue('test-token')
  // Minimal window.omi bridge fake.
  ;(globalThis as Record<string, unknown>).window = {
    omi: {
      listenStart: h.listen.start,
      listenFeed: h.listen.feed,
      listenFinalize: h.listen.finalize,
      listenStop: h.listen.stop,
      onListenMessage: (fn: (msg: unknown) => void) => {
        h.listen.handlers.push(fn)
        return () => {
          h.listen.handlers = h.listen.handlers.filter((x) => x !== fn)
        }
      }
    }
  }
})

describe('startPttStream', () => {
  it('starts a ptt-mode session and maps bridge messages to callbacks (own session only)', async () => {
    const cb = { onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() }
    const stream = await startPttStream(cb)
    const args = h.listen.start.mock.calls[0][0]
    expect(args.mode).toBe('ptt')
    expect(args.token).toBe('test-token')
    const sid = args.sessionId as string

    emit({ sessionId: 'someone-else', kind: 'connected' })
    expect(cb.onConnected).not.toHaveBeenCalled()

    emit({ sessionId: sid, kind: 'connected' })
    expect(cb.onConnected).toHaveBeenCalledOnce()

    emit({ sessionId: sid, kind: 'segments', segments: [{ text: ' hello ' }, { text: '' }, { text: 'world' }] })
    expect(cb.onFinal.mock.calls.map((c) => c[0])).toEqual(['hello', 'world'])
    stream.stop()
  })

  it('feed forwards chunks and stops forwarding after stop()', async () => {
    const stream = await startPttStream({ onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() })
    const pcm = new Int16Array([1, 2, 3])
    stream.feed(pcm)
    expect(h.listen.feed).toHaveBeenCalledOnce()
    stream.stop()
    stream.feed(pcm)
    expect(h.listen.feed).toHaveBeenCalledOnce()
    expect(h.listen.stop).toHaveBeenCalledOnce()
  })

  it('reports death once — on fatal error or close, whichever first', async () => {
    const cb = { onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() }
    const stream = await startPttStream(cb)
    const sid = h.listen.start.mock.calls[0][0].sessionId as string
    emit({ sessionId: sid, kind: 'error', message: 'x', fatal: true })
    emit({ sessionId: sid, kind: 'closed', code: 1006, reason: '' })
    expect(cb.onDead).toHaveBeenCalledOnce()
    stream.stop()
  })

  it('a non-fatal error does not kill the stream', async () => {
    const cb = { onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() }
    const stream = await startPttStream(cb)
    const sid = h.listen.start.mock.calls[0][0].sessionId as string
    emit({ sessionId: sid, kind: 'error', message: 'transient', fatal: false })
    expect(cb.onDead).not.toHaveBeenCalled()
    stream.stop()
  })

  it('an intentional stop() suppresses the close echo — no onDead', async () => {
    const cb = { onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() }
    const stream = await startPttStream(cb)
    const sid = h.listen.start.mock.calls[0][0].sessionId as string
    stream.stop()
    emit({ sessionId: sid, kind: 'closed', code: 1000, reason: '' })
    expect(cb.onDead).not.toHaveBeenCalled()
  })
})

describe('batchTranscribe', () => {
  it('POSTs the raw PCM with the exact contract params and returns the transcript', async () => {
    h.post.mockResolvedValueOnce({ data: { transcript: 'hello world' } })
    const pcm = new Int16Array([1, 2, 3, 4])
    const out = await batchTranscribe(pcm, new AbortController().signal)
    expect(out).toBe('hello world')
    const [url, body, config] = h.post.mock.calls[0]
    expect(url).toBe('/v2/voice-message/transcribe')
    expect(body).toBe(pcm.buffer)
    expect(config.params).toEqual({ language: 'en', sample_rate: 16000, encoding: 'linear16', channels: 1 })
    expect(config.headers['Content-Type']).toBe('application/octet-stream')
    expect(config.__noRetry).toBe(true)
  })

  it('returns "" when the backend heard nothing', async () => {
    h.post.mockResolvedValueOnce({ data: { transcript: '' } })
    expect(await batchTranscribe(new Int16Array(4), new AbortController().signal)).toBe('')
  })

  it('retries exactly once on 401 with a force-refreshed token', async () => {
    h.post.mockRejectedValueOnce(axiosErrorWithStatus(401)).mockResolvedValueOnce({ data: { transcript: 'ok' } })
    expect(await batchTranscribe(new Int16Array(4), new AbortController().signal)).toBe('ok')
    expect(h.getIdToken).toHaveBeenCalledWith(true)
    expect(h.post).toHaveBeenCalledTimes(2)
  })

  it('does not retry on non-401 failures', async () => {
    h.post.mockRejectedValueOnce(axiosErrorWithStatus(429))
    await expect(batchTranscribe(new Int16Array(4), new AbortController().signal)).rejects.toThrow()
    expect(h.post).toHaveBeenCalledTimes(1)
  })
})

describe('batchErrorMessage', () => {
  it('maps each backend rejection to its friendly strip message', () => {
    expect(batchErrorMessage(axiosErrorWithStatus(402))).toMatch(/omi plan/i)
    expect(batchErrorMessage(axiosErrorWithStatus(413))).toMatch(/too long/i)
    expect(batchErrorMessage(axiosErrorWithStatus(429))).toMatch(/limit/i)
    expect(batchErrorMessage(axiosErrorWithStatus(401))).toMatch(/sign.?in/i)
  })
  it('maps timeouts/network errors to the connection message', () => {
    expect(batchErrorMessage(new AxiosError('timeout', 'ECONNABORTED'))).toMatch(/connection/i)
    expect(batchErrorMessage(new Error('anything'))).toMatch(/connection/i)
  })
})
