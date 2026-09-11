import { describe, it, expect, vi, beforeEach } from 'vitest'
import type { VoicePlayer } from './pcmPlayer'
import type { ProviderSessionCallbacks } from './providerSession'

// gptLiveSession transitively pulls the AudioWorklet/mic graph. Stub the heavy
// bits so the pure message-handler logic is testable in the node env —
// base64ToBytes stays a real passthrough so enqueued payloads are assertable.
vi.mock('../audio', () => ({ acquireMicStream: vi.fn() }))
vi.mock('../capture/pipelineHandle', () => ({ makePipelineHandle: vi.fn() }))
vi.mock('../capture/pcmPipeline', () => ({ createPcmPipeline: vi.fn() }))
vi.mock('./pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  int16ToBase64: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

import { createGptLiveMessageHandler, gptLiveSessionStartFrame } from './gptLiveSession'

function makePlayer(): VoicePlayer & Record<string, ReturnType<typeof vi.fn>> {
  return {
    enqueuePcm16: vi.fn(),
    flush: vi.fn(),
    clear: vi.fn(),
    setSinkId: vi.fn(),
    close: vi.fn()
  } as VoicePlayer & Record<string, ReturnType<typeof vi.fn>>
}

function makeCb(): ProviderSessionCallbacks {
  return {
    onConnected: vi.fn(),
    onFatal: vi.fn(),
    onSpeakingStart: vi.fn(),
    onSpeakingEnd: vi.fn(),
    onUtterance: vi.fn(),
    onUsage: vi.fn()
  }
}

describe('gptLiveSessionStartFrame', () => {
  it('builds the session.start frame with the gpt-live-1 model + 24k PCM', () => {
    const frame = gptLiveSessionStartFrame('INSTR') as {
      type: string
      event_id: string
      session: Record<string, unknown>
    }
    expect(frame.type).toBe('session.start')
    expect(typeof frame.event_id).toBe('string')
    expect(frame.session.model).toBe('gpt-live-1')
    expect(frame.session.instructions).toBe('INSTR')
    expect(frame.session.audio).toEqual({
      format: { type: 'audio/pcm', rate: 24000 },
      output: { voice: 'marin' }
    })
  })
})

describe('createGptLiveMessageHandler', () => {
  let player: ReturnType<typeof makePlayer>
  let cb: ProviderSessionCallbacks
  let handler: ReturnType<typeof createGptLiveMessageHandler>
  let started: number

  beforeEach(() => {
    player = makePlayer()
    cb = makeCb()
    started = 0
    handler = createGptLiveMessageHandler({
      isStopped: () => false,
      getPlayer: () => player,
      cb,
      onStarted: () => {
        started += 1
      }
    })
  })

  it('plays output audio deltas and signals ready on session.started', () => {
    handler.handle(JSON.stringify({ type: 'session.started', session: { id: 'x' } }))
    expect(started).toBe(1)
    handler.handle(JSON.stringify({ type: 'session.output_audio.delta', delta: 'AAE=' }))
    expect(player.enqueuePcm16).toHaveBeenCalledTimes(1)
  })

  it('accumulates assistant transcript deltas and flushes one source utterance', () => {
    handler.handle(JSON.stringify({ type: 'session.output_transcript.delta', delta: 'Hello ' }))
    handler.handle(JSON.stringify({ type: 'session.output_transcript.delta', delta: 'there' }))
    handler.flush()
    expect(cb.onUtterance).toHaveBeenCalledExactlyOnceWith('gpt-live-turn-0', 'Hello there')
    // A second flush with nothing accumulated emits nothing.
    handler.flush()
    expect(cb.onUtterance).toHaveBeenCalledTimes(1)
  })

  it('interrupt clears playback and drops the partial reply', () => {
    handler.handle(JSON.stringify({ type: 'session.output_transcript.delta', delta: 'Half' }))
    handler.handle(JSON.stringify({ type: 'session.interrupted' }))
    expect(player.clear).toHaveBeenCalledTimes(1)
    handler.flush()
    expect(cb.onUtterance).not.toHaveBeenCalled()
  })

  it('session.closed maps usage and flushes the reply', () => {
    handler.handle(JSON.stringify({ type: 'session.output_transcript.delta', delta: 'Done' }))
    handler.handle(
      JSON.stringify({
        type: 'session.closed',
        usage: { input_tokens: 3, output_tokens: 2 }
      })
    )
    expect(cb.onUsage).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: 'gpt_live',
        model: 'gpt-live-1',
        input_text_tokens: 3,
        output_text_tokens: 2
      })
    )
    expect(cb.onUtterance).toHaveBeenCalledWith('gpt-live-turn-0', 'Done')
  })

  it('an error frame is fatal', () => {
    handler.handle(JSON.stringify({ type: 'error', message: 'boom' }))
    expect(cb.onFatal).toHaveBeenCalledWith('boom', true)
  })

  it('ignores messages once the session is stopped', () => {
    let stopped = false
    const h = createGptLiveMessageHandler({
      isStopped: () => stopped,
      getPlayer: () => player,
      cb
    })
    stopped = true
    h.handle(JSON.stringify({ type: 'session.output_audio.delta', delta: 'AAE=' }))
    expect(player.enqueuePcm16).not.toHaveBeenCalled()
  })
})
