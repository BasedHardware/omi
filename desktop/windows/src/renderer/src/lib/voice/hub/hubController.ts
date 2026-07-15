// Warm-hub controller (Track 2 / A5 PR-5).
//
// The minimal Windows-native replacement for the pieces of macOS
// `RealtimeHubController.swift` that survive after the reducer took over turn
// fencing. Mac's controller is a FACADE whose overlapping-response queue the
// reducer (PR-1) now owns authoritatively, so it is deliberately NOT ported
// wholesale (orchestrator ruling). This module provides ONLY the five
// responsibilities §C.5 leaves to Windows:
//
//   1. `ensureWarm()` — resolve the effective provider (A8), assemble the session
//      instructions + <about_user> card (A9), mint an ephemeral token, and warm
//      the correct provider hub session (PR-4). Idempotent; eager-callable (bar
//      summon wiring is PR-6).
//   2. The reducer-facing warm-wait PCM buffer + flush. PCM captured while the
//      socket is still connecting is buffered HERE (not in the session), then on
//      hub-ready flushed into the session, or — on the reducer's 1 s `hubWarm`
//      timeout — handed to the batch cascade WITHOUT terminating the turn (the
//      graceful cold-press degradation; "never worse than today").
//   3. The four per-turn primitives (begin / append / commit / cancel), turn-ID
//      fenced so a superseded turn's late call is inert.
//   4. `voiceTurnDidTerminate(turnID)` — release per-turn state but KEEP the warm
//      socket (that is the entire point of a warm hub).
//   5. The connect/error surface A7c (reconnect / failover / wake) will consume:
//      `onConnected(sessionID)` + `onError({ reason, aliveForMs })`. A5 builds the
//      seam only — no retry timers, strike counters, or failover policy here.
//
// This module is NOT wired into the live PTT path in PR-5 (PR-6 does that behind
// the `pttHubEnabled` kill-switch, default OFF). Every collaborator — provider
// session, token mint, provider resolver, instruction builder, clock — is an
// injected seam so the whole controller is exercised hermetically against fakes.
//
// Division of buffering with the session (do NOT duplicate): the session
// (`BaseHubSession`) has its OWN pre-open buffer for ITS connect. The controller
// WITHHOLDS warm-wait PCM from the session entirely until it knows whether the
// hub or the cascade wins, so the session's pre-open buffer stays dormant on this
// path and a fallen-back turn's audio can never leak into the next hub turn.

import { trackEvent } from '../../analytics'
import { getPreferences } from '../../preferences'
import {
  resolveEffectiveVoiceProvider,
  refreshIfStale as refreshAutoModelIfStale
} from '../autoModelSelector'
import { getAboutUserCard, refreshAboutUserCard } from '../aboutUser'
import { buildVoiceSystemInstruction } from '../systemInstruction'
import { mintRealtimeToken } from '../tokenMint'
import type { VoiceProvider } from '../sessionMachine'
import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import { GeminiHubSession } from './geminiHubSession'
import { OpenAiHubSession } from './openaiHubSession'
import type { HubEventIdentity, HubSession, HubSessionEvents } from './hubSession'
import { classifyHubClose, HUB_IDLE_TEARDOWN_THRESHOLD_MS, type HubCloseCategory } from './hubClose'

// MARK: - Public surface

/** The PCM handed to the cascade when the hub loses the 1 s warm race. Frozen at
 *  the instant of hand-off; `committed` records whether the user had already
 *  released (so the cascade knows to finalize rather than await more audio). */
export type HubCascadeHandoff = {
  readonly frames: readonly Uint8Array[]
  readonly committed: boolean
}

/** A fatal session error, enriched with `aliveForMs` — the A7c seam that lets a
 *  future reconnect policy tell a flapping socket (strike) from a long-lived one
 *  (reset strikes). 0 when the socket never finished connecting. */
export type HubControllerError = {
  readonly reason: string
  readonly retryable: boolean
  readonly aliveForMs: number
}

/** Everything the controller surfaces to its host (PR-6). The content events are
 *  a straight pass-through of the session's; connect/error are enriched for A7c;
 *  `onCascadeHandoff` is the warm-wait → cascade degradation. */
export type HubControllerEvents = {
  onConnected?: (sessionID: VoiceSessionID) => void
  onError?: (error: HubControllerError) => void
  onInputTranscript?: (text: string, isFinal: boolean, identity: HubEventIdentity | null) => void
  onAssistantText?: (text: string, isFinal: boolean, identity: HubEventIdentity | null) => void
  onSpeakingStart?: () => void
  onSpeakingEnd?: () => void
  onToolRequest?: (
    call: { name: string; callId: string; argumentsJSON: string },
    identity: HubEventIdentity | null
  ) => void
  onTurnDone?: (identity: HubEventIdentity | null) => void
  onCascadeHandoff?: (handoff: HubCascadeHandoff) => void
}

/** How the controller builds a provider session — injected so tests supply a fake
 *  and never touch a real WebSocket. */
export type HubSessionSpec = {
  provider: VoiceProvider
  token: string
  instructions: string
  events: HubSessionEvents
}

export type HubControllerOptions = {
  events?: HubControllerEvents
  /** A8 — collapse the 'auto' voice-provider setting to a concrete lane. */
  resolveProvider?: () => VoiceProvider
  /** A9 — assemble the per-session system instruction (persona + about_user). */
  buildInstructions?: () => string
  /** Mint one ephemeral token for the resolved provider. Fresh per `ensureWarm`. */
  mintToken?: (provider: VoiceProvider) => Promise<string>
  /** Construct the provider hub session. Default picks OpenAI/Gemini by provider. */
  createSession?: (spec: HubSessionSpec) => HubSession
  /** Output device for spoken audio; default = system default. */
  sinkId?: () => string | undefined
  /** Injectable wall clock for `aliveForMs` (tests use a fake). */
  now?: () => number
  /** Injectable one-shot timer for the A7c reconnect backoff (fake timers in tests).
   *  Defaults to `setTimeout`/`clearTimeout`. */
  setTimer?: (ms: number, fire: () => void) => unknown
  clearTimer?: (handle: unknown) => void
}

// MARK: - Controller

export class HubController {
  private readonly events: HubControllerEvents
  private readonly resolveProvider: () => VoiceProvider
  private readonly buildInstructions: () => string
  private readonly mintToken: (provider: VoiceProvider) => Promise<string>
  private readonly createSession: (spec: HubSessionSpec) => HubSession
  private readonly now: () => number
  private readonly setTimer: (ms: number, fire: () => void) => unknown
  private readonly clearTimer: (handle: unknown) => void

  private session: HubSession | null = null
  private sessionProvider: VoiceProvider | null = null
  private sessionID: VoiceSessionID | null = null
  private connectedAt: number | null = null
  /** In flight ensureWarm, so overlapping calls (summon + first press) coalesce. */
  private warming: Promise<VoiceSessionID> | null = null

  // A7c reconnect budget (ported from macOS RealtimeHubController) ---------------
  /** After this many consecutive FAILURE re-warms with no surviving session, stop
   *  re-warming so a dead endpoint (revoked token, provider outage) isn't hammered
   *  (Mac `maxReconnectStrikes`). Expected idle teardowns never spend a strike. */
  private static readonly MAX_RECONNECT_STRIKES = 5
  /** Backoff before a scheduled re-warm (Mac's 1.5 s `asyncAfter`). */
  private static readonly RECONNECT_BACKOFF_MS = 1500
  private reconnectStrikes = 0
  private reconnectPending = false
  private reconnectHandle: unknown = null

  // Per-turn state (all reset by voiceTurnDidTerminate) ------------------------
  private activeTurnID: VoiceTurnID | null = null
  /** Non-null ⇒ we are in the reducer's warm-wait and withholding PCM from the
   *  session (buffering it here for the hub-flush-or-cascade-handoff decision). */
  private warmBuffer: Uint8Array[] | null = null
  /** The user released while still warm-waiting — replay the commit after flush. */
  private warmCommitted = false
  /** The warm-wait buffer was handed to the cascade — the hub side is abandoned
   *  for this turn, so later primitives are inert until the next turn. */
  private handedOff = false
  /** A `beginTurn` that arrived before the session object existed (cold press with
   *  no prior summon); applied once `createSession` runs. */
  private pendingBegin: {
    turnID: VoiceTurnID
    responseID?: VoiceResponseID
    interrupting: boolean
  } | null = null

  constructor(options: HubControllerOptions = {}) {
    this.events = options.events ?? {}
    this.resolveProvider = options.resolveProvider ?? resolveEffectiveVoiceProvider
    this.buildInstructions =
      options.buildInstructions ??
      (() =>
        buildVoiceSystemInstruction({
          aboutUser: getAboutUserCard(),
          userLanguages: getPreferences().voiceLanguages ?? []
        }))
    this.mintToken =
      options.mintToken ?? ((provider) => mintRealtimeToken(provider).then((m) => m.token))
    const sinkId = options.sinkId
    this.createSession =
      options.createSession ??
      ((spec) => {
        const opts = {
          token: spec.token,
          instructions: spec.instructions,
          events: spec.events,
          sinkId: sinkId?.()
        }
        return spec.provider === 'openai' ? new OpenAiHubSession(opts) : new GeminiHubSession(opts)
      })
    this.now = options.now ?? (() => Date.now())
    this.setTimer = options.setTimer ?? ((ms, fire) => setTimeout(fire, ms))
    this.clearTimer = options.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  }

  // MARK: Warm (idempotent, eager-callable)

  /** Open (or reuse) the warm hub socket for the currently-effective provider.
   *  Idempotent: a no-op that resolves to the live session id when already warm on
   *  the same provider, and coalesces with an in-flight warm. */
  ensureWarm(): Promise<VoiceSessionID> {
    if (this.warming) return this.warming
    const provider = this.resolveProvider()
    if (
      this.session &&
      this.sessionProvider === provider &&
      this.session.isWarm() &&
      this.sessionID
    ) {
      return Promise.resolve(this.sessionID)
    }
    this.warming = this.createAndWarm(provider)
    return this.warming
  }

  private async createAndWarm(provider: VoiceProvider): Promise<VoiceSessionID> {
    try {
      // Refresh the daily A8 pick and the <about_user> card OFF the hot path — this
      // session uses whatever is cached now; the next one gets the fresh values.
      refreshAutoModelIfStale()
      refreshAboutUserCard()

      // Tear down a stale / other-provider session before minting a fresh token.
      if (this.session) {
        const stale = this.session
        this.session = null
        this.sessionProvider = null
        this.connectedAt = null
        stale.teardown()
      }

      const token = await this.mintToken(provider)
      const instructions = this.buildInstructions()
      const session = this.createSession({
        provider,
        token,
        instructions,
        events: this.sessionEvents()
      })
      this.session = session
      this.sessionProvider = provider

      // A turn that began before the session existed (cold press, no summon) now
      // gets its provider begin frames.
      if (this.pendingBegin && this.pendingBegin.turnID === this.activeTurnID) {
        const begin = this.pendingBegin
        this.pendingBegin = null
        session.beginTurn(begin)
      }

      await session.ensureWarm()
      // onConnected (wired below) set `sessionID` synchronously inside markReady,
      // before this promise resolves.
      if (this.sessionID === null) throw new Error('hub session connected without a session id')
      return this.sessionID
    } finally {
      this.warming = null
    }
  }

  isWarm(): boolean {
    return this.session?.isWarm() ?? false
  }

  /** Whether the resolved provider currently has a session object at all (warm or
   *  connecting). PR-6's route selection uses `isWarm()`; this is the coarser gate. */
  isAvailable(): boolean {
    return this.session !== null
  }

  /** PCM16 rate the host must resample mic frames to before `appendAudio`
   *  (OpenAI 24 k, Gemini 16 k). Null until a session exists. */
  requiredInputSampleRate(): number | null {
    return this.session?.requiredInputSampleRate ?? null
  }

  /** A7c seam: drop the warm socket (idle release / wake refresh / failover). A
   *  re-warm is `teardownSession()` then `ensureWarm()`; both are safe at any turn
   *  phase. Does NOT touch per-turn reducer state. */
  teardownSession(): void {
    // An explicit drop (kill-switch off / sign-out) must NOT auto-re-warm, and it is a
    // clean reset — cancel any pending backoff and clear the strike budget.
    this.cancelReconnect()
    this.reconnectStrikes = 0
    const s = this.session
    this.session = null
    this.sessionProvider = null
    this.sessionID = null
    this.connectedAt = null
    s?.teardown()
  }

  // MARK: The four per-turn primitives (turn-ID fenced)

  /** Start a PTT turn on the warm hub. Supersedes any prior turn (a barge-in
   *  `interrupting` begin drives the provider's in-flight-reply cancel). Buffers
   *  PCM locally when the socket is not yet warm (the reducer's warm-wait). */
  beginTurn(
    turnID: VoiceTurnID,
    opts: { responseID?: VoiceResponseID; interrupting?: boolean } = {}
  ): void {
    this.activeTurnID = turnID
    this.handedOff = false
    this.warmCommitted = false
    const begin = { turnID, responseID: opts.responseID, interrupting: opts.interrupting ?? false }

    // Warm-wait iff the socket is not ready: withhold PCM so it can still be handed
    // to the cascade if the hub loses the race. When already warm, audio streams
    // straight through and `warmBuffer` stays null.
    this.warmBuffer = this.session?.isWarm() ? null : []

    void this.ensureWarm() // idempotent safety; eager summon usually warmed already
    if (this.session) {
      this.session.beginTurn(begin)
    } else {
      // No session object yet (cold press, no prior summon) — apply on create.
      this.pendingBegin = begin
    }
  }

  /** Feed one mic PCM16 frame at `requiredInputSampleRate`. Buffered locally during
   *  warm-wait; inert once the turn has been handed to the cascade. */
  appendAudio(turnID: VoiceTurnID, pcm: Uint8Array): void {
    if (turnID !== this.activeTurnID || this.handedOff) return
    if (this.warmBuffer !== null) {
      this.warmBuffer.push(pcm)
      return
    }
    this.session?.appendAudio(pcm)
  }

  /** End the held turn and ask the model to respond. During warm-wait the commit is
   *  deferred: it replays after the flush on hub-ready, or the cascade owns finalize
   *  after a hand-off. */
  commitTurn(turnID: VoiceTurnID): void {
    if (turnID !== this.activeTurnID || this.handedOff) return
    if (this.warmBuffer !== null) {
      this.warmCommitted = true
      return
    }
    this.session?.commitTurn()
  }

  /** Abandon the current turn (silent tap / explicit cancel / non-preserving
   *  barge-in), keeping the warm socket. Discards any warm-wait buffer. */
  cancelTurn(turnID: VoiceTurnID): void {
    if (turnID !== this.activeTurnID) return
    this.warmBuffer = null
    this.warmCommitted = false
    this.session?.cancelTurn()
  }

  /** The reducer's 1 s `hubWarm` deadline fired: the hub lost the race. Hand the
   *  buffered PCM to the batch cascade and record the fail-open. The turn CONTINUES
   *  on the cascade — nothing here terminates it (the reducer keeps it alive). */
  handoffWarmWaitToCascade(turnID: VoiceTurnID): void {
    if (turnID !== this.activeTurnID || this.warmBuffer === null) return
    const frames = this.warmBuffer
    const committed = this.warmCommitted
    this.warmBuffer = null
    this.handedOff = true

    // Fail-open path — provider/mode changed (hub → cascade). Shared telemetry
    // contract (AGENTS.md): closed enums, no new counter, do not duplicate the
    // openai↔gemini mint fallback.
    trackEvent('fallback_triggered', {
      component: 'ptt_cascade',
      from: 'hub',
      to: 'omni_stt',
      reason: 'hub_warm_timeout',
      outcome: 'degraded'
    })
    this.events.onCascadeHandoff?.({ frames, committed })

    // Abandon the hub side of this turn cleanly (closes Gemini's activity window /
    // OpenAI's input buffer) while KEEPING the warm socket for the next turn.
    this.session?.cancelTurn()
  }

  /** The turn terminated (any reason). Release per-turn state so the next turn
   *  starts clean, but KEEP the warm socket — that is the whole point of a warm hub;
   *  only the 180 s idle timer or an explicit `teardownSession` closes it. */
  voiceTurnDidTerminate(turnID: VoiceTurnID): void {
    if (turnID !== this.activeTurnID) return
    this.activeTurnID = null
    this.warmBuffer = null
    this.warmCommitted = false
    this.handedOff = false
    this.pendingBegin = null
  }

  // MARK: Session event wiring (pass-through + connect/error enrichment)

  private sessionEvents(): HubSessionEvents {
    return {
      onConnected: (sessionID) => this.handleConnected(sessionID),
      onError: (message, retryable, closeCode) => this.handleError(message, retryable, closeCode),
      onInputTranscript: (text, isFinal, identity) =>
        this.events.onInputTranscript?.(text, isFinal, identity),
      onAssistantText: (text, isFinal, identity) =>
        this.events.onAssistantText?.(text, isFinal, identity),
      onSpeakingStart: () => this.events.onSpeakingStart?.(),
      onSpeakingEnd: () => this.events.onSpeakingEnd?.(),
      onToolRequest: (call, identity) => this.events.onToolRequest?.(call, identity),
      onTurnDone: (identity) => {
        // A completed turn proves the hub works — reset the strike budget (Mac :3328).
        this.reconnectStrikes = 0
        this.events.onTurnDone?.(identity)
      }
    }
  }

  private handleConnected(sessionID: VoiceSessionID): void {
    this.sessionID = sessionID
    this.connectedAt = this.now()
    // A live socket supersedes any pending reconnect backoff. NB: connecting alone does
    // NOT reset the strike budget (Mac parity) — only a PROVEN-good signal does (a
    // completed turn, or a socket that survives past the idle window). A socket that
    // connects then dies fast repeatedly must still exhaust its budget and stop.
    this.cancelReconnect()
    // Flush any PCM withheld during warm-wait into the now-ready session, in order,
    // then replay a deferred commit. The hub won the race.
    if (this.warmBuffer !== null && this.session) {
      const buffered = this.warmBuffer
      this.warmBuffer = null
      for (const frame of buffered) this.session.appendAudio(frame)
      if (this.warmCommitted) {
        this.warmCommitted = false
        this.session.commitTurn()
      }
    }
    this.events.onConnected?.(sessionID)
  }

  private handleError(message: string, retryable: boolean, closeCode?: number): void {
    const aliveForMs = this.connectedAt !== null ? Math.max(0, this.now() - this.connectedAt) : 0
    // Classify BEFORE forwarding: the forward drives the reducer's terminal, which
    // clears `activeTurnID`, so the turn-at-close-time must be captured first.
    const hadActiveTurn = this.activeTurnID !== null
    // The session tore itself down on error; drop our handle so ensureWarm rebuilds.
    this.session = null
    this.sessionProvider = null
    this.connectedAt = null
    const category = classifyHubClose({
      message,
      closeCode,
      aliveForMs,
      hasActiveTurn: hadActiveTurn
    })
    this.events.onError?.({ reason: message, retryable, aliveForMs })
    this.scheduleReconnectForClose(category, aliveForMs)
  }

  // MARK: A7c reconnect policy (strike-bounded re-warm)

  /** Decide whether/how to re-warm after a socket close. A genuine FAILURE re-warms
   *  bounded by the strike budget so a dead endpoint (revoked token, provider outage)
   *  isn't hammered. A socket that survived past the idle window proved the endpoint
   *  works, so it refreshes the budget (Mac: aliveFor>60 → strikes=0). An EXPECTED idle
   *  teardown is left to A7c item C (proactive idle re-warm). */
  private scheduleReconnectForClose(category: HubCloseCategory, aliveForMs: number): void {
    if (category === 'expected_idle_teardown') return
    if (aliveForMs > HUB_IDLE_TEARDOWN_THRESHOLD_MS) this.reconnectStrikes = 0
    if (this.reconnectStrikes >= HubController.MAX_RECONNECT_STRIKES) return
    this.reconnectStrikes += 1
    this.scheduleReWarm()
  }

  /** Arm the one-shot backoff (Mac's 1.5 s `asyncAfter`). Coalesced: a second close
   *  while one is pending is a no-op. Rebuilds only if nothing else re-warmed first. */
  private scheduleReWarm(): void {
    if (this.reconnectPending) return
    this.reconnectPending = true
    this.reconnectHandle = this.setTimer(HubController.RECONNECT_BACKOFF_MS, () => {
      this.reconnectHandle = null
      this.reconnectPending = false
      // A failed re-warm (e.g. a still-dead mint) is expected on this path — swallow
      // the rejection so it never surfaces as an unhandled promise; the next press
      // (or a socket close from a partial connect) drives the next attempt.
      if (this.session === null) void this.ensureWarm().catch(() => {})
    })
  }

  private cancelReconnect(): void {
    if (this.reconnectHandle !== null) {
      this.clearTimer(this.reconnectHandle)
      this.reconnectHandle = null
    }
    this.reconnectPending = false
  }
}
