// GPT-Live-1 (OpenAI) hub lane over WebSocket.
//
// GPT-Live-1 is a FULL-DUPLEX text-JSON protocol: the server owns turn detection
// and response generation, so there is NO `response.create`, NO input commit, and
// NO per-turn activity window. PTT simply streams mic PCM while held; the server
// emits user/assistant transcript deltas and PCM audio as the conversation flows.
// This is why `canAcceptInput` is gated only on the socket being open.
//
// Managed auth (the Windows path): the Omi backend injects the OpenAI key, so the
// session connects to the Omi relay `wss://<backend>/v1/omni/relay?provider=gpt_live`
// and authenticates in the first WS message (`{type:'auth', token}`) because a
// renderer WebSocket cannot set an Authorization header and the bearer token must
// not ride the URL. BYOK: when the caller supplies the user's own OpenAI key, we
// connect direct to `wss://api.openai.com/v1/live/sessions` and carry the key in
// the `openai-insecure-api-key.<key>` subprotocol (the same pattern
// `openaiHubSession.ts` uses for the realtime API).
//
// The macOS `RealtimeHubSession.swift` has no GPT-Live lane yet; this mirrors its
// OpenAI/Gemini lane shape and the web client's protocol
// (`web/app/src/lib/gptLive.ts`), which is the wire reference.

import { GPT_LIVE_MODEL } from '../tokenMint'
import {
  BaseHubSession,
  type HubBargeInStrategy,
  type HubProvider,
  type HubSessionOptions
} from './hubSession'

/** GPT-Live's output voice (mirrors the web client's `GPT_LIVE_VOICE`). */
export const GPT_LIVE_VOICE = 'marin'

/** The backend WebSocket base for the Omi relay, derived from the API base the
 *  renderer already uses (http(s) → ws(s)). Defaults to the production backend
 *  when the env var is absent (tests / a bare node import). */
function relayWsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_OMI_API_BASE as string | undefined
  if (apiBase && /^https?:\/\//.test(apiBase))
    return apiBase.replace(/^http/, 'ws').replace(/\/$/, '')
  return 'wss://api.omi.me'
}

/** The Omi relay URL for a managed GPT-Live session. The Omi bearer token never
 *  travels in the query string (WebSocket request targets are logged); managed
 *  clients send it in the first `{type:'auth'}` message. Exported for the URL test. */
export function gptLiveRelayUrl(): string {
  return `${relayWsBaseUrl()}/v1/omni/relay?provider=gpt_live`
}

/** Unique per-frame event id (the protocol requires one on `session.start`). */
function eventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `evt-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export class GptLiveHubSession extends BaseHubSession {
  readonly provider: HubProvider = 'gpt_live'
  readonly requiredInputSampleRate = 24000
  // Full duplex: the server detects barge-ins and emits `session.interrupted`, so
  // no fresh session is required — we only flush locally queued playback.
  readonly bargeInStrategy: HubBargeInStrategy = 'inSessionCancel'

  private readonly byokKey: string | undefined

  constructor(opts: HubSessionOptions) {
    super(opts)
    this.byokKey = opts.byokKey
  }

  protected connectSpec(): { url: string; protocols?: string[] } {
    if (this.byokKey) {
      // BYOK: direct to OpenAI with the key in the WS subprotocol.
      return {
        url: 'wss://api.openai.com/v1/live/sessions',
        protocols: [`openai-insecure-api-key.${this.byokKey}`]
      }
    }
    // Managed: through the Omi relay, which injects the OpenAI key server-side.
    return { url: gptLiveRelayUrl() }
  }

  /** Managed relay: the renderer cannot set the upgrade `Authorization` header,
   *  so the Omi token is sent in the first WS message (never the URL). BYOK
   *  connects direct to OpenAI with the key in the subprotocol — no auth frame. */
  protected authFrame(): object | null {
    if (this.byokKey) return null
    return { type: 'auth', token: this.token }
  }

  protected sessionSetupFrame(): object {
    return {
      type: 'session.start',
      event_id: eventId(),
      session: {
        model: GPT_LIVE_MODEL,
        instructions: this.instructions,
        audio: {
          format: { type: 'audio/pcm', rate: 24000 },
          output: { voice: GPT_LIVE_VOICE }
        }
      }
    }
  }

  protected canAcceptInput(): boolean {
    return this.isOpen
  }

  protected appendAudioFrame(b64: string): void {
    this.send({ type: 'session.input_audio.append', audio: b64 })
  }

  protected onBeginTurn(interrupting: boolean): void {
    // A barge-in on a full-duplex lane: drop locally queued reply audio so the
    // old reply can't keep playing. The server separately emits
    // `session.interrupted`; no client cancel frame exists in the protocol.
    if (interrupting) this.clearPlayback()
  }

  protected commitTurnNow(): void {
    // No-op: GPT-Live has no input commit — the server responds on its own.
  }

  protected onCancelTurn(): void {
    // Abandon (silent tap / cancel), keeping the warm socket. There is no input
    // buffer to clear on the wire; drop queued playback and let the server's
    // interruption handling take over.
    this.clearPlayback()
  }

  protected onSendToolResult(_callId: string, _name: string, _output: string): void {
    // The GPT-Live protocol has no function-call frames (web parity); tool relay
    // is a follow-up once the server advertises a tool-call event.
  }

  protected onProviderReady(): void {
    /* Full-duplex: no deferred activity window to open at ready. */
  }

  protected resetProviderState(): void {
    /* No per-connection provider flags to clear. */
  }

  // MARK: Receive

  protected handleProviderMessage(e: Record<string, unknown>): void {
    const type = e.type
    if (typeof type !== 'string') return
    switch (type) {
      case 'session.started':
        this.markReady()
        return
      case 'session.output_audio.delta': {
        if (typeof e.delta === 'string') this.playAudio(e.delta)
        return
      }
      case 'session.input_transcript.delta': {
        if (typeof e.delta === 'string') this.emitInputTranscript(e.delta, false)
        return
      }
      case 'session.output_transcript.delta': {
        if (typeof e.delta === 'string') this.emitAssistantText(e.delta, false)
        return
      }
      case 'session.interrupted': {
        this.clearPlayback()
        return
      }
      case 'response.event': {
        this.handleResponseEvent(e)
        return
      }
      case 'session.closed': {
        // The server ended the session. Surface it as a normal close so the hub
        // controller's reconnect policy runs (same class as a socket close).
        this.handleError('gpt-live session closed', true)
        return
      }
      case 'error': {
        const err = e.error
        const nested =
          typeof err === 'object' && err !== null
            ? (err as Record<string, unknown>).message
            : undefined
        const message =
          (typeof e.message === 'string' && e.message) ||
          (typeof err === 'string' && err) ||
          (typeof nested === 'string' ? nested : 'GPT-Live realtime error')
        this.handleError(message, true)
        return
      }
      default: {
        // Defensive: an `interrupted` boolean may ride any frame.
        if (e.interrupted === true) this.clearPlayback()
        return
      }
    }
  }

  /**
   * GPT-Live response lifecycle arrives as `response.event` envelopes (mirrors
   * `RealtimeHubSession.swift`). A nested `response.done` / `response.completed`
   * is the per-turn boundary the full-duplex lane otherwise never surfaces, so
   * the hub would wait out `providerNoResponse` on every spoken turn. Tool calls
   * are not yet mapped onto the hub pipeline (web parity) — return without
   * ending the turn so a tool-only event can't dispatch a premature finish.
   */
  private handleResponseEvent(e: Record<string, unknown>): void {
    const nested = (e.event as Record<string, unknown> | undefined) ?? e
    const nestedType = typeof nested.type === 'string' ? nested.type : ''
    if (nestedType.includes('function_call') || nestedType.includes('tool_call')) {
      return
    }
    if (nestedType === 'response.done' || nestedType === 'response.completed') {
      this.flushPlayback()
      this.emitAssistantText('', true)
      this.emitTurnDone()
    }
  }
}
