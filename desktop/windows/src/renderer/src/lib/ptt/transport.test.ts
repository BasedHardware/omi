import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AxiosError, AxiosHeaders } from 'axios'

const h = vi.hoisted(() => ({
  post: vi.fn(),
  getIdToken: vi.fn(async (_force?: boolean) => 'test-token'),
  // Mutable so feed-forward tests can vary voiceLanguages between turns.
  prefs: { language: 'en' } as { language: string; voiceLanguages?: string[] },
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
vi.mock('../preferences', () => ({ getPreferences: () => h.prefs }))
// Node test env has no window.localStorage / WebCrypto subtle for the real hash.
vi.mock('../clientDevice', () => ({ getWindowsDeviceIdHash: vi.fn(async () => 'abcd1234') }))

import {
  startPttStream,
  batchTranscribe,
  batchErrorMessage,
  __resetPttLanguageMemoryForTests
} from './transport'
import { startPttKeywordCollection, __resetPttKeywordsForTests } from './vocabulary'

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
  h.prefs = { language: 'en' }
  __resetPttLanguageMemoryForTests()
  __resetPttKeywordsForTests()
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

    emit({
      sessionId: sid,
      kind: 'segments',
      segments: [{ text: ' hello ' }, { text: '' }, { text: 'world' }]
    })
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

  it('feed sends exactly a subarray view window, never the full underlying buffer', async () => {
    // A trimmed backfill chunk is a subarray; sending its whole backing buffer
    // would ship pre-key-down samples the trim exists to exclude.
    const stream = await startPttStream({ onConnected: vi.fn(), onFinal: vi.fn(), onDead: vi.fn() })
    const backing = new Int16Array(4096)
    const view = backing.subarray(4000) // 96 samples = 192 bytes
    stream.feed(view)
    const sent = h.listen.feed.mock.calls[0][1] as ArrayBuffer
    expect(sent.byteLength).toBe(192)
    stream.stop()
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
  it('never POSTs an empty buffer (backend 400s a zero-byte body) — returns "" without network', async () => {
    const out = await batchTranscribe(new Int16Array(0), new AbortController().signal)
    expect(out).toBe('')
    expect(h.post).not.toHaveBeenCalled()
  })

  it('POSTs the raw PCM with the exact contract params and returns the transcript', async () => {
    h.post.mockResolvedValueOnce({ data: { transcript: 'hello world' } })
    const pcm = new Int16Array([1, 2, 3, 4])
    const out = await batchTranscribe(pcm, new AbortController().signal)
    expect(out).toBe('hello world')
    const [url, body, config] = h.post.mock.calls[0]
    expect(url).toBe('/v2/voice-message/transcribe')
    expect(body).toBe(pcm.buffer)
    // The context bridge (screenReadText/rewindFrames) is absent in this fake, so
    // keyword collection yields nothing but the always-on "Omi,OMI" brand prepend.
    expect(config.params).toEqual({
      language: 'en',
      sample_rate: 16000,
      encoding: 'linear16',
      channels: 1,
      keywords: 'Omi,OMI'
    })
    expect(config.headers['Content-Type']).toBe('application/octet-stream')
    expect(config.__noRetry).toBe(true)
  })

  it('ships the hold-start-collected keywords after the brand prepend', async () => {
    // Collection is kicked off at hold-start; batchTranscribe consumes the cache
    // instead of running OCR on the release/transcribe path.
    ;(globalThis as Record<string, unknown>).window = {
      omi: { screenReadText: async () => 'Photoshop Illustrator' }
    }
    startPttKeywordCollection(1000)
    h.post.mockResolvedValueOnce({ data: { transcript: 'x' } })
    await batchTranscribe(new Int16Array(4), new AbortController().signal)
    const kw = String(
      (h.post.mock.calls[0][2] as { params: Record<string, unknown> }).params.keywords
    ).split(',')
    expect(kw.slice(0, 2)).toEqual(['Omi', 'OMI'])
    expect(kw).toContain('Photoshop')
    expect(kw).toContain('Illustrator')
  })

  it('returns "" when the backend heard nothing', async () => {
    h.post.mockResolvedValueOnce({ data: { transcript: '' } })
    expect(await batchTranscribe(new Int16Array(4), new AbortController().signal)).toBe('')
  })

  it('retries exactly once on 401 with a force-refreshed token', async () => {
    h.post
      .mockRejectedValueOnce(axiosErrorWithStatus(401))
      .mockResolvedValueOnce({ data: { transcript: 'ok' } })
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

describe('spoken-language feed-forward (A3)', () => {
  const sig = (): AbortSignal => new AbortController().signal
  const paramsOf = (call: number): Record<string, unknown> =>
    (h.post.mock.calls[call][2] as { params: Record<string, unknown> }).params

  it('is inert when voiceLanguages is empty — the language param never changes', async () => {
    h.prefs = { language: 'en' } // no voiceLanguages
    h.post.mockResolvedValue({ data: { transcript: 'привет', language: 'ru' } })
    await batchTranscribe(new Int16Array(4), sig())
    await batchTranscribe(new Int16Array(4), sig())
    expect(paramsOf(0).language).toBe('en')
    expect(paramsOf(1).language).toBe('en') // detected 'ru' is NOT fed forward
  })

  it('feeds the last detected language into the next turn when it is a candidate', async () => {
    h.prefs = { language: 'en', voiceLanguages: ['ru', 'en'] }
    h.post.mockResolvedValueOnce({ data: { transcript: 'привет', language: 'ru' } })
    h.post.mockResolvedValueOnce({ data: { transcript: 'ok', language: 'en' } })
    await batchTranscribe(new Int16Array(4), sig()) // turn 1: static 'en', detects 'ru'
    await batchTranscribe(new Int16Array(4), sig()) // turn 2: uses fed-forward 'ru'
    expect(paramsOf(0).language).toBe('en')
    expect(paramsOf(1).language).toBe('ru')
  })

  it('ignores a detected language outside the candidate set', async () => {
    h.prefs = { language: 'en', voiceLanguages: ['ru', 'en'] }
    h.post.mockResolvedValueOnce({ data: { transcript: 'привет', language: 'ru' } }) // in set → remembered
    h.post.mockResolvedValueOnce({ data: { transcript: 'ciao', language: 'it' } }) // out of set → ignored
    h.post.mockResolvedValueOnce({ data: { transcript: 'ok', language: 'en' } })
    await batchTranscribe(new Int16Array(4), sig())
    await batchTranscribe(new Int16Array(4), sig())
    await batchTranscribe(new Int16Array(4), sig())
    expect(paramsOf(0).language).toBe('en') // no prior detection
    expect(paramsOf(1).language).toBe('ru') // fed forward from turn 1
    expect(paramsOf(2).language).toBe('ru') // turn 2's 'it' was out-of-set, so 'ru' persists
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
