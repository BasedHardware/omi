// Regression test for the carry-forward bug fix surfaced in the A5 PR-5 audit:
// `BaseHubSession.send()` had no `readyState` guard, so a control frame emitted
// while the socket was still CONNECTING (e.g. a slow-warm barge-in `cancelTurn`
// sending `input_audio_buffer.clear`) would call a real `WebSocket.send` in the
// CONNECTING state and throw `InvalidStateError` out of `send()`. The guard drops
// such a frame instead. See hubSession.ts `send()`.

import { describe, it, expect } from 'vitest'
import {
  BaseHubSession,
  defaultSocketFactory,
  type HubBargeInStrategy,
  type HubProvider,
  type HubSocketFactory
} from './hubSession'
import type { VoicePlayer } from '../pcmPlayer'

/** A player that does nothing — the base only needs it to exist. */
const noopPlayer: VoicePlayer = {
  enqueuePcm16: () => {},
  clear: () => {},
  flush: () => {},
  close: () => {}
} as unknown as VoicePlayer

// Regression for the Gemini binary-frame drop that the default-ON hub flip would
// otherwise ship. Gemini Live delivers control frames (incl. the
// `{"setupComplete":{}}` readiness signal) as BINARY. The real defaultSocketFactory
// must set binaryType='arraybuffer' and decode binary→text; otherwise the readiness
// frame is dropped, the Gemini session never warms, and every hub turn silently
// cascades. The injected-fake socket tests below never exercise this real factory
// (they pass strings), which is exactly why this shipped uncaught for Gemini.
describe('defaultSocketFactory — binary frame decoding', () => {
  it('sets binaryType=arraybuffer and decodes a BINARY readiness frame to text', () => {
    let created: FakeWS | null = null
    class FakeWS {
      binaryType = 'blob'
      onopen: (() => void) | null = null
      onmessage: ((e: { data: unknown }) => void) | null = null
      onclose: ((e: { code: number; reason: string }) => void) | null = null
      onerror: (() => void) | null = null
      readyState = 0
      constructor(
        public url: string,
        public protocols?: string | string[]
      ) {
        created = this
      }
      send(): void {}
      close(): void {}
    }
    const orig = globalThis.WebSocket
    globalThis.WebSocket = FakeWS as unknown as typeof WebSocket
    try {
      const received: string[] = []
      defaultSocketFactory({
        url: 'wss://generativelanguage.googleapis.com/ws',
        onOpen: () => {},
        onMessage: (m) => received.push(m),
        onClose: () => {},
        onError: () => {}
      })
      expect(created).not.toBeNull()
      // Without this the browser delivers binary frames as Blob and they are dropped.
      expect(created!.binaryType).toBe('arraybuffer')

      // Gemini's readiness frame — arrives BINARY, not string.
      const binary = new TextEncoder().encode('{"setupComplete":{}}').buffer
      created!.onmessage!({ data: binary })
      expect(received).toEqual(['{"setupComplete":{}}'])

      // A normal string frame (OpenAI, or Gemini text) still passes through unchanged.
      created!.onmessage!({ data: '{"serverContent":{}}' })
      expect(received).toEqual(['{"setupComplete":{}}', '{"serverContent":{}}'])
    } finally {
      globalThis.WebSocket = orig
    }
  })
})

/** A controllable socket whose `send` throws when not OPEN, exactly like a real
 *  `WebSocket` — so a missing guard in `BaseHubSession.send` would surface as a
 *  thrown error, and the guard's presence as a silently-dropped frame. */
function makeControllableSocket() {
  const sent: string[] = []
  let readyState = 0 // CONNECTING
  let spec: Parameters<HubSocketFactory>[0] | null = null
  const factory: HubSocketFactory = (s) => {
    spec = s
    return {
      send: (d) => {
        if (readyState !== 1) throw new Error('InvalidStateError')
        sent.push(d)
      },
      close: () => {
        readyState = 3
      },
      get readyState() {
        return readyState
      }
    }
  }
  return {
    sent,
    factory,
    /** Move to OPEN and fire the open handshake (sends the setup frame). */
    open: () => {
      readyState = 1
      spec?.onOpen()
    },
    setReadyState: (n: number) => {
      readyState = n
    }
  }
}

/** Minimal concrete session that routes `cancelTurn` to a base `send()` so the
 *  guard is exercised through the real per-turn primitive path. */
class TestHubSession extends BaseHubSession {
  readonly provider: HubProvider = 'openai'
  readonly requiredInputSampleRate = 24000
  readonly bargeInStrategy: HubBargeInStrategy = 'inSessionCancel'
  protected connectSpec(): { url: string; protocols?: string[] } {
    return { url: 'wss://test.invalid/realtime' }
  }
  protected sessionSetupFrame(): object {
    return { type: 'session.setup' }
  }
  protected handleProviderMessage(obj: Record<string, unknown>): void {
    if (obj.type === 'ready') this.markReady()
  }
  protected canAcceptInput(): boolean {
    return this.isOpen
  }
  protected appendAudioFrame(): void {
    /* unused in this test */
  }
  protected onBeginTurn(): void {
    /* unused in this test */
  }
  protected commitTurnNow(): void {
    /* unused in this test */
  }
  protected onCancelTurn(): void {
    // A control frame — the exact shape that races a not-yet-open socket.
    this.send({ type: 'input_audio_buffer.clear' })
  }
  protected onSendToolResult(): void {
    /* unused in this test */
  }
  protected onProviderReady(): void {
    /* unused in this test */
  }
  protected resetProviderState(): void {
    /* unused in this test */
  }
}

async function warmedSession() {
  const sock = makeControllableSocket()
  const session = new TestHubSession({
    token: 'tok',
    instructions: 'instr',
    socketFactory: sock.factory,
    playerFactory: async () => noopPlayer
  })
  void session.ensureWarm()
  // openConnection awaits the player factory before creating the socket.
  await Promise.resolve()
  await Promise.resolve()
  return { sock, session }
}

describe('BaseHubSession.send — non-OPEN socket guard', () => {
  it('drops a control frame on a CONNECTING socket without throwing', async () => {
    const { sock, session } = await warmedSession()
    // Socket exists but is still CONNECTING (no open handshake yet).
    expect(() => session.cancelTurn()).not.toThrow()
    expect(sock.sent).toEqual([])
  })

  it('sends the control frame once the socket is OPEN', async () => {
    const { sock, session } = await warmedSession()
    sock.open() // OPEN + fires the setup frame
    expect(sock.sent).toEqual([JSON.stringify({ type: 'session.setup' })])
    session.cancelTurn()
    expect(sock.sent).toEqual([
      JSON.stringify({ type: 'session.setup' }),
      JSON.stringify({ type: 'input_audio_buffer.clear' })
    ])
  })

  it('drops a control frame on a CLOSING socket without throwing', async () => {
    const { sock, session } = await warmedSession()
    sock.open()
    sock.setReadyState(2) // CLOSING
    expect(() => session.cancelTurn()).not.toThrow()
    // Only the setup frame from open() — the CLOSING control frame was dropped.
    expect(sock.sent).toEqual([JSON.stringify({ type: 'session.setup' })])
  })
})
