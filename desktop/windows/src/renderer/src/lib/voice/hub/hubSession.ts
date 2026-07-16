// Warm-hub provider session lanes (Track 2 / A5 PR-4).
//
// A hub session owns ONE persistent WebSocket to a realtime provider and drives
// the per-turn frame choreography for a system-wide PTT turn. It is a 1:1 port of
// the provider-session half of macOS `RealtimeHubSession.swift`
// (Sources/FloatingControlBar/RealtimeHubSession.swift). The macOS
// `RealtimeHubController` facade is deliberately NOT ported (orchestrator ruling);
// only the session-level frame logic lives here.
//
// Windows deviations from Mac, all mandated by the A5 orchestrator decisions:
//   * D3 — the OpenAI lane is WebSocket + capture-window PCM, NOT the shipped
//     `OpenAIRealtimeWebRTC` lane. A warm WebRTC session would hold the mic open
//     for its whole lifetime and light the Windows mic-privacy indicator. So these
//     lanes NEVER call `acquireMicStream`: mic PCM is fed in via `appendAudio()`
//     (the capture window already produces it, mic opens only while a turn is
//     held) and spoken audio is played through the EXISTING `pcmPlayer`
//     (`createVoicePlayer`) — no new audio graph. The shipped WebRTC lane
//     (`openaiSession.ts`) is untouched; it still serves the continuous Home
//     voice surface.
//   * D4 — a warm socket is released after 180 s idle (`HUB_IDLE_RELEASE_MS`) and
//     `ensureWarm()` can be called eagerly (e.g. on bar summon) and is idempotent;
//     a cold press degrades gracefully because pre-open mic PCM is buffered and
//     flushed on connect.
//
// These lanes are standalone in PR-4: they are exercised against a fake WebSocket
// and are NOT wired into the live PTT reducer/coordinator (PR-6 does that behind
// the `pttHubEnabled` kill-switch). Everything is injectable (socket, player,
// clock, session-id mint) so the wire frames can be asserted hermetically.

import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import { base64ToBytes, createVoicePlayer, type VoicePlayer } from '../pcmPlayer'

export type HubProvider = 'openai' | 'gemini'

/** Provider-specific interruption contract, mirroring Swift `bargeInStrategy`.
 *  OpenAI can cancel an in-flight reply in-session; Gemini cannot cleanly cancel
 *  a streaming reply, so its barge-in is a fresh session (the controller's job). */
export type HubBargeInStrategy = 'inSessionCancel' | 'freshSession'

/** Identity a hub event belongs to. Threaded through so a future host can map an
 *  incoming provider callback back to the reducer's turn/response fencing. */
export type HubEventIdentity = {
  readonly turnID: VoiceTurnID
  readonly responseID: VoiceResponseID
}

/** Everything a hub session emits. Audio itself is played internally through the
 *  existing `pcmPlayer` (D3); the audible-output signal surfaces as speaking
 *  edges, which is what the echo gate and the output lease need. */
export type HubSessionEvents = {
  /** Socket handshake complete, config applied, audio can flow. */
  onConnected?: (sessionID: VoiceSessionID) => void
  /** User speech STT from the provider (input transcription). */
  onInputTranscript?: (text: string, isFinal: boolean, identity: HubEventIdentity | null) => void
  /** Assistant reply text (for the on-screen bubble / logging). */
  onAssistantText?: (text: string, isFinal: boolean, identity: HubEventIdentity | null) => void
  /** Spoken audio began audibly playing (echo gate: activate). */
  onSpeakingStart?: () => void
  /** Spoken audio drained / was interrupted (echo gate: start release). */
  onSpeakingEnd?: () => void
  /** The model requested a tool call. Tool EXECUTION is a host concern; the lane
   *  only surfaces the request and can relay a result via `sendToolResult`. */
  onToolRequest?: (
    call: { name: string; callId: string; argumentsJSON: string },
    identity: HubEventIdentity | null
  ) => void
  /** The model finished this turn (spoken reply complete). */
  onTurnDone?: (identity: HubEventIdentity | null) => void
  /** The session cannot continue (handshake failed or a fatal mid-session drop).
   *  `closeCode` is the WS close code when the drop came from a socket close (so the
   *  hub controller can classify a Gemini 1008 idle-teardown vs a fast fault); absent
   *  for non-close faults (an OpenAI error frame, an audio-init failure). */
  onError?: (message: string, retryable: boolean, closeCode?: number) => void
}

/** The four per-turn primitives (plus warm/teardown) both providers implement. */
export type HubSession = {
  readonly provider: HubProvider
  /** Mic PCM16 input rate the caller must resample to (OpenAI GA 24k, Gemini 16k). */
  readonly requiredInputSampleRate: number
  readonly bargeInStrategy: HubBargeInStrategy
  /** Open (or reuse) the warm socket and apply session config. Idempotent. */
  ensureWarm(): Promise<void>
  isWarm(): boolean
  /** Start a PTT turn. Gemini opens a fresh speech-activity window every turn;
   *  OpenAI, when `interrupting`, cancels the in-flight reply first. */
  beginTurn(opts?: {
    turnID?: VoiceTurnID
    responseID?: VoiceResponseID
    interrupting?: boolean
  }): void
  /** Feed one mic PCM16 frame at `requiredInputSampleRate` (buffered pre-open). */
  appendAudio(pcm: Uint8Array): void
  /** End the held turn and ask the model to respond. */
  commitTurn(): void
  /** Abandon the current turn without a reply, keeping the warm socket (silent
   *  tap / cancel / barge-in). */
  cancelTurn(): void
  /** Return a tool result to the model so it can continue speaking. */
  sendToolResult(callId: string, name: string, output: string): void
  /** Close the socket. The object stays reusable — `ensureWarm()` re-establishes. */
  teardown(): void
}

// MARK: - Injectable seams (socket / player / clock)

/** Minimal socket surface the sessions use — real `WebSocket` in production, a
 *  frame-recording fake in tests. Client→server frames are always JSON TEXT
 *  (spoken audio rides as base64 inside JSON), so `send` is string-typed. But
 *  server→client frames are NOT all text: Gemini Live delivers its JSON control
 *  frames (incl. the `{"setupComplete":{}}` readiness signal) as BINARY, so the
 *  real factory decodes binary→text before `onMessage` (which stays string). */
export type HubSocket = {
  send(data: string): void
  close(): void
  /** The live `WebSocket.readyState` (0 CONNECTING · 1 OPEN · 2 CLOSING · 3
   *  CLOSED). Optional so a minimal test fake may omit it — an absent readyState
   *  is treated as always-sendable (backward compatible with existing fakes). The
   *  real factory exposes it so `BaseHubSession.send` can drop a control frame
   *  that races a not-yet-open socket instead of throwing `InvalidStateError`. */
  readonly readyState?: number
}

/** `WebSocket.OPEN` as a bare literal — used off the DOM (vitest node env has no
 *  global `WebSocket`), and identical to the spec constant. */
const WEBSOCKET_OPEN = 1
export type HubSocketFactory = (spec: {
  url: string
  protocols?: string[]
  onOpen: () => void
  onMessage: (data: string) => void
  onClose: (code: number, reason: string) => void
  onError: (message: string) => void
}) => HubSocket

/** Injectable timer so the 180 s idle release is testable with fake timers. */
export type HubClock = {
  setTimer(ms: number, fire: () => void): unknown
  clearTimer(handle: unknown): void
}

const defaultClock: HubClock = {
  setTimer: (ms, fire) => setTimeout(fire, ms),
  clearTimer: (h) => clearTimeout(h as ReturnType<typeof setTimeout>)
}

const wsTextDecoder = new TextDecoder()

// Exported for the binary-frame regression test (hubSession.test.ts). The
// injected-fake socket tests pass strings and never exercise this real factory,
// which is how the dropped-binary-frame bug reached the default-ON flip.
export const defaultSocketFactory: HubSocketFactory = (spec) => {
  const ws = new WebSocket(spec.url, spec.protocols)
  // Gemini Live delivers control frames (incl. the `{"setupComplete":{}}`
  // readiness signal) as BINARY. Force ArrayBuffer delivery (browser default is
  // Blob) and decode to text; without this the readiness frame is dropped, the
  // Gemini session never warms, and every hub turn silently cascades.
  ws.binaryType = 'arraybuffer'
  ws.onopen = () => spec.onOpen()
  ws.onmessage = (e: MessageEvent) =>
    spec.onMessage(
      typeof e.data === 'string' ? e.data : e.data instanceof ArrayBuffer ? wsTextDecoder.decode(e.data) : ''
    )
  ws.onclose = (e: CloseEvent) => spec.onClose(e.code, e.reason)
  ws.onerror = () => spec.onError('websocket error')
  return {
    send: (d) => ws.send(d),
    close: () => {
      try {
        ws.close()
      } catch {
        /* already closing */
      }
    },
    get readyState() {
      return ws.readyState
    }
  }
}

/** D4: release a warm socket after this much idle time. Named + tunable. */
export const HUB_IDLE_RELEASE_MS = 180_000

export type HubSessionOptions = {
  /** Ephemeral token minted by the backend (managed users — Windows path). */
  token: string
  /** Assembled per-session system instruction (A9). */
  instructions: string
  /** Output device for spoken audio ('' / undefined = system default). */
  sinkId?: string
  events?: HubSessionEvents
  socketFactory?: HubSocketFactory
  /** Spoken-audio player factory (default = the existing `pcmPlayer`). */
  playerFactory?: (opts: { onStarted: () => void; onDrained: () => void }) => Promise<VoicePlayer>
  clock?: HubClock
  mintSessionID?: () => VoiceSessionID
  idleReleaseMs?: number
  /** Provider tool declarations. Tool CATALOG assembly is a host concern (PR-5/6);
   *  default is none so the warm frame is still faithful. */
  tools?: unknown[]
}

/** Chunked bytes → base64 (large frames must not blow the `String.fromCharCode`
 *  arg limit). Mirrors `pcmPlayer.int16ToBase64` for raw byte input. */
export function bytesToBase64(bytes: Uint8Array): string {
  let binary = ''
  const STEP = 0x8000
  for (let i = 0; i < bytes.length; i += STEP) {
    binary += String.fromCharCode(...bytes.subarray(i, i + STEP))
  }
  return btoa(binary)
}

// MARK: - Shared base (socket lifecycle, idle release, warm-wait buffer, player)

/** Everything both providers share: connect/teardown, the 180 s idle timer, the
 *  pre-open PCM buffer, spoken-audio playback through `pcmPlayer`, and the emit
 *  helpers. Provider subclasses supply the wire frames and message parsing. */
export abstract class BaseHubSession implements HubSession {
  abstract readonly provider: HubProvider
  abstract readonly requiredInputSampleRate: number
  abstract readonly bargeInStrategy: HubBargeInStrategy

  protected readonly instructions: string
  protected readonly token: string
  protected readonly tools: unknown[]
  private readonly events: HubSessionEvents
  private readonly socketFactory: HubSocketFactory
  private readonly clock: HubClock
  private readonly mintSessionID: () => VoiceSessionID
  private readonly idleReleaseMs: number
  private readonly createPlayer: (opts: {
    onStarted: () => void
    onDrained: () => void
  }) => Promise<VoicePlayer>

  protected socket: HubSocket | null = null
  protected isOpen = false
  protected sessionID: VoiceSessionID | null = null
  /** Identity of the turn currently held (set by `beginTurn`). */
  protected activeIdentity: HubEventIdentity | null = null

  /** Mic PCM (base64) captured before the socket/activity window is ready. */
  private pendingAudio: string[] = []
  protected pendingCommit = false

  private player: VoicePlayer | null = null
  private idleHandle: unknown = null
  private warmPromise: Promise<void> | null = null
  private warmResolve: (() => void) | null = null
  private warmReject: ((e: Error) => void) | null = null
  private errored = false

  constructor(opts: HubSessionOptions) {
    this.instructions = opts.instructions
    this.token = opts.token
    this.tools = opts.tools ?? []
    this.events = opts.events ?? {}
    this.socketFactory = opts.socketFactory ?? defaultSocketFactory
    this.clock = opts.clock ?? defaultClock
    this.mintSessionID = opts.mintSessionID ?? (() => crypto.randomUUID() as VoiceSessionID)
    this.idleReleaseMs = opts.idleReleaseMs ?? HUB_IDLE_RELEASE_MS
    this.createPlayer =
      opts.playerFactory ??
      ((o) =>
        createVoicePlayer({
          sampleRate: 24000, // both providers emit 24 kHz spoken PCM
          sinkId: opts.sinkId,
          onStarted: o.onStarted,
          onDrained: o.onDrained
        }))
  }

  // MARK: Warm / teardown (shared)

  ensureWarm(): Promise<void> {
    this.touchIdle()
    if (this.isOpen) return Promise.resolve()
    if (this.warmPromise) return this.warmPromise
    this.errored = false
    this.sessionID = this.mintSessionID()
    this.warmPromise = new Promise<void>((resolve, reject) => {
      this.warmResolve = resolve
      this.warmReject = reject
    })
    void this.openConnection()
    return this.warmPromise
  }

  isWarm(): boolean {
    return this.isOpen
  }

  private async openConnection(): Promise<void> {
    let player: VoicePlayer
    try {
      player = await this.createPlayer({
        onStarted: () => this.events.onSpeakingStart?.(),
        onDrained: () => this.events.onSpeakingEnd?.()
      })
    } catch {
      this.handleError('audio player init failed', true)
      return
    }
    // A teardown() during the await voids this connection attempt.
    if (!this.warmPromise) {
      player.close()
      return
    }
    this.player = player
    const spec = this.connectSpec()
    this.socket = this.socketFactory({
      url: spec.url,
      protocols: spec.protocols,
      onOpen: () => this.onSocketOpen(),
      onMessage: (d) => this.onSocketMessage(d),
      onClose: (c, r) => this.handleError(`websocket closed (${c})${r ? ` ${r}` : ''}`, true, c),
      onError: (m) => this.handleError(m, true)
    })
  }

  private onSocketOpen(): void {
    // Provider "ready" (session.created / setupComplete) flips isOpen in
    // markReady(); the open handshake only sends session setup.
    this.send(this.sessionSetupFrame())
  }

  private onSocketMessage(data: string): void {
    this.touchIdle() // any socket traffic (incl. a long reply) keeps the socket warm
    let obj: Record<string, unknown>
    try {
      obj = JSON.parse(data) as Record<string, unknown>
    } catch {
      return
    }
    this.handleProviderMessage(obj)
  }

  /** Called by the subclass when the provider signals the session is ready. */
  protected markReady(): void {
    if (this.isOpen) return
    this.isOpen = true
    this.onProviderReady() // subclass: Gemini opens a deferred activity window
    this.flushPendingAudio()
    if (this.pendingCommit && this.canAcceptInput()) {
      this.pendingCommit = false
      this.commitTurnNow()
    }
    if (this.warmResolve) {
      this.warmResolve()
      this.warmResolve = null
      this.warmReject = null
    }
    this.warmPromise = null
    if (this.sessionID) this.events.onConnected?.(this.sessionID)
    this.touchIdle()
  }

  teardown(): void {
    if (this.idleHandle != null) {
      this.clock.clearTimer(this.idleHandle)
      this.idleHandle = null
    }
    const s = this.socket
    this.socket = null
    this.isOpen = false
    this.pendingAudio = []
    this.pendingCommit = false
    this.resetProviderState()
    try {
      s?.close()
    } catch {
      /* already gone */
    }
    this.player?.close()
    this.player = null
    // A warm() in flight torn down before it opened must not hang its caller.
    if (this.warmReject) {
      this.warmReject(new Error('hub session torn down before ready'))
    }
    this.warmResolve = null
    this.warmReject = null
    this.warmPromise = null
  }

  // MARK: Idle release (D4)

  private touchIdle(): void {
    if (this.idleHandle != null) this.clock.clearTimer(this.idleHandle)
    this.idleHandle = this.clock.setTimer(this.idleReleaseMs, () => {
      this.idleHandle = null
      this.teardown() // silent release — ensureWarm() re-establishes on the next press
    })
  }

  // MARK: Per-turn primitives (delegate to subclass frames)

  beginTurn(
    opts: { turnID?: VoiceTurnID; responseID?: VoiceResponseID; interrupting?: boolean } = {}
  ): void {
    this.touchIdle()
    this.activeIdentity =
      opts.turnID && opts.responseID ? { turnID: opts.turnID, responseID: opts.responseID } : null
    this.onBeginTurn(opts.interrupting ?? false)
  }

  appendAudio(pcm: Uint8Array): void {
    this.touchIdle()
    const b64 = bytesToBase64(pcm)
    if (!this.canAcceptInput()) {
      this.pendingAudio.push(b64)
      return
    }
    this.appendAudioFrame(b64)
  }

  commitTurn(): void {
    this.touchIdle()
    if (!this.canAcceptInput()) {
      this.pendingCommit = true
      return
    }
    this.commitTurnNow()
  }

  cancelTurn(): void {
    this.touchIdle()
    this.pendingAudio = []
    this.pendingCommit = false
    this.activeIdentity = null
    this.onCancelTurn()
  }

  sendToolResult(callId: string, name: string, output: string): void {
    this.touchIdle()
    this.onSendToolResult(callId, name, output)
  }

  // MARK: Emit helpers (subclass → events, never logging PII)

  protected send(json: object): void {
    const socket = this.socket
    if (socket === null) return
    // Drop a control frame that races the socket still CONNECTING. A slow-warm
    // barge-in cancel (`cancelTurn` → the provider's `input_audio_buffer.clear` /
    // Gemini activity-end) can fire before the socket opened; a real
    // `WebSocket.send` throws `InvalidStateError` in any non-OPEN state and would
    // escape `send()`. Dropping is safe: nothing was sent on this socket yet, so
    // there is nothing to cancel, and the session-setup frame is sent from
    // `onSocketOpen` where readyState is provably OPEN. A fake without a readyState
    // (undefined) is treated as sendable — unchanged for existing tests.
    if (socket.readyState !== undefined && socket.readyState !== WEBSOCKET_OPEN) return
    socket.send(JSON.stringify(json))
  }

  protected flushPendingAudio(): void {
    if (!this.canAcceptInput()) return
    const buffered = this.pendingAudio
    this.pendingAudio = []
    for (const b64 of buffered) this.appendAudioFrame(b64)
  }

  /** Decode base64 spoken PCM and play through the existing pcmPlayer (D3). */
  protected playAudio(b64: string): void {
    if (b64.length === 0) return
    this.player?.enqueuePcm16(base64ToBytes(b64))
  }

  /** Barge-in: drop everything buffered in the player immediately. */
  protected clearPlayback(): void {
    this.player?.clear()
  }

  /** Turn boundary: play any queued sub-cushion tail instead of withholding it. */
  protected flushPlayback(): void {
    this.player?.flush()
  }

  protected emitInputTranscript(
    text: string,
    isFinal: boolean,
    identity?: HubEventIdentity | null
  ): void {
    this.events.onInputTranscript?.(text, isFinal, identity ?? this.activeIdentity)
  }

  protected emitAssistantText(
    text: string,
    isFinal: boolean,
    identity?: HubEventIdentity | null
  ): void {
    if (text.length === 0 && !isFinal) return
    this.events.onAssistantText?.(text, isFinal, identity ?? this.activeIdentity)
  }

  protected emitToolRequest(
    call: { name: string; callId: string; argumentsJSON: string },
    identity?: HubEventIdentity | null
  ): void {
    this.events.onToolRequest?.(call, identity ?? this.activeIdentity)
  }

  protected emitTurnDone(identity?: HubEventIdentity | null): void {
    this.events.onTurnDone?.(identity ?? this.activeIdentity)
  }

  protected handleError(message: string, retryable: boolean, closeCode?: number): void {
    if (this.errored) return
    this.errored = true
    const reject = this.warmReject
    this.warmReject = null
    this.warmResolve = null
    this.warmPromise = null
    this.events.onError?.(message, retryable, closeCode)
    // teardown() closes the socket/player; guard against re-entrant error.
    this.teardown()
    reject?.(new Error(message))
  }

  // MARK: Provider hooks

  /** Connection URL + WS subprotocols. */
  protected abstract connectSpec(): { url: string; protocols?: string[] }
  /** The one-time session-config frame sent right after socket open. */
  protected abstract sessionSetupFrame(): object
  /** Parse one decoded provider message. Call `markReady`/emit helpers. */
  protected abstract handleProviderMessage(obj: Record<string, unknown>): void
  /** Whether the provider can accept mic input right now (Gemini needs its
   *  activity window open; OpenAI only needs the socket). */
  protected abstract canAcceptInput(): boolean
  /** Send one mic PCM frame (already base64). Precondition: `canAcceptInput`. */
  protected abstract appendAudioFrame(b64: string): void
  /** Provider `beginTurn` frames (Gemini activityStart / OpenAI barge-in cancel). */
  protected abstract onBeginTurn(interrupting: boolean): void
  /** Provider `commit` frames. Precondition: `canAcceptInput`. */
  protected abstract commitTurnNow(): void
  /** Provider `cancel`/abandon frames (keep the socket). */
  protected abstract onCancelTurn(): void
  /** Provider tool-result frames. */
  protected abstract onSendToolResult(callId: string, name: string, output: string): void
  /** Provider-specific flush at markReady (Gemini deferred activityStart). */
  protected abstract onProviderReady(): void
  /** Clear all per-connection provider flags on teardown. */
  protected abstract resetProviderState(): void
}
