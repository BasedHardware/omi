// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  failSource: 'system' as 'mic' | 'system',
  micStop: vi.fn(),
  systemStop: vi.fn(),
  startSession: vi.fn(),
  stopSession: vi.fn(() => null),
  startTranscription: vi.fn(),
  navigate: vi.fn()
}))

vi.mock('react-router-dom', () => ({ useNavigate: () => h.navigate }))
vi.mock('./useRecording', () => ({
  useRecording: () => ({
    state: 'idle',
    start: h.startSession,
    stop: h.stopSession
  })
}))
vi.mock('../lib/transcriptionClient', () => ({
  startTranscription: h.startTranscription
}))
vi.mock('../lib/pageCache', () => ({
  invalidateConversationsCache: vi.fn(),
  refreshCloudConversations: vi.fn()
}))
vi.mock('../lib/sync/segmentRetention', () => ({
  createSegmentStore: () => ({ add: vi.fn(), list: () => [] })
}))
vi.mock('../lib/sync/mergeLanes', () => ({ mergeLanes: () => [] }))
vi.mock('../lib/sync/outbox', () => ({ queueForSync: vi.fn() }))
vi.mock('../lib/sync/conversationSync', () => ({ syncLocalConversation: vi.fn() }))

import { useRecorder } from './useRecorder'

beforeEach(() => {
  h.failSource = 'system'
  h.micStop.mockReset()
  h.systemStop.mockReset()
  h.startSession.mockReset()
  h.stopSession.mockReset()
  h.stopSession.mockReturnValue(null)
  h.navigate.mockReset()
  h.startTranscription.mockReset()
  h.startTranscription.mockImplementation(async (source: 'mic' | 'system') => {
    if (source === h.failSource) throw new Error(`${source} unavailable`)
    return {
      stop: source === 'mic' ? h.micStop : h.systemStop,
      finalize: vi.fn()
    }
  })
  Object.defineProperty(window, 'omi', {
    configurable: true,
    value: {
      onCaptureEvent: () => () => {},
      captureCommand: vi.fn()
    }
  })
  vi.stubGlobal('alert', vi.fn())
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('useRecorder transactional lane startup', () => {
  it.each([
    ['system', 'mic'],
    ['mic', 'system']
  ] as const)('stops the %s sibling when the %s lane fails', async (healthy, failed) => {
    h.failSource = failed
    const { result } = renderHook(() => useRecorder())

    await act(async () => {
      await result.current.start({ system: true })
    })

    expect(healthy === 'mic' ? h.micStop : h.systemStop).toHaveBeenCalledOnce()
    expect(h.stopSession).toHaveBeenCalledOnce()
    expect(alert).toHaveBeenCalledWith(`Recording failed: ${failed} unavailable`)
  })
})
