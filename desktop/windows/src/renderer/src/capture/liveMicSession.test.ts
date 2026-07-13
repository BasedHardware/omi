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

vi.mock('../lib/transcriptionClient', () => ({
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
}))

vi.mock('../lib/liveConversation', () => ({
  isConversationBoundary: () => false,
  onFinalizeRequest: () => () => {}
}))

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

import { startLiveMicSession, isLiveMicSessionActive } from './liveMicSession'
import { MAX_RECONNECT_ATTEMPTS } from './liveRescue'

const insertLocalConversation = vi.fn(async (_row: unknown) => {})
const notifyConversationsChanged = vi.fn()

/** The callbacks the most recent (re)connect registered. */
function latest(): Call {
  return calls[calls.length - 1]
}

beforeEach(() => {
  vi.useFakeTimers()
  calls.length = 0
  storeSegments.length = 0
  stop.mockClear()
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
    await vi.advanceTimersByTimeAsync(0)
    ctrl.stop()
    expect(isLiveMicSessionActive()).toBe(false)
    ctrl.stop() // idempotent — must not drive the count negative
    expect(isLiveMicSessionActive()).toBe(false)
  })
})
