import { describe, it, expect, vi } from 'vitest'
import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import type { HubSessionEvents, HubSocket, HubSocketFactory, HubClock } from './hubSession'

// pcmPlayer pulls the AudioWorklet `?worker&url` asset (unresolvable in node);
// stub it — base64ToBytes stays real so enqueued payloads are assertable.
vi.mock('../pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

import { GptLiveHubSession } from './gptLiveHubSession'

type Json = Record<string, unknown>

class FakeSocket implements HubSocket {
  sent: string[] = []
  closed = false
  constructor(public spec: Parameters<HubSocketFactory>[0]) {}
  send(d: string): void {
    this.sent.push(d)
  }
  close(): void {
    this.closed = true
  }
  frames(): Json[] {
    return this.sent.map((s) => JSON.parse(s) as Json)
  }
  types(): string[] {
    return this.frames().map((f) => f.type as string)
  }
}

function makePlayer(): Record<string, ReturnType<typeof vi.fn>> {
  return {
    enqueuePcm16: vi.fn(),
    flush: vi.fn(),
    clear: vi.fn(),
    setSinkId: vi.fn(),
    close: vi.fn()
  }
}

function makeEvents(): Record<keyof HubSessionEvents, ReturnType<typeof vi.fn>> {
  return {
    onConnected: vi.fn(),
    onInputTranscript: vi.fn(),
    onAssistantText: vi.fn(),
    onSpeakingStart: vi.fn(),
    onSpeakingEnd: vi.fn(),
    onToolRequest: vi.fn(),
    onTurnDone: vi.fn(),
    onError: vi.fn()
  }
}

const tick = (): Promise<void> => new Promise((r) => setTimeout(r, 0))
const tid = 't1' as VoiceTurnID
const rid = 'r1' as VoiceResponseID

function harness(opts: { token?: string; byokKey?: string } = {}): {
  session: GptLiveHubSession
  events: ReturnType<typeof makeEvents>
  player: ReturnType<typeof makePlayer>
  getSocket: () => FakeSocket
} {
  const events = makeEvents()
  const player = makePlayer()
  let socket: FakeSocket | undefined
  const socketFactory: HubSocketFactory = (spec) => {
    socket = new FakeSocket(spec)
    return socket
  }
  const clock: HubClock = { setTimer: () => ({}), clearTimer: () => {} }
  const session = new GptLiveHubSession({
    token: opts.token ?? 'omi-token/value',
    byokKey: opts.byokKey,
    instructions: 'INSTR',
    events,
    socketFactory,
    playerFactory: async () => player as never,
    clock,
    mintSessionID: () => 'sess-gpt' as VoiceSessionID
  })
  return {
    session,
    events,
    player,
    getSocket: () => {
      if (!socket) throw new Error('socket not created')
      return socket
    }
  }
}

/** Drive ensureWarm through socket-open + provider `session.started`. */
async function connect(h: ReturnType<typeof harness>): Promise<void> {
  const warm = h.session.ensureWarm()
  await tick()
  h.getSocket().spec.onOpen()
  h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.started', session: { id: 'x' } }))
  await warm
  h.getSocket().sent = []
}

describe('GptLiveHubSession — connect + session.start', () => {
  it('declares the gpt_live lane at 24kHz full duplex', () => {
    const h = harness()
    expect(h.session.provider).toBe('gpt_live')
    expect(h.session.requiredInputSampleRate).toBe(24000)
    expect(h.session.bargeInStrategy).toBe('inSessionCancel')
  })

  it('managed: targets the Omi relay with provider=gpt_live&token= and sends session.start', async () => {
    const h = harness({ token: 'omi-token/value' })
    const warm = h.session.ensureWarm()
    await tick()
    const socket = h.getSocket()
    expect(socket.spec.url).toContain('/v1/omni/relay')
    expect(socket.spec.url).toContain('provider=gpt_live')
    expect(socket.spec.url).toContain('token=omi-token%2Fvalue')
    expect(socket.spec.protocols).toBeUndefined()

    socket.spec.onOpen()
    const start = socket.frames()[0]
    expect(start.type).toBe('session.start')
    expect(typeof start.event_id).toBe('string')
    const session = start.session as Json
    expect(session.model).toBe('gpt-live-1')
    expect(session.instructions).toBe('INSTR')
    expect(session.audio).toEqual({
      format: { type: 'audio/pcm', rate: 24000 },
      output: { voice: 'marin' }
    })

    socket.spec.onMessage(JSON.stringify({ type: 'session.started', session: { id: 'x' } }))
    await warm
    expect(h.session.isWarm()).toBe(true)
    expect(h.events.onConnected).toHaveBeenCalledWith('sess-gpt')
  })

  it('BYOK: connects direct to OpenAI with the openai-insecure-api-key subprotocol', async () => {
    const h = harness({ byokKey: 'sk-user-key', token: 'sk-user-key' })
    h.session.ensureWarm().catch(() => {})
    await tick()
    const socket = h.getSocket()
    expect(socket.spec.url).toBe('wss://api.openai.com/v1/live/sessions')
    expect(socket.spec.protocols).toEqual(['openai-insecure-api-key.sk-user-key'])
  })
})

describe('GptLiveHubSession — full-duplex turn', () => {
  it('append streams session.input_audio.append with no commit/response.create frames', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([1, 2]))
    h.session.commitTurn()
    expect(h.getSocket().types()).toEqual(['session.input_audio.append'])
  })

  it('parses audio + input/output transcript deltas', async () => {
    const h = harness()
    await connect(h)
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'session.output_audio.delta', delta: 'AAAA' })
    )
    expect(h.player.enqueuePcm16).toHaveBeenCalledTimes(1)

    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'session.input_transcript.delta', delta: 'hello' })
    )
    expect(h.events.onInputTranscript).toHaveBeenCalledWith('hello', false, null)

    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'session.output_transcript.delta', delta: 'hi there' })
    )
    expect(h.events.onAssistantText).toHaveBeenCalledWith('hi there', false, null)
  })

  it('a server interrupt drops queued playback', async () => {
    const h = harness()
    await connect(h)
    h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.interrupted' }))
    expect(h.player.clear).toHaveBeenCalledTimes(1)
  })

  it('session.closed surfaces a fatal and tears the socket down', async () => {
    const h = harness()
    await connect(h)
    h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.closed', usage: {} }))
    expect(h.events.onError).toHaveBeenCalledTimes(1)
    expect(h.getSocket().closed).toBe(true)
  })
})

describe('GptLiveHubSession — cold press (warm-wait buffer)', () => {
  it('buffers PCM before ready and flushes it on session.started', async () => {
    const h = harness()
    const warm = h.session.ensureWarm()
    await tick()
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([9, 9]))
    h.session.commitTurn()
    h.getSocket().spec.onOpen()
    // Only the setup frame so far; open alone does not mark ready.
    expect(h.getSocket().types()).toEqual(['session.start'])
    h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.started', session: { id: 'x' } }))
    await warm
    expect(h.getSocket().types()).toEqual(['session.start', 'session.input_audio.append'])
  })
})
