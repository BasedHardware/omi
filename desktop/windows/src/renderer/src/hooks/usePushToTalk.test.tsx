// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import { HOLD_THRESHOLD_MS, STREAM_FINALIZE_DEADLINE_MS, ERROR_STRIP_MS } from '../lib/ptt/constants'

// The pure machine/gate/transport logic has its own suites — these tests cover
// what only the hook owns: the Space gesture timing, effect interpretation,
// foreground/background job isolation (rapid holds), and UI state/timers.

type CaptureOpts = {
  onChunk?: (pcm: Int16Array) => void
  onCapped?: () => void
  backfillMs?: number
}
type StreamCbs = {
  onConnected: () => void
  onFinal: (text: string) => void
  onDead: () => void
}

const h = vi.hoisted(() => {
  const state = {
    drainBuffer: new Int16Array(0),
    /** When true, startPttStream stays pending until releaseStream() is called —
     *  simulates the window where audio flows before the session exists. */
    deferStream: false,
    streamReleasers: [] as Array<() => void>,
    captureOpts: [] as CaptureOpts[],
    captures: [] as Array<{ analyser: object; drain: ReturnType<typeof vi.fn>; dispose: ReturnType<typeof vi.fn> }>,
    streamCbs: [] as StreamCbs[],
    streams: [] as Array<{
      feed: ReturnType<typeof vi.fn>
      finalize: ReturnType<typeof vi.fn>
      stop: ReturnType<typeof vi.fn>
    }>,
    batchCalls: [] as Array<{
      pcm: Int16Array
      signal: AbortSignal
      resolve: (t: string) => void
      reject: (e: unknown) => void
    }>
  }
  return {
    state,
    startPttCapture: vi.fn(async (opts: CaptureOpts) => {
      state.captureOpts.push(opts)
      const capture = {
        analyser: {},
        drain: vi.fn(async () => state.drainBuffer),
        dispose: vi.fn()
      }
      state.captures.push(capture)
      return capture
    }),
    startPttStream: vi.fn((cb: StreamCbs) => {
      state.streamCbs.push(cb)
      const stream = { feed: vi.fn(), finalize: vi.fn(), stop: vi.fn() }
      state.streams.push(stream)
      if (!state.deferStream) return Promise.resolve(stream)
      return new Promise<typeof stream>((resolve) => {
        state.streamReleasers.push(() => resolve(stream))
      })
    }),
    batchTranscribe: vi.fn(
      (pcm: Int16Array, signal: AbortSignal) =>
        new Promise<string>((resolve, reject) => state.batchCalls.push({ pcm, signal, resolve, reject }))
    )
  }
})

vi.mock('../lib/ptt/capture', () => ({
  startPttCapture: h.startPttCapture,
  warmPttMic: vi.fn(async () => {}),
  releasePttMic: vi.fn()
}))
vi.mock('../lib/ptt/transport', () => ({
  startPttStream: h.startPttStream,
  batchTranscribe: h.batchTranscribe,
  batchErrorMessage: () => 'friendly error',
  prefetchAuthToken: vi.fn()
}))

import { usePushToTalk } from './usePushToTalk'

const VOICED_1S = new Int16Array(16000).fill(8000) // 1s, fully voiced → gate ok
const SHORT_200MS = new Int16Array(3200).fill(8000) // 0.2s → too-short

function setup(): {
  result: { current: ReturnType<typeof usePushToTalk> }
  onCommit: ReturnType<typeof vi.fn>
  onTranscript: ReturnType<typeof vi.fn>
  onCaptureEnd: ReturnType<typeof vi.fn>
} {
  const onCommit = vi.fn()
  const onTranscript = vi.fn()
  const onCaptureEnd = vi.fn()
  const { result } = renderHook(() =>
    usePushToTalk({
      onCommit,
      onTranscript,
      onCaptureEnd,
      restoreDraft: vi.fn(),
      getDraft: () => ''
    })
  )
  return { result, onCommit, onTranscript, onCaptureEnd }
}

const pressSpace = (): void => {
  act(() => {
    window.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', code: 'Space' }))
  })
}
const releaseSpace = (): void => {
  act(() => {
    window.dispatchEvent(new KeyboardEvent('keyup', { key: ' ', code: 'Space' }))
  })
}
const advance = async (ms: number): Promise<void> => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  h.state.drainBuffer = VOICED_1S
  h.state.deferStream = false
  h.state.streamReleasers = []
  h.state.captureOpts = []
  h.state.captures = []
  h.state.streamCbs = []
  h.state.streams = []
  h.state.batchCalls = []
})
afterEach(() => {
  cleanup() // vitest runs without globals, so RTL's auto-cleanup never registers
  vi.useRealTimers()
})

describe('space gesture', () => {
  it('a quick tap never starts a capture', async () => {
    setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS - 100)
    releaseSpace()
    await advance(1000)
    expect(h.startPttCapture).not.toHaveBeenCalled()
  })

  it('a hold starts capture (with key-down backfill) and the opportunistic stream', async () => {
    const { result } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(result.current.recording).toBe(true)
    expect(h.startPttCapture).toHaveBeenCalledOnce()
    // Warm-mic backfill covers exactly the hold threshold (fake timers → precise).
    expect(h.state.captureOpts[0].backfillMs).toBe(HOLD_THRESHOLD_MS)
    expect(h.startPttStream).toHaveBeenCalledOnce()
  })

  it('a LONG hold (30s+) keeps recording — the watchdog never fires while the key is down', async () => {
    // Regression: the watchdog used to arm at hold start and silently discard
    // any dictation longer than 25s with a false "timed out" error.
    const { result, onCommit } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    await advance(30_000)
    expect(result.current.recording).toBe(true)
    expect(result.current.error).toBeNull()
    releaseSpace()
    await advance(0)
    await act(async () => {
      h.state.batchCalls[0].resolve('long dictation')
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onCommit).toHaveBeenCalledWith('long dictation')
  })

  it('audio captured before the stream session exists (backfill + early speech) is flushed into it in order', async () => {
    h.state.deferStream = true
    setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    // The capture emits chunks while startPttStream is still pending.
    const early1 = new Int16Array([1, 1])
    const early2 = new Int16Array([2, 2])
    act(() => {
      h.state.captureOpts[0].onChunk?.(early1)
      h.state.captureOpts[0].onChunk?.(early2)
    })
    expect(h.state.streams[0].feed).not.toHaveBeenCalled()
    // Session resolves → queued audio flushes first, then live audio flows direct.
    await act(async () => {
      h.state.streamReleasers[0]()
      await vi.advanceTimersByTimeAsync(0)
    })
    const live = new Int16Array([3, 3])
    act(() => h.state.captureOpts[0].onChunk?.(live))
    expect(h.state.streams[0].feed.mock.calls.map((c) => c[0])).toEqual([early1, early2, live])
  })
})

describe('release paths', () => {
  it('release with no stream connection → batch → commit clears the draft', async () => {
    const { result, onCommit, onTranscript, onCaptureEnd } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0) // drain + gate microtasks
    expect(result.current.transcribing).toBe(true)
    expect(h.state.batchCalls).toHaveLength(1)
    await act(async () => {
      h.state.batchCalls[0].resolve('hello world')
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onCommit).toHaveBeenCalledWith('hello world')
    expect(onTranscript).toHaveBeenLastCalledWith('')
    expect(onCaptureEnd).toHaveBeenCalledOnce()
    expect(result.current.transcribing).toBe(false)
  })

  it('connected stream: finalize is sent and the post-release segment commits instantly (no batch)', async () => {
    const { onCommit } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    act(() => h.state.streamCbs[0].onConnected())
    releaseSpace()
    await advance(0)
    expect(h.state.streams[0].finalize).toHaveBeenCalledOnce()
    act(() => h.state.streamCbs[0].onFinal('hi there'))
    expect(onCommit).toHaveBeenCalledWith('hi there')
    expect(h.batchTranscribe).not.toHaveBeenCalled()
  })

  it('stream deadline expires → batch fallback commits', async () => {
    const { onCommit } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    act(() => h.state.streamCbs[0].onConnected())
    releaseSpace()
    await advance(0)
    await advance(STREAM_FINALIZE_DEADLINE_MS)
    expect(h.state.batchCalls).toHaveLength(1)
    await act(async () => {
      h.state.batchCalls[0].resolve('from batch')
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onCommit).toHaveBeenCalledWith('from batch')
  })

  it('too-short hold → hint, no network, and an immediate re-hold works', async () => {
    h.state.drainBuffer = SHORT_200MS
    const { result, onCommit } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    expect(result.current.hint).toMatch(/hold longer/i)
    expect(h.batchTranscribe).not.toHaveBeenCalled()
    expect(onCommit).not.toHaveBeenCalled()
    // Rapid re-press: a new capture starts right away.
    h.state.drainBuffer = VOICED_1S
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(result.current.recording).toBe(true)
    expect(h.startPttCapture).toHaveBeenCalledTimes(2)
  })

  it('batch failure → friendly error strip that auto-clears', async () => {
    const { result, onCommit } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    await act(async () => {
      h.state.batchCalls[0].reject(new Error('boom'))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.error).toBe('friendly error')
    expect(onCommit).not.toHaveBeenCalled()
    await advance(ERROR_STRIP_MS)
    expect(result.current.error).toBeNull()
  })
})

describe('foreground/background isolation (rapid holds)', () => {
  it('a new hold never aborts the previous capture in-flight batch; both commit in order', async () => {
    const { result, onCommit, onTranscript } = setup()
    // Hold 1 → release → batching.
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    expect(h.state.batchCalls).toHaveLength(1)

    // Hold 2 starts while hold 1 is still transcribing.
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(result.current.recording).toBe(true)
    expect(h.state.batchCalls[0].signal.aborted).toBe(false) // not cannibalized

    const transcriptCallsBefore = onTranscript.mock.calls.length
    await act(async () => {
      h.state.batchCalls[0].resolve('first hold text')
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onCommit).toHaveBeenCalledWith('first hold text')
    // The background commit must NOT clear the new hold's live draft.
    expect(onTranscript.mock.calls.length).toBe(transcriptCallsBefore)

    // Hold 2 finishes normally through batch.
    releaseSpace()
    await advance(0)
    await act(async () => {
      h.state.batchCalls[1].resolve('second hold text')
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(onCommit.mock.calls.map((c) => c[0])).toEqual(['first hold text', 'second hold text'])
  })
})

describe('cancel', () => {
  it('Esc mid-hold discards: mic disposed, stream stopped, zero network, no commit', async () => {
    const { result, onCommit, onCaptureEnd } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    act(() => result.current.cancel())
    await advance(1000)
    expect(h.state.captures[0].dispose).toHaveBeenCalled()
    expect(h.state.streams[0].stop).toHaveBeenCalled()
    expect(h.batchTranscribe).not.toHaveBeenCalled()
    expect(onCommit).not.toHaveBeenCalled()
    expect(onCaptureEnd).not.toHaveBeenCalled()
    expect(result.current.recording).toBe(false)
  })

  it('cancel while batching aborts the POST', async () => {
    const { result } = setup()
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    expect(h.state.batchCalls).toHaveLength(1)
    act(() => result.current.cancel())
    expect(h.state.batchCalls[0].signal.aborted).toBe(true)
    expect(result.current.transcribing).toBe(false)
  })
})
