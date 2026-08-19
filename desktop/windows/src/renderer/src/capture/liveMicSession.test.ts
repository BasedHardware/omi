import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { TranscriptionCallbacks } from '../lib/transcriptionClient'

// ── Mocks ─────────────────────────────────────────────────────────────────────
// Capture every startTranscription call so the test can drive its callbacks and
// assert the mode + clientConversationId passed on each (re)connect.
type Call = {
  source: string
  cb: TranscriptionCallbacks
  mode?: string
  clientConversationId?: string
}
const calls: Call[] = []
const stop = vi.fn()
const finalizeHandle = vi.fn()
const trackEvent = vi.fn()

vi.mock('../lib/analytics', () => ({
  trackEvent: (...args: unknown[]) => trackEvent(...args)
}))

// Preserve the module's real exports (liveRescue's isRetryableDropError now
// calls the real isQuotaExhaustedMessage from this module) and mock only
// startTranscription.
vi.mock('../lib/transcriptionClient', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/transcriptionClient')>()
  return {
    ...actual,
    startTranscription: vi.fn(
      async (
        source: string,
        cb: TranscriptionCallbacks,
        mode?: string,
        clientConversationId?: string
      ) => {
        calls.push({ source, cb, mode, clientConversationId })
        return { stop, finalize: finalizeHandle }
      }
    )
  }
})

vi.mock('../lib/liveConversation', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../lib/liveConversation')>()
  return { ...actual, onFinalizeRequest: () => () => {} }
})

vi.mock('../lib/retentionRules', () => ({
  transcriptWordCount: (t: string) => (t.trim() ? t.trim().split(/\s+/).length : 0)
}))

vi.mock('../lib/voice/injectedTranscript', () => ({
  isInjectedLineId: () => false
}))

const storeSegments: { id?: string; speaker?: string; text: string }[] = []
vi.mock('./liveStore', () => ({
  captureLiveStore: {
    reset: vi.fn(() => {
      storeSegments.length = 0
    }),
    setStatus: vi.fn(),
    appendLine: vi.fn((l: { id?: string; speaker?: string; text: string }) =>
      storeSegments.push(l)
    ),
    saved: vi.fn(),
    getSegments: () => storeSegments
  }
}))

const syncLocalConversation = vi.fn(async (_row: unknown) => ({
  status: 'done',
  cloudId: 'c1',
  deduped: false
}))
vi.mock('../lib/sync/conversationSync', () => ({
  syncLocalConversation: (row: unknown) => syncLocalConversation(row)
}))

import {
  getLiveMicSessionHealth,
  isLiveMicSessionActive,
  startLiveMicSession,
  waitForLiveMicSessionReady
} from './liveMicSession'
import { MAX_RECONNECT_ATTEMPTS } from './liveRescue'

const insertLocalConversation = vi.fn(async (_row: unknown) => {})
const notifyConversationsChanged = vi.fn()

/** The callbacks the most recent (re)connect registered. */
function latest(): Call {
  return calls[calls.length - 1]
}

beforeEach(() => {
  vi.useFakeTimers()
  // Reconnect delay now carries decorrelating jitter (rand()*1s). Pin rand to 0 so
  // the delay equals the exact exponential base these timing assertions advance by.
  vi.spyOn(Math, 'random').mockReturnValue(0)
  calls.length = 0
  storeSegments.length = 0
  stop.mockClear()
  trackEvent.mockClear()
  syncLocalConversation.mockClear()
  insertLocalConversation.mockClear()
  notifyConversationsChanged.mockClear()
  vi.stubGlobal('window', { omi: { insertLocalConversation, notifyConversationsChanged } })
  if (!globalThis.crypto?.randomUUID) {
    let n = 0
    vi.stubGlobal('crypto', { randomUUID: () => `uuid-${n++}` })
  }
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('startLiveMicSession', () => {
  it('opens a conversation-mode /v4/listen session with a client_conversation_id', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0) // fire the deferred initial connect
    expect(calls).toHaveLength(1)
    expect(latest().source).toBe('mic')
    expect(latest().mode).toBe('conversation')
    expect(latest().clientConversationId).toBeTruthy()
    expect(trackEvent).toHaveBeenCalledWith('Transcription Started', {
      source: 'desktop_mic',
      provider: 'omi'
    })
    ctrl.stop()
  })

  it('emits exactly one successful terminal lifecycle for a backend boundary', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(5_000)

    latest().cb.onEvent?.({ type: 'memory_creating', raw: {} })

    const terminal = trackEvent.mock.calls.filter(([event]) => event === 'Transcription Ended')
    expect(terminal).toEqual([
      [
        'Transcription Ended',
        {
          source: 'desktop_mic',
          provider: 'omi',
          outcome: 'completed',
          duration_seconds: 5,
          retry_count: 0
        }
      ]
    ])
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Error')).toEqual([])
    ctrl.stop()
  })

  it('reconnects on a drop and RESUMES the same conversation id', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    const firstId = latest().clientConversationId
    // Prove it was live, then drop the socket.
    latest().cb.onBackend('omi')
    latest().cb.onError(new Error('socket dropped'))
    // Backoff for the 1st reconnect is 2s (min(2^1, 32)s).
    await vi.advanceTimersByTimeAsync(2000)
    expect(calls).toHaveLength(2)
    expect(latest().clientConversationId).toBe(firstId) // resume, not a new conversation
    ctrl.stop()
  })

  it('after exhausting reconnects, rescues the recording via a from-segments upload', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    // Capture enough speech that the rescue is worth uploading (≥ 5 words).
    latest().cb.onSegments?.([
      { id: 's1', text: 'this is a genuine long enough sentence', is_user: true, start: 0, end: 2 }
    ])
    // Drive drops until the reconnect budget is spent. Each onError schedules the
    // next attempt; advance past the (capped) backoff so the next connect fires.
    for (let i = 0; i < MAX_RECONNECT_ATTEMPTS; i++) {
      latest().cb.onError(new Error('outage'))
      await vi.advanceTimersByTimeAsync(32000)
    }
    // Budget spent — the next drop triggers the rescue instead of another reconnect.
    latest().cb.onError(new Error('outage'))
    await vi.advanceTimersByTimeAsync(0)

    expect(insertLocalConversation).toHaveBeenCalledOnce()
    const row = insertLocalConversation.mock.calls[0][0] as unknown as {
      syncState: string
      segments: { text: string }[]
      transcript: string
    }
    // Inserted 'unconfirmed' so the outbox dedupes against the cloud before posting
    // (never double-creates if the backend also finalized the pre-drop audio).
    expect(row.syncState).toBe('unconfirmed')
    expect(row.segments).toHaveLength(1)
    expect(row.transcript).toContain('genuine long enough sentence')
    expect(syncLocalConversation).toHaveBeenCalledOnce()
    ctrl.stop()
  })

  it('does NOT reconnect on a quota/entitlement error — surfaces it immediately', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    latest().cb.onError(
      new Error('Omi transcription stopped: free Omi transcription quota is used up (1008)')
    )
    // Give any (wrongly-scheduled) reconnect ample time to fire — none should.
    await vi.advanceTimersByTimeAsync(60_000)
    expect(calls).toHaveLength(1)
    expect(insertLocalConversation).not.toHaveBeenCalled()
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Error')).toEqual([
      [
        'Transcription Error',
        {
          source: 'desktop_mic',
          provider: 'omi',
          outcome: 'failed',
          error_class: 'quota',
          retry_count: 0
        }
      ]
    ])
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Ended')).toEqual([
      [
        'Transcription Ended',
        {
          source: 'desktop_mic',
          provider: 'omi',
          outcome: 'failed',
          duration_seconds: 0,
          retry_count: 0
        }
      ]
    ])
    // Repeated delivery of the same terminal callback must not duplicate either event.
    latest().cb.onError(new Error('Omi transcription stopped: quota is used up (1008)'))
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Error')).toHaveLength(
      1
    )
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Ended')).toHaveLength(
      1
    )
    ctrl.stop()
  })

  it('reports bounded retry exhaustion without exposing the raw error', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    for (let i = 0; i < MAX_RECONNECT_ATTEMPTS; i++) {
      latest().cb.onError(new Error('secret socket failure for customer@example.com'))
      await vi.advanceTimersByTimeAsync(32_000)
    }
    latest().cb.onError(new Error('secret socket failure for customer@example.com'))

    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Error')).toEqual([
      [
        'Transcription Error',
        {
          source: 'desktop_mic',
          provider: 'omi',
          outcome: 'failed',
          error_class: 'network',
          retry_count: MAX_RECONNECT_ATTEMPTS
        }
      ]
    ])
    expect(JSON.stringify(trackEvent.mock.calls)).not.toContain('customer@example.com')
    ctrl.stop()
  })

  it('does NOT rescue a trivial blip (< 5 words) on exhaustion', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    latest().cb.onSegments?.([{ id: 's1', text: 'hi there', is_user: true, start: 0, end: 1 }])
    for (let i = 0; i <= MAX_RECONNECT_ATTEMPTS; i++) {
      latest().cb.onError(new Error('outage'))
      await vi.advanceTimersByTimeAsync(32000)
    }
    expect(insertLocalConversation).not.toHaveBeenCalled()
    ctrl.stop()
  })

  it('reports active while running and clears on stop (C6 defer signal)', async () => {
    const ctrl = startLiveMicSession()
    expect(isLiveMicSessionActive()).toBe(true)
    expect(getLiveMicSessionHealth()).toBe('connecting')
    await vi.advanceTimersByTimeAsync(0)
    const ready = waitForLiveMicSessionReady()
    latest().cb.onBackend('omi')
    await expect(ready).resolves.toBe(true)
    expect(getLiveMicSessionHealth()).toBe('ready')
    ctrl.stop()
    expect(isLiveMicSessionActive()).toBe(false)
    expect(getLiveMicSessionHealth()).toBe('inactive')
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Ended')).toEqual([
      [
        'Transcription Ended',
        {
          source: 'desktop_mic',
          provider: 'omi',
          outcome: 'cancelled',
          duration_seconds: 0,
          retry_count: 0
        }
      ]
    ])
    ctrl.stop() // idempotent — must not drive the count negative
    expect(isLiveMicSessionActive()).toBe(false)
    expect(trackEvent.mock.calls.filter(([event]) => event === 'Transcription Ended')).toHaveLength(
      1
    )
  })

  it('reports terminal startup failure to delegated meeting readiness', async () => {
    const ctrl = startLiveMicSession()
    await vi.advanceTimersByTimeAsync(0)
    const ready = waitForLiveMicSessionReady()

    latest().cb.onError(new Error('Omi transcription unavailable (not signed in)'))

    await expect(ready).resolves.toBe(false)
    expect(getLiveMicSessionHealth()).toBe('failed')
    ctrl.stop()
  })
})
