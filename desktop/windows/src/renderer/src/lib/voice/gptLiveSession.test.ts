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

import {
  createGptLiveMessageHandler,
  gptLiveSessionStartFrame,
  startGptLiveSession
} from './gptLiveSession'
import { acquireMicStream } from '../audio'

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

describe('startGptLiveSession — stop flush', () => {
  class FakeWebSocket {
    static OPEN = 1
    static instances: FakeWebSocket[] = []
    readyState = FakeWebSocket.OPEN
    sent: string[] = []
    onopen: (() => void) | null = null
    onmessage: ((e: { data: string }) => void) | null = null
    onerror: (() => void) | null = null
    onclose: ((e: { code: number; reason: string }) => void) | null = null
    constructor(
      public url: string,
      public protocols?: string[]
    ) {
      FakeWebSocket.instances.push(this)
    }
    send(d: string): void {
      this.sent.push(d)
    }
    close(): void {
      this.onclose?.({ code: 1000, reason: '' })
    }
    emit(o: object): void {
      this.onmessage?.({ data: JSON.stringify(o) })
    }
  }

  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.mocked(acquireMicStream).mockResolvedValue({ getTracks: () => [] } as never)
  })

  it('authenticates in the first message and starts the session after auth_response', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({ token: 'omi-token', instructions: 'INSTR', cb })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    expect(ws.url).toContain('/v1/omni/relay')
    expect(ws.url).not.toContain('token')
    ws.onopen!()
    expect(ws.sent).toHaveLength(1)
    expect(JSON.parse(ws.sent[0]!)).toEqual({ type: 'auth', token: 'omi-token' })

    ws.emit({ type: 'auth_response', success: true })
    const start = JSON.parse(ws.sent[1]!)
    expect(start.type).toBe('session.start')
    expect(start.session.model).toBe('gpt-live-1')

    ws.emit({ type: 'session.started' })
    const handle = await promise
    expect(cb.onConnected).toHaveBeenCalledTimes(1)
    handle.stop()
  })

  it('flushes the accumulated assistant reply before marking the session stopped', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({ token: 'tok', instructions: 'INSTR', cb })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    ws.onopen!()
    ws.emit({ type: 'auth_response', success: true })
    ws.emit({ type: 'session.started' })
    const handle = await promise

    ws.emit({ type: 'session.output_transcript.delta', delta: 'Pending reply' })
    handle.stop()

    expect(cb.onUtterance).toHaveBeenCalledWith('gpt-live-turn-0', 'Pending reply')
  })

  it('BYOK connects direct with the key subprotocol and sends no auth frame', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({ token: 'sk-user', byok: true, instructions: 'INSTR', cb })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    expect(ws.url).toBe('wss://api.openai.com/v1/live/sessions')
    expect(ws.protocols).toEqual(['openai-insecure-api-key.sk-user'])
    ws.onopen!()
    expect(JSON.parse(ws.sent[0]!).type).toBe('session.start')
    ws.emit({ type: 'session.started' })
    const handle = await promise
    handle.stop()
  })

  it('rejects the start when an error frame arrives before the handshake', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({ token: 'omi-token', instructions: 'INSTR', cb })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    ws.onopen!()
    ws.emit({ type: 'auth_response', success: true })
    ws.emit({ type: 'error', message: 'relay refused' })

    await expect(promise).rejects.toThrow('relay refused')
    // The controller learns about the failure from the throw, not a double fatal.
    expect(cb.onFatal).not.toHaveBeenCalled()
  })

  it('finalizes a server session.closed without reporting a fatal error', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({ token: 'omi-token', instructions: 'INSTR', cb })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    ws.onopen!()
    ws.emit({ type: 'auth_response', success: true })
    ws.emit({ type: 'session.started' })
    const handle = await promise

    ws.emit({ type: 'session.closed', usage: {} })
    expect(cb.onFatal).not.toHaveBeenCalled()
    handle.stop()
  })

  it('rejects if the provider never signals session.started', async () => {
    const cb = makeCb()
    const promise = startGptLiveSession({
      token: 'omi-token',
      instructions: 'INSTR',
      cb,
      connectTimeoutMs: 10
    })
    await new Promise((r) => setTimeout(r, 0))
    const ws = FakeWebSocket.instances[0]!
    ws.onopen!()
    ws.emit({ type: 'auth_response', success: true })

    await expect(promise).rejects.toThrow(/timed out/i)
  })
})
