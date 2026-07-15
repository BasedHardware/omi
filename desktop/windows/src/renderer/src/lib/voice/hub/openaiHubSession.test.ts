import { describe, it, expect, vi } from 'vitest'
import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import type { HubSessionEvents, HubSocket, HubSocketFactory, HubClock } from './hubSession'

// pcmPlayer transitively imports the AudioWorklet `?worker&url` asset, which does
// not resolve in the node test env. Stub it: base64ToBytes stays a real passthrough
// so we can assert the enqueued payload; the player is injected per-session anyway.
vi.mock('../pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

import { OpenAiHubSession } from './openaiHubSession'

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

function harness(): {
  session: OpenAiHubSession
  events: ReturnType<typeof makeEvents>
  player: ReturnType<typeof makePlayer>
  getSocket: () => FakeSocket
  fireIdle: () => void
} {
  const events = makeEvents()
  const player = makePlayer()
  let socket: FakeSocket | undefined
  const socketFactory: HubSocketFactory = (spec) => {
    socket = new FakeSocket(spec)
    return socket
  }
  let idleFire: (() => void) | null = null
  const clock: HubClock = {
    setTimer: (_ms, fire) => {
      idleFire = fire
      return {}
    },
    clearTimer: () => {
      idleFire = null
    }
  }
  const session = new OpenAiHubSession({
    token: 'ek_secret',
    instructions: 'INSTR',
    events,
    socketFactory,
    playerFactory: async () => player as never,
    clock,
    mintSessionID: () => 'sess-1' as VoiceSessionID,
    idleReleaseMs: 180_000
  })
  return {
    session,
    events,
    player,
    getSocket: () => {
      if (!socket) throw new Error('socket not created')
      return socket
    },
    fireIdle: () => idleFire?.()
  }
}

/** Drive ensureWarm through socket-open + provider ready, then clear setup frames. */
async function connect(h: ReturnType<typeof harness>): Promise<void> {
  const warm = h.session.ensureWarm()
  await tick() // playerFactory await → socket created
  h.getSocket().spec.onOpen()
  h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.created' }))
  await warm
  h.getSocket().sent = [] // drop the session.update so per-turn frames are isolated
}

describe('OpenAiHubSession — warm config', () => {
  it('warms with turn_detection: null and NO server VAD (PTT owns turns)', async () => {
    const h = harness()
    const warm = h.session.ensureWarm()
    await tick()
    h.getSocket().spec.onOpen()
    const setup = h.getSocket().frames()[0]
    expect(setup.type).toBe('session.update')
    const session = setup.session as Json
    const audio = session.audio as Json
    const input = audio.input as Json
    // turn_detection is explicitly null — the single most important warm assertion.
    expect(input.turn_detection).toBeNull()
    expect('turn_detection' in input).toBe(true)
    // No auto-VAD anywhere in the input config.
    expect(JSON.stringify(input)).not.toMatch(/server_vad|semantic_vad|"create_response"/)
    expect(input.format).toEqual({ type: 'audio/pcm', rate: 24000 })
    h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.created' }))
    await warm
    expect(h.session.isWarm()).toBe(true)
    expect(h.events.onConnected).toHaveBeenCalledWith('sess-1')
  })
})

describe('OpenAiHubSession — one turn', () => {
  it('append (while held) → commit → response.create, in that exact order', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([1, 2, 3, 4]))
    h.session.appendAudio(new Uint8Array([5, 6]))
    h.session.commitTurn()
    expect(h.getSocket().types()).toEqual([
      'input_audio_buffer.append',
      'input_audio_buffer.append',
      'input_audio_buffer.commit',
      'response.create'
    ])
    const create = h.getSocket().frames()[3]
    expect((create.response as Json).output_modalities).toEqual(['audio'])
  })

  it('response.done with no tool calls finishes the turn once', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.commitTurn()
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'response.created', response: { id: 'resp_1' } })
    )
    // Audio delta for the current response is played through pcmPlayer.
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'response.output_audio.delta', response_id: 'resp_1', delta: 'AAAA' })
    )
    expect(h.player.enqueuePcm16).toHaveBeenCalledTimes(1)
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'response.done', response: { id: 'resp_1', output: [] } })
    )
    expect(h.events.onTurnDone).toHaveBeenCalledTimes(1)
    // A stale response.done (wrong id) does not finish again.
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'response.done', response: { id: 'other', output: [] } })
    )
    expect(h.events.onTurnDone).toHaveBeenCalledTimes(1)
  })
})

describe('OpenAiHubSession — barge-in (Swift-faithful)', () => {
  it('cancels the in-flight reply with response.cancel + input_audio_buffer.clear, NOT truncate', async () => {
    const h = harness()
    await connect(h)
    // Establish an active response.
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.commitTurn()
    h.getSocket().spec.onMessage(
      JSON.stringify({ type: 'response.created', response: { id: 'resp_1' } })
    )
    h.getSocket().sent = []
    // Barge-in: a new turn interrupts the live reply.
    h.session.beginTurn({
      turnID: 't2' as VoiceTurnID,
      responseID: 'r2' as VoiceResponseID,
      interrupting: true
    })
    const types = h.getSocket().types()
    expect(types).toContain('response.cancel')
    expect(types).toContain('input_audio_buffer.clear')
    // §C.5 / the plan summary claim `conversation.item.truncate`; the actual macOS
    // session never sends it. The Swift wins — assert it is absent.
    expect(types).not.toContain('conversation.item.truncate')
    // Stale playback for the cancelled reply is dropped.
    expect(h.player.clear).toHaveBeenCalled()
  })
})

describe('OpenAiHubSession — idle release (D4) + re-warm', () => {
  it('tears the socket down after the idle timer, then ensureWarm re-establishes', async () => {
    const h = harness()
    await connect(h)
    const first = h.getSocket()
    expect(h.session.isWarm()).toBe(true)
    h.fireIdle()
    expect(first.closed).toBe(true)
    expect(h.session.isWarm()).toBe(false)
    // Re-warm mints a fresh socket and reaches ready again.
    const warm = h.session.ensureWarm()
    await tick()
    const second = h.getSocket()
    expect(second).not.toBe(first)
    second.spec.onOpen()
    second.spec.onMessage(JSON.stringify({ type: 'session.updated' }))
    await warm
    expect(h.session.isWarm()).toBe(true)
  })
})

describe('OpenAiHubSession — cold press (warm-wait buffer)', () => {
  it('buffers PCM + commit sent before the socket is ready, flushes on connect', async () => {
    const h = harness()
    const warm = h.session.ensureWarm()
    await tick()
    // Press arrives before the provider is ready.
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([9, 9]))
    h.session.commitTurn()
    // Nothing turn-related on the wire yet (only the pre-open setup, if open fired).
    h.getSocket().spec.onOpen()
    h.getSocket().sent = h.getSocket().sent.filter((s) => !s.includes('session.update'))
    expect(h.getSocket().types()).toEqual([])
    // Provider becomes ready → buffered audio + commit flush in order.
    h.getSocket().spec.onMessage(JSON.stringify({ type: 'session.created' }))
    await warm
    expect(h.getSocket().types()).toEqual([
      'input_audio_buffer.append',
      'input_audio_buffer.commit',
      'response.create'
    ])
  })
})
