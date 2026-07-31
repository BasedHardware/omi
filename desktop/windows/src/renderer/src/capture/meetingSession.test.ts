import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the transcription client so no real WS/audio is touched.
const stops: Record<'mic' | 'system', ReturnType<typeof vi.fn>> = {
  mic: vi.fn(),
  system: vi.fn()
}
type LaneCb = { onLine: (l: { id: string; text: string; speaker?: string }) => void }
const laneCbs: Partial<Record<'mic' | 'system', LaneCb>> = {}
const laneModes: Partial<Record<'mic' | 'system', string>> = {}
let systemShouldFail = false

vi.mock('../lib/transcriptionClient', () => ({
  startTranscription: vi.fn(async (source: 'mic' | 'system', cb: LaneCb, mode?: string) => {
    laneCbs[source] = cb
    laneModes[source] = mode
    if (source === 'system' && systemShouldFail) throw new Error('loopback unavailable')
    return { stop: stops[source], finalize: vi.fn() }
  })
}))

// The meeting session defers its mic lane only to a healthy continuous mic (C6).
const live = vi.hoisted(() => ({
  health: 'inactive' as 'inactive' | 'connecting' | 'ready' | 'failed',
  waitForReady: vi.fn(async () => true),
  listeners: [] as Array<(health: 'inactive' | 'connecting' | 'ready' | 'failed') => void>
}))
vi.mock('./liveMicSession', () => ({
  getLiveMicSessionHealth: () => live.health,
  waitForLiveMicSessionReady: live.waitForReady,
  onLiveMicSessionHealth: (
    listener: (health: 'inactive' | 'connecting' | 'ready' | 'failed') => void
  ) => {
    live.listeners.push(listener)
    listener(live.health)
    return () => {
      live.listeners = live.listeners.filter((candidate) => candidate !== listener)
    }
  }
}))

import { startMeetingSession, formatMeetingTranscript } from './meetingSession'

const insertLocalConversation = vi.fn(async (c: { transcript: string }): Promise<void> => void c)
const notifyConversationsChanged = vi.fn()

beforeEach(() => {
  stops.mic.mockClear()
  stops.system.mockClear()
  laneCbs.mic = undefined
  laneCbs.system = undefined
  laneModes.mic = undefined
  laneModes.system = undefined
  systemShouldFail = false
  live.health = 'inactive'
  live.waitForReady.mockReset()
  live.waitForReady.mockImplementation(async () => {
    live.health = 'ready'
    return true
  })
  live.listeners = []
  insertLocalConversation.mockClear()
  notifyConversationsChanged.mockClear()
  // meetingSession reads window.omi.* and the global crypto.randomUUID.
  vi.stubGlobal('window', { omi: { insertLocalConversation, notifyConversationsChanged } })
  if (!globalThis.crypto?.randomUUID) {
    vi.stubGlobal('crypto', { randomUUID: () => '00000000-0000-0000-0000-000000000000' })
  }
})

describe('formatMeetingTranscript', () => {
  it('renders the system (remote) lane only — mic is backend-owned', () => {
    expect(
      formatMeetingTranscript([
        { id: '1', speaker: 'Speaker 1', text: 'hi' },
        { id: '2', text: 'there' }
      ])
    ).toBe('Speaker 1: hi\nthere')
    expect(formatMeetingTranscript([])).toBe('')
  })
})

describe('startMeetingSession', () => {
  it('saves only the system-lane transcript on stop (no mic duplication)', async () => {
    const session = await startMeetingSession({ appName: 'Zoom', onError: vi.fn() })
    laneCbs.mic?.onLine({ id: 'm', text: 'my own voice' })
    laneCbs.system?.onLine({ id: 's', speaker: 'Alex', text: 'remote side' })
    await session.stop()
    expect(insertLocalConversation).toHaveBeenCalledOnce()
    const saved = insertLocalConversation.mock.calls[0][0]
    expect(saved.transcript).toContain('Meeting (Zoom)')
    expect(saved.transcript).toContain('Alex: remote side')
    expect(saved.transcript).not.toContain('my own voice') // mic not double-saved
    expect(notifyConversationsChanged).toHaveBeenCalledOnce()
  })

  it('wires the local-only system lane transcription-only and the mic lane backend-owned', () => {
    return startMeetingSession({ appName: 'Zoom', onError: vi.fn() }).then(() => {
      // System is saved locally → must NOT create a server-side /v4/listen
      // conversation (would race the mic conversation on the per-uid pointer).
      expect(laneModes.system).toBe('transcribe')
      // Mic is backend-owned when the meeting opens it.
      expect(laneModes.mic).toBe('conversation')
    })
  })

  it('does NOT open a second mic lane when a continuous mic session is already active (C6)', async () => {
    live.health = 'ready'
    const session = await startMeetingSession({ appName: 'Zoom', onError: vi.fn() })
    // Only the system lane runs; the mic is left to the continuous session so no
    // duplicate /v4/listen mic socket is opened for the same audio.
    expect(laneCbs.mic).toBeUndefined()
    expect(laneCbs.system).toBeDefined()
    // The system transcript still saves locally.
    laneCbs.system?.onLine({ id: 's', speaker: 'Alex', text: 'remote side' })
    await session.stop()
    expect(stops.mic).not.toHaveBeenCalled()
    expect(stops.system).toHaveBeenCalledOnce()
    expect(insertLocalConversation).toHaveBeenCalledOnce()
  })

  it('includes a connecting continuous mic in the startup readiness barrier', async () => {
    live.health = 'connecting'
    const session = await startMeetingSession({ appName: 'Zoom', onError: vi.fn() })

    expect(live.waitForReady).toHaveBeenCalledOnce()
    expect(laneCbs.mic).toBeUndefined()
    await session.stop()
  })

  it('reports a delegated continuous mic that fails after startup', async () => {
    live.health = 'ready'
    const onError = vi.fn()
    const session = await startMeetingSession({ appName: 'Zoom', onError })

    live.health = 'failed'
    for (const listener of live.listeners) listener(live.health)

    expect(onError).toHaveBeenCalledWith('microphone: continuous transcription stopped')
    await session.stop()
    expect(live.listeners).toHaveLength(0)
  })

  it('fails startup and stops system audio when the delegated mic never becomes ready', async () => {
    live.health = 'connecting'
    live.waitForReady.mockResolvedValue(false)

    await expect(startMeetingSession({ appName: 'Zoom', onError: vi.fn() })).rejects.toThrow(
      'continuous microphone transcription did not become ready'
    )
    expect(stops.system).toHaveBeenCalledOnce()
    expect(laneCbs.mic).toBeUndefined()
  })

  it('skips the save when the system lane produced nothing', async () => {
    const session = await startMeetingSession({ appName: 'Teams', onError: vi.fn() })
    laneCbs.mic?.onLine({ id: 'm', text: 'only mic spoke' })
    await session.stop()
    expect(insertLocalConversation).not.toHaveBeenCalled()
  })

  it('tears down the ALREADY-STARTED sibling lane when the other lane fails (no hot-mic leak)', async () => {
    systemShouldFail = true
    await expect(startMeetingSession({ appName: 'Zoom', onError: vi.fn() })).rejects.toThrow(
      'loopback unavailable'
    )
    // The mic lane resolved before system rejected — it MUST be stopped, not
    // orphaned (the regression: Promise.all left it running).
    expect(stops.mic).toHaveBeenCalledOnce()
  })

  it('is idempotent on repeated stop()', async () => {
    const session = await startMeetingSession({ appName: 'Zoom', onError: vi.fn() })
    laneCbs.system?.onLine({ id: 's', text: 'x' })
    await session.stop()
    await session.stop()
    expect(stops.mic).toHaveBeenCalledOnce()
    expect(stops.system).toHaveBeenCalledOnce()
    expect(insertLocalConversation).toHaveBeenCalledOnce()
  })
})
