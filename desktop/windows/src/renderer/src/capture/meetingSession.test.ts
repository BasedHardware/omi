import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock the transcription client so no real WS/audio is touched.
const stops: Record<'mic' | 'system', ReturnType<typeof vi.fn>> = {
  mic: vi.fn(),
  system: vi.fn()
}
type LaneCb = { onLine: (l: { id: string; text: string; speaker?: string }) => void }
const laneCbs: Partial<Record<'mic' | 'system', LaneCb>> = {}
let systemShouldFail = false

vi.mock('../lib/transcriptionClient', () => ({
  startTranscription: vi.fn(async (source: 'mic' | 'system', cb: LaneCb) => {
    laneCbs[source] = cb
    if (source === 'system' && systemShouldFail) throw new Error('loopback unavailable')
    return { stop: stops[source] }
  })
}))

import { startMeetingSession, formatMeetingTranscript } from './meetingSession'

const insertLocalConversation = vi.fn(
  async (c: { transcript: string }): Promise<void> => void c
)
const notifyConversationsChanged = vi.fn()

beforeEach(() => {
  stops.mic.mockClear()
  stops.system.mockClear()
  laneCbs.mic = undefined
  laneCbs.system = undefined
  systemShouldFail = false
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
    // orphaned (the C1 regression: Promise.all left it running).
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
