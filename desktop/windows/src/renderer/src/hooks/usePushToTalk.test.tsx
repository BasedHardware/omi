// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, cleanup } from '@testing-library/react'
import {
  HOLD_THRESHOLD_MS,
  STREAM_FINALIZE_DEADLINE_MS,
  ERROR_STRIP_MS
} from '../lib/ptt/constants'

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
    captures: [] as Array<{
      analyser: object
      drain: ReturnType<typeof vi.fn>
      dispose: ReturnType<typeof vi.fn>
    }>,
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
        new Promise<string>((resolve, reject) =>
          state.batchCalls.push({ pcm, signal, resolve, reject })
        )
    ),
    rebuildPttMic: vi.fn(),
    trackEvent: vi.fn()
  }
})

vi.mock('../lib/ptt/capture', () => ({
  startPttCapture: h.startPttCapture,
  warmPttMic: vi.fn(async () => {}),
  releasePttMic: vi.fn(),
  rebuildPttMic: h.rebuildPttMic
}))
// deadMicPolicy → analytics: assert the silent_mic fallback events without a fetch.
vi.mock('../lib/analytics', () => ({ trackEvent: h.trackEvent }))
vi.mock('../lib/ptt/transport', () => ({
  startPttStream: h.startPttStream,
  batchTranscribe: h.batchTranscribe,
  batchErrorMessage: () => 'friendly error',
  prefetchAuthToken: vi.fn()
}))

import { usePushToTalk } from './usePushToTalk'

const VOICED_1S = new Int16Array(16000).fill(8000) // 1s, fully voiced → gate ok
const SHORT_200MS = new Int16Array(3200).fill(8000) // 0.2s → too-short

function setup(extra: Partial<Parameters<typeof usePushToTalk>[0]> = {}): {
  result: { current: ReturnType<typeof usePushToTalk> }
  onCommit: ReturnType<typeof vi.fn>
  onTranscript: ReturnType<typeof vi.fn>
  onCaptureEnd: ReturnType<typeof vi.fn>
  onHoldStart: ReturnType<typeof vi.fn>
} {
  const onCommit = vi.fn()
  const onTranscript = vi.fn()
  const onCaptureEnd = vi.fn()
  const onHoldStart = vi.fn()
  const { result } = renderHook(() =>
    usePushToTalk({
      onCommit,
      onTranscript,
      onCaptureEnd,
      onHoldStart,
      restoreDraft: vi.fn(),
      getDraft: () => '',
      ...extra
    })
  )
  return { result, onCommit, onTranscript, onCaptureEnd, onHoldStart }
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

  it('fires onHoldStart (barge-in) at hold-start, but never for a quick tap', async () => {
    const { onHoldStart } = setup()
    // A quick tap (threshold not crossed) must not interrupt a playing reply.
    pressSpace()
    await advance(HOLD_THRESHOLD_MS - 100)
    releaseSpace()
    expect(onHoldStart).not.toHaveBeenCalled()
    // A real hold fires it exactly once as capture begins.
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(onHoldStart).toHaveBeenCalledTimes(1)
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

describe('pre-capture usage veto (macOS isBlockedByUsageLimit)', () => {
  it('OVER LIMIT: a hold is refused before the mic opens — no capture, no STT, popup raised once', async () => {
    const checkUsageLimit = vi.fn(() => ({ blocked: true, message: 'over the cap' }))
    const onUsageLimitBlocked = vi.fn()
    const { result, onHoldStart, onCommit } = setup({ checkUsageLimit, onUsageLimitBlocked })
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    // The gesture never opened the mic or the stream — the whole record→STT round
    // trip is skipped.
    expect(h.startPttCapture).not.toHaveBeenCalled()
    expect(h.startPttStream).not.toHaveBeenCalled()
    expect(result.current.recording).toBe(false)
    // Popup raised exactly once, with the limit line; barge-in suppressed (a
    // blocked hold must not cut off a playing reply); nothing is ever committed.
    expect(onUsageLimitBlocked).toHaveBeenCalledTimes(1)
    expect(onUsageLimitBlocked).toHaveBeenCalledWith('over the cap')
    expect(onHoldStart).not.toHaveBeenCalled()
    // Release does nothing — there was no hold to finalize (no second popup at send).
    releaseSpace()
    await advance(1000)
    expect(onCommit).not.toHaveBeenCalled()
    expect(onUsageLimitBlocked).toHaveBeenCalledTimes(1)
  })

  it('IN LIMIT: the veto lets the hold through unchanged — no regression, no added await', async () => {
    const checkUsageLimit = vi.fn(() => ({ blocked: false as const }))
    const onUsageLimitBlocked = vi.fn()
    const { result, onHoldStart } = setup({ checkUsageLimit, onUsageLimitBlocked })
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(result.current.recording).toBe(true)
    expect(h.startPttCapture).toHaveBeenCalledOnce()
    expect(onHoldStart).toHaveBeenCalledTimes(1)
    expect(onUsageLimitBlocked).not.toHaveBeenCalled()
  })

  it('COLD START (no snapshot ⇒ verdict not blocked): fails open, the user can speak', async () => {
    // The gate's checkSync returns { blocked:false } when it has no snapshot yet;
    // the hold must proceed rather than be refused on a probe that hasn't landed.
    const checkUsageLimit = vi.fn(() => ({ blocked: false as const }))
    const { result } = setup({ checkUsageLimit })
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    expect(result.current.recording).toBe(true)
    expect(h.startPttCapture).toHaveBeenCalledOnce()
  })

  it('a quick TAP is never vetoed — the veto only runs when a real hold begins', async () => {
    // A tap types a space; it must not consult the quota or raise the popup.
    const checkUsageLimit = vi.fn(() => ({ blocked: true, message: 'over the cap' }))
    const onUsageLimitBlocked = vi.fn()
    setup({ checkUsageLimit, onUsageLimitBlocked })
    pressSpace()
    await advance(HOLD_THRESHOLD_MS - 100)
    releaseSpace()
    await advance(1000)
    expect(checkUsageLimit).not.toHaveBeenCalled()
    expect(onUsageLimitBlocked).not.toHaveBeenCalled()
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

describe('silent-mic escalation (A7b)', () => {
  // Zeros, 1s: totalSec 1 ≥ 0.35, no voiced frames, peak 0 < DEAD_MIC_PEAK → dead-mic.
  const DEAD_1S = new Int16Array(16000)
  const BASE_HINT = 'Mic heard nothing — check your input device in Windows sound settings'
  const ESCALATED_HINT = 'Mic still silent — check your microphone, or restart Omi'

  // A completed dead-mic hold (release → drain → gate 'dead-mic' → terminal).
  const deadHold = async (result: { current: ReturnType<typeof usePushToTalk> }): Promise<void> => {
    h.state.drainBuffer = DEAD_1S
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    void result // keep the signature parallel to goodHold
  }

  // A completed good hold: gate 'ok' → batch → resolve → commit (resets the counter).
  const goodHold = async (): Promise<void> => {
    h.state.drainBuffer = VOICED_1S
    pressSpace()
    await advance(HOLD_THRESHOLD_MS)
    releaseSpace()
    await advance(0)
    await act(async () => {
      h.state.batchCalls[h.state.batchCalls.length - 1].resolve('hello')
      await vi.advanceTimersByTimeAsync(0)
    })
  }

  it('turn 1 hints only; turn 2 rebuilds + degraded; turn 3 escalates + exhausted', async () => {
    const { result } = setup()

    await deadHold(result) // 1
    expect(result.current.hint).toBe(BASE_HINT)
    expect(h.rebuildPttMic).not.toHaveBeenCalled()
    expect(h.trackEvent).not.toHaveBeenCalled()

    await deadHold(result) // 2 → rebuild
    expect(h.rebuildPttMic).toHaveBeenCalledTimes(1)
    expect(h.trackEvent).toHaveBeenLastCalledWith('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'rebuilt',
      reason: 'local_heal',
      outcome: 'degraded'
    })
    expect(result.current.hint).toBe(BASE_HINT)

    await deadHold(result) // 3 → escalate
    expect(h.rebuildPttMic).toHaveBeenCalledTimes(1) // no second rebuild
    expect(h.trackEvent).toHaveBeenLastCalledWith('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'none',
      reason: 'local_heal',
      outcome: 'exhausted'
    })
    expect(result.current.hint).toBe(ESCALATED_HINT)
  })

  it('a good turn resets the counter', async () => {
    const { result } = setup()
    await deadHold(result) // 1
    await deadHold(result) // 2 → rebuild
    expect(h.rebuildPttMic).toHaveBeenCalledTimes(1)

    await goodHold() // resets

    h.rebuildPttMic.mockClear()
    h.trackEvent.mockClear()
    await deadHold(result) // back to turn 1 — base hint, no rebuild
    expect(result.current.hint).toBe(BASE_HINT)
    expect(h.rebuildPttMic).not.toHaveBeenCalled()
    expect(h.trackEvent).not.toHaveBeenCalled()
  })
})
