import { describe, it, expect, vi } from 'vitest'

// The module imports the transitive apiClient/audio graph — stub the heavy
// bits so the pure mapping is testable in node.
vi.mock('../apiClient', () => ({ desktopApi: { post: vi.fn() } }))
vi.mock('../audio', () => ({ acquireMicStream: vi.fn() }))

import { speakingEdgeForTransportEvent } from './openaiSession'

describe('speakingEdgeForTransportEvent (WebRTC echo-gate wiring)', () => {
  it('maps the WebRTC playout-buffer lifecycle to gate edges', () => {
    expect(speakingEdgeForTransportEvent('output_audio_buffer.started')).toBe('start')
    expect(speakingEdgeForTransportEvent('output_audio_buffer.stopped')).toBe('end')
    expect(speakingEdgeForTransportEvent('output_audio_buffer.cleared')).toBe('end')
  })

  it('REGRESSION: never keys the gate off WS-transport-only audio events', () => {
    // Shipped bug (caught by the live loop-check): the gate listened to the
    // session's 'audio_start'/'audio_stopped', which derive from transport
    // 'audio' CHUNK events that only the WebSocket transport emits — over
    // WebRTC the gate never engaged. The raw server events behind those
    // session events must NOT be treated as playout edges here either
    // (response.output_audio.done is GENERATION done, not playout drained).
    expect(speakingEdgeForTransportEvent('response.output_audio.delta')).toBe(null)
    expect(speakingEdgeForTransportEvent('response.output_audio.done')).toBe(null)
    expect(speakingEdgeForTransportEvent('response.done')).toBe(null)
    expect(speakingEdgeForTransportEvent('session.updated')).toBe(null)
  })
})
