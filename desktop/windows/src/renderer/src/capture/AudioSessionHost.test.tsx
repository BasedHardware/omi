// @vitest-environment jsdom
import { act, cleanup, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { CaptureCommand, CaptureEvent } from '../../../shared/types'
import type { PipelineSetupResult } from '../lib/capture/pipelineHandle'

const h = vi.hoisted(() => ({
  commandHandler: null as null | ((command: CaptureCommand, ownerId: number) => void),
  pipelineReady: Promise.resolve({ ok: true } as PipelineSetupResult),
  pipelineStop: vi.fn(),
  gateStop: vi.fn(),
  trackStop: vi.fn(),
  captureEmit: vi.fn()
}))

vi.mock('../lib/audio', () => ({
  acquireMicStream: async () => ({ getTracks: () => [{ stop: h.trackStop }] })
}))
vi.mock('../lib/capture/systemAudio', () => ({
  getSystemAudioStream: async () => ({ getTracks: () => [{ stop: h.trackStop }] })
}))
vi.mock('../lib/capture/captureEngine', () => ({
  createPcmPipeline: () => ({ stop: h.pipelineStop, ready: h.pipelineReady }),
  createVadGate: () => ({ push: vi.fn(), stop: h.gateStop })
}))
vi.mock('../lib/capture/loopbackMusicFilter', () => ({
  createLoopbackMusicFilter: () => ({ push: vi.fn(), stop: vi.fn(), verdict: vi.fn() })
}))
vi.mock('../lib/preferences', () => ({ getPreferences: () => ({ vadGateEnabled: true }) }))
vi.mock('./assistantGate', () => ({
  assistantGate: { setSpeaking: vi.fn() },
  wrapFeed: (feed: unknown) => feed
}))
vi.mock('../lib/capture/vadGate', () => ({ resolveVadGateMode: () => 'gated' }))

import { AudioSessionHost } from './AudioSessionHost'

beforeEach(() => {
  h.commandHandler = null
  h.pipelineReady = Promise.resolve({ ok: true })
  h.pipelineStop.mockReset()
  h.gateStop.mockReset()
  h.trackStop.mockReset()
  h.captureEmit.mockReset()
  Object.defineProperty(window, 'omi', {
    configurable: true,
    value: {
      listenFeed: vi.fn(),
      captureEmit: h.captureEmit,
      onCaptureCommand: (handler: (command: CaptureCommand, ownerId: number) => void) => {
        h.commandHandler = handler
        return () => {
          h.commandHandler = null
        }
      }
    }
  })
})

afterEach(() => {
  cleanup()
})

describe('AudioSessionHost readiness', () => {
  it('emits ready only after the PCM pipeline setup resolves', async () => {
    let resolveSetup!: (result: PipelineSetupResult) => void
    h.pipelineReady = new Promise((resolve) => {
      resolveSetup = resolve
    })
    render(<AudioSessionHost />)

    act(() => {
      h.commandHandler?.({ type: 'audio-start', sessionId: 'delayed', source: 'mic' }, 42)
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(h.captureEmit).not.toHaveBeenCalled()

    await act(async () => {
      resolveSetup({ ok: true })
      await h.pipelineReady
    })
    expect(h.captureEmit).toHaveBeenCalledWith(
      { type: 'audio-source-ready', sessionId: 'delayed' },
      42
    )

    act(() => {
      h.commandHandler?.({ type: 'audio-stop', sessionId: 'delayed' }, 42)
    })
  })

  it('reports pipeline setup failure without claiming the source is ready', async () => {
    h.pipelineReady = Promise.resolve({ ok: false, error: new Error('audio graph failed') })
    render(<AudioSessionHost />)

    act(() => {
      h.commandHandler?.({ type: 'audio-start', sessionId: 'failed', source: 'mic' }, 7)
    })
    await act(async () => {
      await h.pipelineReady
    })

    const events = h.captureEmit.mock.calls.map(([event]) => event as CaptureEvent)
    expect(events).toContainEqual({
      type: 'audio-source-error',
      sessionId: 'failed',
      name: 'Error',
      message: 'audio graph failed'
    })
    expect(events.some((event) => event.type === 'audio-source-ready')).toBe(false)
    expect(h.pipelineStop).toHaveBeenCalledOnce()
  })
})
