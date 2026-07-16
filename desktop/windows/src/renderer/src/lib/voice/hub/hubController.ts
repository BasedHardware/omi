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
import { mintRealtimeToken, MintError } from '../tokenMint'
import type { VoiceProvider } from '../sessionMachine'
import type { VoiceSessionID, VoiceTurnID, VoiceResponseID } from '../turn/voiceTurnMachine'
import { GeminiHubSession } from './geminiHubSession'
import { OpenAiHubSession } from './openaiHubSession'
import type { HubEventIdentity, HubSession, HubSessionEvents } from './hubSession'
import {
  classifyHubClose,
  consumesStrike,
  HUB_IDLE_TEARDOWN_THRESHOLD_MS,
  type HubCloseCategory
} from './hubClose'

// MARK: - Language resolution

/** The languages the model should assume the user speaks. Prefer the explicit
 *  `voiceLanguages` candidates; fall back to the single `language` pref (macOS
 *  falls back to the system locale) so the imperative language line still renders
 *  even before a `voiceLanguages` UI writer lands. */
function resolveVoiceLanguages(prefs: { voiceLanguages?: string[]; language?: string }): string[] {
  if (prefs.voiceLanguages && prefs.voiceLanguages.length > 0) return prefs.voiceLanguages
  return prefs.language ? [prefs.language] : []
}

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
  /** Read the current voice continuity seed for the shared thread (the kernel tail,
   *  source-tagged). Injected so the controller stays hermetic; the host wires it to
   *  the `voiceHub:getSeedContext` IPC. Absent ⇒ the seed stays empty (today's
   *  behavior). Its result feeds the default `buildInstructions`'
   *  `topLevelConversationContext`, refreshed via a full reconnect when stale. */
  fetchSeed?: () => Promise<{ context: string; idempotencyKeys: string[] }>
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

/** Thrown by `createAndWarm` when a `teardownSession` bumped the warm generation
 *  while the warm was in flight: the result is discarded (never installed) rather
 *  than left as an orphaned socket re-warming on a now-disabled hub (M1). Callers
 *  swallow it exactly like the A7c reconnect reject — it is not a surfaced error. */
class HubWarmAbortedError extends Error {
  constructor() {
    super('hub warm aborted by teardown')
    this.name = 'HubWarmAbortedError'
  }
}

export class HubController {
  private readonly events: HubControllerEvents
  private readonly resolveProvider: () => VoiceProvider
  private readonly buildInstructions: () => string
  private readonly fetchSeed?: () => Promise<{ context: string; idempotencyKeys: string[] }>
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
  /** Monotonic warm generation, bumped by every `teardownSession`. An in-flight
   *  `createAndWarm` captures it at the START and, at each commit point (after the
   *  mint, after the connect), discards its result if the generation moved — so a
   *  teardown that interleaves a warm can't leave an orphaned socket re-warming on a
   *  now-disabled hub (M1). Only diverges when a teardown straddles a warm; the
   *  normal no-teardown path is unaffected, so coalescing semantics are unchanged. */
  private warmGeneration = 0

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

  // A7c cross-provider failover (item D — ported from macOS RealtimeHubController) ---
  /** Failover chain: when the effective (primary) provider's ephemeral-token mint
   *  fails in a provider-scoped way (unconfigured / quota / auth / outage), warm the
   *  OTHER realtime provider once before giving up to the batch cascade. `null` = on
   *  the primary; non-null = the provider we failed over TO (Mac `fallbackProvider`).
   *  Reset back to the primary only on a proven-good signal — a socket that survives
   *  past the idle window (Mac :3585), NOT on every connect or completed turn. */
  private fallbackProvider: VoiceProvider | null = null
  /** Reason recorded on the failover switch; cleared once the alternate connects
   *  (recovered) so the recovered event fires exactly once (Mac `pendingFailoverReason`). */
  private pendingFailoverReason: string | null = null

  // A7c wake / zombie-session refresh (item E — ported from macOS RealtimeHubController) ---
  /** A wake/unlock refresh that arrived mid-turn is deferred here so we never tear
   *  down a live turn, then applied once the turn terminates (Mac
   *  `pendingSessionRefreshReason` / `applyPendingSessionRefreshIfIdle`). */
  private pendingRefreshReason: string | null = null

  // Continuity seed (PR-B — the <recent_top_level_conversation> block) --------------
  /** The seed string the current/next session's instruction is built with. Empty
   *  until the first refresh finds prior turns. Staged for the next `buildInstructions`. */
  private seedContext = ''
  /** Idempotency keys the warm session ALREADY reflects (seeded-in on its build +
   *  produced live). A fresh snapshot carrying a key NOT in here is an unseen turn
   *  (typically a typed turn) → the session is stale and reconnects. Self-produced
   *  hub turns are added via `markSeedKeyProduced` so they never look unseen (thrash
   *  guard: without it, every hub turn would make the next one reconnect). */
  private knownSeedKeys = new Set<string>()
  /** A seed refresh that arrived mid-turn is deferred (never reconnect a live turn),
   *  then applied on termination — mirrors the wake-refresh defer above. */
  private pendingSeedRefresh = false

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
    this.fetchSeed = options.fetchSeed
    this.buildInstructions =
      options.buildInstructions ??
      (() =>
        buildVoiceSystemInstruction({
          aboutUser: getAboutUserCard(),
          // The kernel continuity seed (PR-B): recent typed/voice turns of the shared
          // thread, so a realtime session isn't blind to the typed conversation.
          topLevelConversationContext: this.seedContext,
          userLanguages: resolveVoiceLanguages(getPreferences())
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
    this.clearTimer =
      options.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>))
  }

  // MARK: Warm (idempotent, eager-callable)

  /** Open (or reuse) the warm hub socket for the currently-effective provider.
   *  Idempotent: a no-op that resolves to the live session id when already warm on
   *  the same provider, and coalesces with an in-flight warm. */
  ensureWarm(): Promise<VoiceSessionID> {
    if (this.warming) return this.warming
    const provider = this.effectiveProvider()
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

  /** The realtime provider to actually warm: the failover pick if we've switched to
   *  it, otherwise the user/Auto-resolved one (Mac `effectiveProvider`). */
  private effectiveProvider(): VoiceProvider {
    return this.fallbackProvider ?? this.resolveProvider()
  }

  private async createAndWarm(provider: VoiceProvider): Promise<VoiceSessionID> {
    // Capture the generation this warm belongs to. A teardownSession() that runs at
    // any await point below bumps it, and the commit-point checks then discard this
    // warm instead of installing an orphaned socket (M1).
    const gen = this.warmGeneration
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

      // Mint for the effective provider; on a provider-scoped mint failure, fail over
      // to the OTHER provider once before giving up (Mac mintAndConnect :1176-1234).
      // The loop runs at most twice: `failoverOnMintFailure` returns a provider only on
      // the null→alternate transition, so the once-per-chain guard bounds it.
      let activeProvider = provider
      let token: string
      for (;;) {
        try {
          token = await this.mintToken(activeProvider)
          break
        } catch (e) {
          const alternate = this.failoverOnMintFailure(e, activeProvider)
          if (alternate === null) throw e // not provider-scoped, or already failed over
          activeProvider = alternate
        }
      }
      // A teardownSession() straddled the mint (e.g. the wake-deferred refresh kicked
      // this warm off, then a kill-switch-off / sign-out dropped the hub while minting —
      // at which point `this.session` was still null so the teardown could not cancel
      // this not-yet-constructed session). Bail BEFORE building a session: nothing was
      // opened yet, so there is nothing to close, just discard the token.
      if (this.warmGeneration !== gen) throw new HubWarmAbortedError()
      const instructions = this.buildInstructions()
      const session = this.createSession({
        provider: activeProvider,
        token,
        instructions,
        events: this.sessionEvents()
      })
      this.session = session
      this.sessionProvider = activeProvider

      // A turn that began before the session existed (cold press, no summon) now
      // gets its provider begin frames.
      if (this.pendingBegin && this.pendingBegin.turnID === this.activeTurnID) {
        const begin = this.pendingBegin
        this.pendingBegin = null
        session.beginTurn(begin)
      }

      await session.ensureWarm()
      // A teardownSession() interleaved between the warm resolving (markReady fired
      // onConnected, so `warmReject` was already cleared — the session was torn down but
      // NOT rejected) and this continuation. Discard the just-connected session: close
      // its socket so it does not leak, and do NOT touch `this.session`/`this.sessionID`
      // (teardownSession already cleared them; a newer warm would own them). A teardown
      // DURING the connect await instead rejects the session's warm promise, so that
      // path throws above and never reaches here. `teardown()` is idempotent, so a
      // double close (teardownSession already closed it) is safe.
      if (this.warmGeneration !== gen) {
        session.teardown()
        throw new HubWarmAbortedError()
      }
      // onConnected (wired below) set `sessionID` synchronously inside markReady,
      // before this promise resolves.
      if (this.sessionID === null) throw new Error('hub session connected without a session id')
      return this.sessionID
    } finally {
      this.warming = null
    }
  }

  /** Decide the failover response to a mint failure (Mac `failoverToAlternateProvider`
   *  gated by the mint-failure classification). Returns the alternate provider to warm
   *  next, or `null` to give up (the error surfaces → the host drops this turn to the
   *  batch cascade, exactly as today). Once-per-chain: emits `degraded` on the switch
   *  to the alternate, and `exhausted` when the alternate ALSO fails (both down). */
  private failoverOnMintFailure(e: unknown, from: VoiceProvider): VoiceProvider | null {
    const failure = e instanceof MintError ? e.failure : null
    // Only a provider-scoped failure (unconfigured / quota / auth / outage) is worth the
    // other lane; a session-wide failure (401/402/403) surfaces unchanged.
    if (!failure?.tryOtherProvider) return null
    const alternate: VoiceProvider = from === 'openai' ? 'gemini' : 'openai'
    if (this.fallbackProvider !== null) {
      // Already failed over once this chain → the alternate is down too. Give up to the
      // cascade (Mac's guard-fail branch). One shared fallback event, closed enums.
      trackEvent('fallback_triggered', {
        component: 'realtime_hub',
        from: this.fallbackProvider,
        to: 'none',
        reason: 'provider_unavailable',
        outcome: 'exhausted'
      })
      return null
    }
    this.fallbackProvider = alternate
    this.pendingFailoverReason = 'provider_unavailable'
    trackEvent('fallback_triggered', {
      component: 'realtime_hub',
      from,
      to: alternate,
      reason: 'provider_unavailable',
      outcome: 'degraded'
    })
    return alternate
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
    // Invalidate any in-flight ensureWarm: a warm that was minting or connecting when
    // this explicit drop happened must discard its result at its next commit point
    // rather than install an orphaned socket on the now-torn-down hub (M1). Every
    // explicit drop is a new generation; bumping when no warm is in flight is harmless.
    this.warmGeneration += 1
    // An explicit drop (kill-switch off / sign-out) must NOT auto-re-warm, and it is a
    // clean reset — cancel any pending backoff and clear the strike budget.
    this.cancelReconnect()
    this.reconnectStrikes = 0
    // An explicit drop also cancels any wake refresh that was deferred behind a turn —
    // re-warming a hub that was just told to close (kill-switch off / sign-out) is wrong.
    this.pendingRefreshReason = null
    const s = this.session
    this.session = null
    this.sessionProvider = null
    this.sessionID = null
    this.connectedAt = null
    s?.teardown()
  }

  /** A7c item E — the OS suspended/locked and resumed: while suspended the OS likely
   *  killed the warm TCP socket, so the next PTT press would commit onto a zombie
   *  session (no reply, no fallback, hang). Proactively drop the possibly-dead socket
   *  and re-warm so the first press after wake is warm. Ported from macOS
   *  RealtimeHubController `requestSessionRefresh`.
   *
   *  Only acts when idle — a live session exists, no active turn, no connect already in
   *  flight (Mac: "neither mid-reply nor mid-mint") — so it never interrupts a turn nor
   *  races an in-flight warm (which is already building a fresh socket anyway). Mid-turn
   *  it DEFERS the reason and re-warms once the turn terminates. It NEVER force-warms a
   *  hub with no session (disabled / signed out): that gate mirrors eager-warm, so wake
   *  can't open a socket the kill-switch closed. No telemetry — a wake refresh of an idle
   *  socket is not a fallback (Mac only logs it). */
  requestSessionRefresh(reason: string): void {
    // Nothing to refresh when the hub isn't warm — never open a socket for a
    // disabled / signed-out hub (Mac `guard session != nil`).
    if (this.session === null) return
    // Mid-turn: defer to the turn's termination so we never tear down a live turn.
    if (this.activeTurnID !== null) {
      this.pendingRefreshReason = reason
      return
    }
    // Mid-connect: a warm is already in flight building a fresh socket — let it finish
    // rather than race it (no need to defer; the in-flight warm is what we'd want anyway).
    if (this.warming !== null) return
    // Idle + warm: drop the (possibly dead) socket and rebuild. teardownSession forces
    // session=null so ensureWarm rebuilds instead of treating the stale socket as warm;
    // swallow the re-warm reject exactly like the A7c reconnect path.
    this.teardownSession()
    void this.ensureWarm().catch(() => {})
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

    // idempotent safety; eager summon usually warmed already. Swallow the reject like
    // the A7c reconnect path: this warm can reject on a mint failure or a teardown-abort
    // (M1), and the reducer's warm-wait / cascade timeout owns the degradation — an
    // unhandled rejection here would be a false crash signal.
    void this.ensureWarm().catch(() => {})
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
    // A wake/refresh that arrived mid-turn was deferred (Mac
    // applyPendingSessionRefreshIfIdle); now idle, honor it. requestSessionRefresh
    // re-checks the gates (session present, no in-flight connect) before re-warming.
    if (this.pendingRefreshReason !== null) {
      const reason = this.pendingRefreshReason
      this.pendingRefreshReason = null
      this.requestSessionRefresh(reason)
    }
    // A seed refresh deferred behind this turn now runs idle (may reconnect if a
    // typed turn appeared while this voice turn was live).
    if (this.pendingSeedRefresh) {
      this.pendingSeedRefresh = false
      this.refreshSeedContext()
    }
  }

  // MARK: Continuity seed (PR-B)

  /** The warm session saw this turn LIVE (it produced it) — record its id as known
   *  so a later seed refresh doesn't count it as an unseen turn and reconnect. */
  markSeedKeyProduced(key: string): void {
    if (key) this.knownSeedKeys.add(key)
  }

  /** Refresh the continuity seed from the kernel and, if it carries a turn the warm
   *  session hasn't seen (e.g. a typed turn), rebuild the session so the NEXT voice
   *  turn is seeded with it (macOS refreshes the seed via a full reconnect when
   *  stale — the hub instruction is single-shot, so there is no mid-session patch).
   *  Idle-only: deferred while a turn is active. Fire-and-forget. */
  refreshSeedContext(): void {
    void this.doRefreshSeedContext().catch(() => {})
  }

  private async doRefreshSeedContext(): Promise<void> {
    if (!this.fetchSeed) return
    // Never tear a live turn's session down mid-turn — defer to its termination.
    if (this.activeTurnID !== null) {
      this.pendingSeedRefresh = true
      return
    }
    let snapshot: { context: string; idempotencyKeys: string[] }
    try {
      snapshot = await this.fetchSeed()
    } catch {
      return
    }
    // A turn began while the fetch was in flight — abandon and let its terminal
    // re-trigger, so we never reconnect underneath an active turn.
    if (this.activeTurnID !== null) {
      this.pendingSeedRefresh = true
      return
    }
    const hasUnseenTurn = snapshot.idempotencyKeys.some((key) => !this.knownSeedKeys.has(key))
    const changed = snapshot.context !== this.seedContext
    if (!hasUnseenTurn && !changed) return
    // Stage the fresh seed for the next session build either way.
    this.seedContext = snapshot.context
    if (hasUnseenTurn) {
      // The warm session is missing a turn — rebuild it so it carries the seed. The
      // rebuilt session reflects exactly the fresh snapshot's keys.
      this.knownSeedKeys = new Set(snapshot.idempotencyKeys)
      if (this.session !== null) {
        this.teardownSession()
        void this.ensureWarm().catch(() => {})
      }
    } else {
      // Text changed but every key is already reflected (e.g. our own turn's
      // assistant row landing) — no reconnect; just keep the keys marked known.
      for (const key of snapshot.idempotencyKeys) this.knownSeedKeys.add(key)
    }
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
    // A7c failover recovered: the alternate provider connected → the failover restored
    // full realtime UX. Fire the shared `recovered` event exactly once (clear the reason,
    // Mac :2553-2564). `fallbackProvider` itself stays set until a proven-good idle-close
    // (Mac :3585), so we don't flap back to a still-broken primary after every connect.
    if (
      this.fallbackProvider !== null &&
      this.pendingFailoverReason !== null &&
      this.sessionProvider === this.fallbackProvider
    ) {
      trackEvent('fallback_triggered', {
        component: 'realtime_hub',
        from: this.resolveProvider(),
        to: this.fallbackProvider,
        reason: this.pendingFailoverReason,
        outcome: 'recovered'
      })
      this.pendingFailoverReason = null
    }
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

  // MARK: A7c reconnect policy (strike-bounded re-warm + idle-teardown survival)

  /** Decide whether/how to re-warm after a socket close. A socket that survived past
   *  the idle window proved the endpoint works, so it refreshes the strike budget
   *  (Mac: aliveFor>60 → strikes=0). A genuine FAILURE re-warms bounded by the budget
   *  so a dead endpoint (revoked token, provider outage) isn't hammered (item B).
   *
   *  Item C (keep an idle user warm): what actually does the work for real Gemini is
   *  the aliveFor>60 RESET above. Live traffic shows Gemini idle-closes at ~117 s with
   *  a NON-1008 code → classified `transient` (consumes a strike), but because the
   *  socket lived >60 s the budget is reset to 0 first, so strikes just oscillate 0↔1
   *  and the hub re-warms indefinitely — the next press takes the warm lane
   *  (`hubWarmWait`), not a cold cascade. The `expected_idle_teardown` strike-exemption
   *  is the belt-and-suspenders path for a true 1008 idle close; it is rarely hit in
   *  practice. Both routes keep the idle user warm. */
  private scheduleReconnectForClose(category: HubCloseCategory, aliveForMs: number): void {
    if (aliveForMs > HUB_IDLE_TEARDOWN_THRESHOLD_MS) {
      this.reconnectStrikes = 0
      // A socket that survived past the idle window proved the endpoint works — return
      // to the Auto/primary provider on the next warm and clear any pending failover
      // (Mac RealtimeHubController :3583-3586). Only this proven-good signal resets the
      // failover; a completed turn or a bare connect does NOT (we stay on the working
      // alternate rather than flap back to a still-broken primary every turn).
      this.fallbackProvider = null
      this.pendingFailoverReason = null
    }
    if (consumesStrike(category)) {
      if (this.reconnectStrikes >= HubController.MAX_RECONNECT_STRIKES) {
        // Budget spent: the re-warm circuit is now OPEN and we stop rebuilding a dead
        // endpoint. This is the silent post-commit death — the warm socket is gone for
        // good (until an explicit summon `warm()` or sign-out+in resets the budget), so
        // every subsequent PTT press falls to the batch cascade, which still returns a
        // valid reply and is therefore INDISTINGUISHABLE from a hub turn. Surfacing it is
        // mandatory (AGENTS.md: silent UX healing is fine, silent ops is not). One shared
        // fallback event, closed enums, no new counter — emitted once as the circuit trips
        // (re-warm has stopped, so no new close can re-emit until the next summon episode).
        trackEvent('fallback_triggered', {
          component: 'ptt_cascade',
          from: 'hub',
          to: 'none',
          reason: 'circuit_open',
          outcome: 'exhausted'
        })
        return
      }
      this.reconnectStrikes += 1
    }
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
