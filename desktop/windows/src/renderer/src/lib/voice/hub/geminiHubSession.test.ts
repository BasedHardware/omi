import { describe, it, expect, vi } from 'vitest'
import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import type { HubSessionEvents, HubSocket, HubSocketFactory, HubClock } from './hubSession'

// pcmPlayer pulls the AudioWorklet `?worker&url` asset (unresolvable in node);
// stub it — base64ToBytes stays real so enqueued payloads are assertable.
vi.mock('../pcmPlayer', () => ({
  createVoicePlayer: vi.fn(),
  base64ToBytes: (s: string) => new TextEncoder().encode(s)
}))

import { GeminiHubSession } from './geminiHubSession'
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
  /** The realtimeInput sub-frame kind (activityStart / activityEnd / audio). */
  riKinds(): string[] {
    return this.frames()
      .map((f) => f.realtimeInput as Json | undefined)
      .filter((r): r is Json => !!r)
      .map((r) => Object.keys(r)[0])
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

function harness(
  opts: {
    tools?: { name: string; description: string; parameters: Record<string, unknown> }[]
  } = {}
): {
  session: GeminiHubSession
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
  const session = new GeminiHubSession({
    token: 'auth_tokens/x',
    instructions: 'INSTR',
    events,
    socketFactory,
    playerFactory: async () => player as never,
    clock,
    mintSessionID: () => 'sess-1' as VoiceSessionID,
    tools: opts.tools
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

async function connect(h: ReturnType<typeof harness>): Promise<void> {
  const warm = h.session.ensureWarm()
  await tick()
  h.getSocket().spec.onOpen()
  h.getSocket().spec.onMessage(JSON.stringify({ setupComplete: {} }))
  await warm
  h.getSocket().sent = []
}

const sc = (body: Json): string => JSON.stringify({ serverContent: body })
const audioPart = (data: string): Json => ({
  modelTurn: { parts: [{ inlineData: { mimeType: 'audio/pcm', data } }] }
})

describe('GeminiHubSession — warm config', () => {
  it('warms with automaticActivityDetection.disabled (manual VAD, PTT owns turns)', async () => {
    const h = harness()
    const warm = h.session.ensureWarm()
    await tick()
    h.getSocket().spec.onOpen()
    const setup = h.getSocket().frames()[0].setup as Json
    const ric = setup.realtimeInputConfig as Json
    const aad = ric.automaticActivityDetection as Json
    expect(aad.disabled).toBe(true)
    expect((setup.generationConfig as Json).responseModalities).toEqual(['AUDIO'])
    // No catalog wired ⇒ an empty (but faithful) functionDeclarations frame.
    expect(setup.tools).toEqual([{ functionDeclarations: [] }])
    h.getSocket().spec.onMessage(JSON.stringify({ setupComplete: {} }))
    await warm
    expect(h.events.onConnected).toHaveBeenCalledWith('sess-1')
  })

  it('projects the provider-neutral catalog into functionDeclarations (PR-C)', async () => {
    const h = harness({
      tools: [
        {
          name: 'spawn_agent',
          description: 'do work',
          parameters: { type: 'object', properties: { objective: { type: 'string' } } }
        }
      ]
    })
    const warm = h.session.ensureWarm()
    await tick()
    h.getSocket().spec.onOpen()
    const setup = h.getSocket().frames()[0].setup as Json
    // Gemini's FunctionDeclaration shape IS the neutral shape — passed straight through.
    expect(setup.tools).toEqual([
      {
        functionDeclarations: [
          {
            name: 'spawn_agent',
            description: 'do work',
            parameters: { type: 'object', properties: { objective: { type: 'string' } } }
          }
        ]
      }
    ])
    h.getSocket().spec.onMessage(JSON.stringify({ setupComplete: {} }))
    await warm
  })

  it('strips JSON-Schema-only keywords Gemini rejects from tool parameters (fast-close root cause)', async () => {
    // The real host catalog stamps `additionalProperties` on every tool (35/35). Gemini's
    // `parameters` is an OpenAPI-3.0 Schema, not full JSON Schema; sending these keys makes
    // Gemini reject the setup and close the socket seconds after connect. The setup frame
    // MUST carry a sanitized schema.
    const h = harness({
      tools: [
        {
          name: 'create_desktop_dispatch',
          description: 'dispatch',
          parameters: {
            type: 'object',
            additionalProperties: false,
            $schema: 'https://json-schema.org/draft/2020-12/schema',
            properties: {
              payload: { type: 'object', additionalProperties: true },
              kind: { type: 'string', enum: ['a', 'b'] }
            },
            required: ['kind']
          }
        }
      ]
    })
    const warm = h.session.ensureWarm()
    await tick()
    h.getSocket().spec.onOpen()
    const setup = h.getSocket().frames()[0].setup as Json
    expect(setup.tools).toEqual([
      {
        functionDeclarations: [
          {
            name: 'create_desktop_dispatch',
            description: 'dispatch',
            parameters: {
              type: 'object',
              properties: {
                payload: { type: 'object' },
                kind: { type: 'string', enum: ['a', 'b'] }
              },
              required: ['kind']
            }
          }
        ]
      }
    ])
    // No unsupported keyword survives anywhere in the emitted setup frame.
    expect(JSON.stringify(setup.tools)).not.toMatch(/additionalProperties|\$schema/)
    h.getSocket().spec.onMessage(JSON.stringify({ setupComplete: {} }))
    await warm
  })

  // NB: the REAL host catalog (buildVoiceHubToolCatalog) is exercised through the sanitizer
  // in a MAIN-side test (voiceTool.geminiSchema.test.ts) — it can't be imported here without
  // dragging the whole agent-kernel graph into the renderer suite.

  it('does not mutate a catalog shared with the OpenAI lane — OpenAI keeps additionalProperties (strict mode)', async () => {
    // One catalog object, both lanes. Gemini must strip additionalProperties; OpenAI's GA
    // realtime REQUIRES it for strict function tools — so the sanitize must be a deep COPY,
    // never an in-place mutation of the shared object. Pins cross-lane isolation forever.
    const sharedCatalog = [
      {
        name: 'update_action_item',
        description: 'edit a task',
        parameters: {
          type: 'object',
          additionalProperties: false,
          properties: { id: { type: 'string' } },
          required: ['id']
        }
      }
    ]

    // Gemini warm first (the lane that sanitizes) — its emitted schema is stripped…
    const g = harness({ tools: sharedCatalog })
    g.session.ensureWarm().catch(() => {})
    await tick()
    g.getSocket().spec.onOpen()
    const gSetup = g.getSocket().frames()[0].setup as Json
    const gParams = ((gSetup.tools as Json[])[0].functionDeclarations as Json[])[0]
      .parameters as Json
    expect(gParams.additionalProperties).toBeUndefined()

    // …the shared source object is UNTOUCHED (deep copy, no mutation)…
    expect((sharedCatalog[0].parameters as Json).additionalProperties).toBe(false)

    // …and the OpenAI lane, given the same object, still emits additionalProperties.
    const events = makeEvents()
    let openaiSocket: FakeSocket | undefined
    const oSession = new OpenAiHubSession({
      token: 'tok',
      instructions: 'instr',
      socketFactory: (spec) => {
        openaiSocket = new FakeSocket(spec)
        return openaiSocket
      },
      playerFactory: async () => makePlayer() as never,
      clock: { setTimer: () => ({}), clearTimer: () => {} },
      mintSessionID: () => 'sess-oai' as VoiceSessionID,
      tools: sharedCatalog,
      events
    })
    oSession.ensureWarm().catch(() => {})
    await tick()
    openaiSocket!.spec.onOpen()
    const oFrame = openaiSocket!.frames().find((f) => f.type === 'session.update') as Json
    const oParams = (((oFrame.session as Json).tools as Json[])[0] as Json).parameters as Json
    expect(oParams.additionalProperties).toBe(false)
  })
})

describe('GeminiHubSession — one turn', () => {
  it('activityStart → audio → activityEnd, in that exact order', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([1, 2]))
    h.session.commitTurn()
    expect(h.getSocket().riKinds()).toEqual(['activityStart', 'audio', 'activityEnd'])
    const audioFrame = h.getSocket().frames()[1].realtimeInput as Json
    expect((audioFrame.audio as Json).mimeType).toBe('audio/pcm;rate=16000')
  })
})

describe('GeminiHubSession — barge-in (fresh-session strategy, no in-session cancel)', () => {
  it('gates trailing audio off on interrupt and starts a fresh window without a cancel frame', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.commitTurn() // activityEnd → responsePending=true
    // Reply audio plays while pending.
    h.getSocket().spec.onMessage(sc(audioPart('g1')))
    expect(h.player.enqueuePcm16).toHaveBeenCalledTimes(1)
    // Server confirms interrupt → gate closes, queued playback flushed.
    h.getSocket().spec.onMessage(sc({ interrupted: true }))
    expect(h.player.clear).toHaveBeenCalledTimes(1)
    // Trailing audio for the dead generation is dropped.
    h.getSocket().spec.onMessage(sc(audioPart('g1-trailing')))
    expect(h.player.enqueuePcm16).toHaveBeenCalledTimes(1)
    // The barge-in turn opens a FRESH window (activityStart) — Gemini has no
    // in-session response cancel, so there is no cancel frame on the wire.
    h.getSocket().sent = []
    h.session.beginTurn({
      turnID: 't2' as VoiceTurnID,
      responseID: 'r2' as VoiceResponseID,
      interrupting: true
    })
    expect(h.getSocket().riKinds()).toEqual(['activityStart'])
    expect(JSON.stringify(h.getSocket().frames())).not.toMatch(/cancel/)
  })

  it('abandon (cancelTurn) closes the open activity window with activityEnd', async () => {
    const h = harness()
    await connect(h)
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.getSocket().sent = []
    h.session.cancelTurn()
    expect(h.getSocket().riKinds()).toEqual(['activityEnd'])
  })
})

describe('GeminiHubSession — idle release (D4) + re-warm', () => {
  it('tears the socket down after the idle timer, then ensureWarm re-establishes', async () => {
    const h = harness()
    await connect(h)
    const first = h.getSocket()
    h.fireIdle()
    expect(first.closed).toBe(true)
    expect(h.session.isWarm()).toBe(false)
    const warm = h.session.ensureWarm()
    await tick()
    const second = h.getSocket()
    expect(second).not.toBe(first)
    second.spec.onOpen()
    second.spec.onMessage(JSON.stringify({ setupComplete: {} }))
    await warm
    expect(h.session.isWarm()).toBe(true)
  })
})

describe('GeminiHubSession — cold press (warm-wait buffer)', () => {
  it('buffers activityStart/PCM/commit before ready, flushes in order on connect', async () => {
    const h = harness()
    const warm = h.session.ensureWarm()
    await tick()
    // Press before the socket is ready.
    h.session.beginTurn({ turnID: tid, responseID: rid })
    h.session.appendAudio(new Uint8Array([7, 7]))
    h.session.commitTurn()
    h.getSocket().spec.onOpen()
    // Only the setup frame so far; no per-turn frames until ready.
    expect(h.getSocket().riKinds()).toEqual([])
    h.getSocket().spec.onMessage(JSON.stringify({ setupComplete: {} }))
    await warm
    // Deferred activityStart, then buffered audio, then the deferred commit.
    expect(h.getSocket().riKinds()).toEqual(['activityStart', 'audio', 'activityEnd'])
  })
})
