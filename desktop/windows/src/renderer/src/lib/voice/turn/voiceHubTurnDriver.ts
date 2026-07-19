// The warm-hub PTT turn DRIVER (Track 2 / A5 PR-6b) — the cross-window ON-path.
//
// PR-6 landed the reducer (`voiceTurnMachine`), the coordinator, the host, the
// hub controller, and the output coordinator, but wired them to NO window. This
// driver is the finale: it mounts them in the MAIN renderer (Option A / decision
// D1 — `pcmPlayer` + `voiceController` are main-resident, so hub spoken audio
// plays locally with zero audio IPC) and turns three low-rate control messages
// from the bar (begin / end / cancel) into a fully-driven voice turn.
//
// The kill-switch is structural, not a runtime `if`: this driver only does work on
// a `begin`, and the bar sends `begin` ONLY when `pttHubEnabled` is on
// (`selectPttRoute` is also gated). When the flag is off the bar runs its local
// cascade exactly as today and this driver sits idle — so the flag-off path is
// byte-for-byte unchanged.
//
// What it owns, per turn:
//   * `coordinator.begin('hold')` → the reducer start; then `selectPttRoute`
//     picks hub / hubWarmWait / omniSTT and it emits `selectRoute`.
//   * Capture ownership: it calls `startCapture` FROM THE MAIN RENDERER, so the
//     capture window routes owned PCM (`ptt-chunk`) to main (captureBridge tags
//     the owner by sender id). Frames feed the hub (`appendAudio`, resampled) and
//     are retained for the cascade / fallback.
//   * Release → `finalize` + `hubController.commitTurn` (hub) or a batch
//     transcription (cascade). Provider/session events map back to reducer events
//     so the turn advances to `success`. Spoken audio never crosses the driver —
//     the `HubSession` plays it through its own `pcmPlayer` (D3).
//   * Barge-in: the interrupt seam (`interruptCurrentResponse`) fires at every
//     `begin` (Mac's `PushToTalkManager.startListening` parity), and a superseding
//     hold begins the hub turn `interrupting:true` so the provider cancels its
//     in-flight reply.
//   * A4 system-audio duck at capture start; the host guarantees the single
//     restore per turn on terminal.
//   * A low-rate orb projection (phase + loudness) to the bar — NO per-frame audio.
//
// Every collaborator is an injected seam so the whole driver is exercised
// hermetically against fakes.

import { trackEvent as defaultTrackEvent } from '../../analytics'
import { getPreferences } from '../../preferences'
import { gateDecision, voicedStats, type AudioStats } from '../../ptt/gate'
import { HINT_MS } from '../../ptt/constants'
import type { PttCapture, PttCaptureOptions } from '../../ptt/capture'
import {
  muteSystemAudioForHubCapture as defaultMuteForCapture,
  restoreSystemAudio as defaultRestoreSystemAudio
} from '../../ptt/systemAudioMute'
import type { VoiceHubBarState } from '../../../../../shared/types'
import type { HubController, HubControllerEvents } from '../hub/hubController'
import { VoiceOutputCoordinator } from './voiceOutputCoordinator'
import { selectPttRoute, VoiceTurnHost, type VoiceTurnHostDeps } from './voiceTurnHost'
import { VoiceTurnCoordinator, type VoiceTurnDeadlineScheduling } from './voiceTurnCoordinator'
import {
  IDLE_PROJECTION,
  type VoiceCaptureID,
  type VoiceLeaseID,
  type VoiceSessionID,
  type VoiceToolCallID,
  type VoiceTurnEvent,
  type VoiceTurnID,
  type VoiceTurnRoute,
  type VoiceTurnUIProjection
} from './voiceTurnMachine'

/** The capture window's PCM16 rate (`capture/pttGraph.ts` `SAMPLE_RATE`). Hub
 *  input is resampled from here to the provider rate (OpenAI 24 k / Gemini 16 k). */
export const CAPTURE_SAMPLE_RATE = 16000

/** How often (ms) the throttled orb-level projection is pushed to the bar. Reducer
 *  transitions publish immediately; only the continuous loudness is rate-limited. */
const ORB_PUBLISH_INTERVAL_MS = 33

/** Cap on the retained cascade PCM buffer (~ the same order as the PTT machine's
 *  pending-stream cap) so a very long hold on the cascade route can't grow without
 *  bound before the batch POST. */
const CASCADE_BUFFER_MAX_BYTES = 16 * 1024 * 1024

/** Release watchdog (2026-07-18 "stuck on Listening" wedge): once the user has
 *  RELEASED (end/cancel), no turn may hold the machine forever. The reducer's own
 *  deadlines bound every post-release phase — this is the belt-and-braces layer
 *  above them, for the wedge class where the deadline machinery itself was broken
 *  (e.g. a collaborator throw skipped the scheduling effect). Generous: it must
 *  comfortably outlast the slowest legitimate pre-response dwell (the cascade's
 *  20 s batch-transcription budget). It never fires for phases that legitimately
 *  run long (playing / tools) — see `fireReleaseWatchdog`'s phase check. */
export const RELEASE_WATCHDOG_MS = 45_000

/** The watchdog's user-facing hint (mirrors the local PTT machine's watchdog copy). */
export const RELEASE_WATCHDOG_HINT = 'Voice input timed out — try again'

const ZERO_STATS: AudioStats = { totalSec: 0, voicedSec: 0, peak: 0 }

export type VoiceHubTurnDriverDeps = {
  /** Build the warm-hub controller with the driver's event wiring. Production:
   *  `(events) => new HubController({ events })`; tests pass a fake. */
  createHub: (events: HubControllerEvents) => HubController
  /** Barge-in: stop the cascade/TTS spoken reply. Production = `voiceController`
   *  `interruptCurrentResponse`. Also the host's `stopPlayback` effect target. */
  interruptPlayback: (leaseID: VoiceLeaseID | null) => void
  /** Push the projected orb state to the bar (main → bar IPC). */
  publishState: (state: VoiceHubBarState) => void
  /** Start the mic capture OWNED BY THIS (main) renderer. Production =
   *  `startPttCapture` — issued from main so the capture window routes owned PCM here. */
  startCapture: (opts: PttCaptureOptions) => Promise<PttCapture>
  /** Batch-transcribe retained PCM (cascade route + hub warm-wait fallback).
   *  Production wraps `transport.batchTranscribe`. */
  transcribe: (pcm: Int16Array) => Promise<string>
  /** Commit the final user transcript to the chat engine (the main window's send).
   *  CASCADE route only — this re-answers via the LLM (fromVoice ⇒ spoken reply).
   *  `turnId` is the per-press id; threaded so the cascade user-turn kernel record
   *  shares the key a hub-native record would use (INV-CHAT-1 double-record guard). */
  onFinalText: (text: string, turnId?: string) => void
  /** Record a COMPLETED HUB turn (user transcript + assistant reply) into the ONE
   *  chat engine — APPEND-only, NO re-answer (the hub already produced and spoke it).
   *  `interrupted` = the turn was cut off by a barge-in (a partial reply is still
   *  recorded, per macOS RealtimeHubController.recordInterruptedTurn). `turnId` is
   *  the per-press idempotency key that dedupes the kernel record. */
  onRecordTurn?: (
    userText: string,
    assistantText: string,
    interrupted: boolean,
    turnId?: string
  ) => void
  /** Execute one voice-requested tool IN-PROCESS via the SAME host executor registry
   *  the typed path uses (PR-C). Production wraps `window.omi.voiceToolExecute` →
   *  main `executeHostTool` (authority host-derived). Never rejects in practice
   *  (main returns `"Error: …"` strings); the driver still guards a rejection so a
   *  transport failure can't wedge the turn. Absent ⇒ no tool loop (today's behavior:
   *  a provider tool call would hang until the reducer's 30 s `pendingTools` deadline). */
  executeTool?: (name: string, argumentsJSON: string) => Promise<string>
  /** Pref-gated system-audio duck at capture start (defaults to the shipped A4 call). */
  muteForCapture?: () => void
  /** Unconditional, idempotent system-audio restore (defaults to shipped). */
  restoreSystemAudio?: () => void
  /** Shared fallback telemetry emitter (defaults to the renderer `trackEvent`). */
  trackEvent?: (event: string, properties: Record<string, unknown>) => void
  /** The live kill-switch pref (defaults to `getPreferences`). */
  prefs?: () => { pttHubEnabled?: boolean }
  /** Schedule the post-release watchdog (defaults to a real `setTimeout` of
   *  `RELEASE_WATCHDOG_MS`); injectable so tests fire it on command. */
  scheduleReleaseWatchdog?: (fire: () => void) => { cancel(): void }
  // --- test seams ---
  scheduler?: VoiceTurnDeadlineScheduling
  mintTurnID?: () => VoiceTurnID
  mintCaptureID?: () => VoiceCaptureID
  output?: VoiceOutputCoordinator
  now?: () => number
}

const isHubRoute = (route: VoiceTurnRoute): boolean =>
  route.kind === 'hub' || route.kind === 'hubWarmWait'

export class VoiceHubTurnDriver {
  private readonly deps: VoiceHubTurnDriverDeps
  private readonly prefs: () => { pttHubEnabled?: boolean }
  private readonly muteForCapture: () => void
  private readonly restoreAudio: () => void
  private readonly scheduleReleaseWatchdog: (fire: () => void) => { cancel(): void }
  private readonly now: () => number
  private readonly mintCaptureID: () => VoiceCaptureID
  private captureSeq = 0

  private readonly hub: HubController
  private readonly output: VoiceOutputCoordinator
  private readonly host: VoiceTurnHost
  private readonly coordinator: VoiceTurnCoordinator

  // Per-turn state ------------------------------------------------------------
  private turnID: VoiceTurnID | null = null
  private captureID: VoiceCaptureID | null = null
  private route: VoiceTurnRoute = { kind: 'undecided' }
  private sessionID: VoiceSessionID | null = null
  private capture: PttCapture | null = null
  private committed = false
  private handedOff = false
  private cascadeBuffer: Int16Array[] = []
  private cascadeBufferBytes = 0
  // Transcript + reply accumulators for chat recording (macOS turnTranscript /
  // assistantText). `turnRecorded` dedups exactly-once across terminal edges (a
  // delegate that fires turn-done twice on reconnect/barge-in). Reset per turn.
  private turnTranscript = ''
  private assistantText = ''
  private turnRecorded = false
  /** Running voiced-audio stats for THIS turn's captured PCM (all routes) — the
   *  hub lane's release gate reads these at end() (the cascade lane gates on its
   *  retained buffer instead). Accumulated per chunk; capture chunks are 4096
   *  samples (256 ms), far above the 320-sample RMS frame, so the per-chunk
   *  trailing-partial loss is negligible. */
  private voiced: AudioStats = ZERO_STATS
  /** Armed at release (end/cancel); force-finalizes a turn the machine failed to
   *  free (see RELEASE_WATCHDOG_MS). Cancelled on terminal reconciliation. */
  private watchdog: { cancel(): void } | null = null

  // Projection state ----------------------------------------------------------
  private lastProjection: VoiceTurnUIProjection = IDLE_PROJECTION
  private orbLevel = 0
  private lastOrbPublishAt = 0

  constructor(deps: VoiceHubTurnDriverDeps) {
    this.deps = deps
    this.prefs = deps.prefs ?? getPreferences
    this.muteForCapture = deps.muteForCapture ?? defaultMuteForCapture
    this.restoreAudio = deps.restoreSystemAudio ?? defaultRestoreSystemAudio
    this.scheduleReleaseWatchdog =
      deps.scheduleReleaseWatchdog ??
      ((fire) => {
        const handle = setTimeout(fire, RELEASE_WATCHDOG_MS)
        return { cancel: () => clearTimeout(handle) }
      })
    this.now = deps.now ?? (() => Date.now())
    // VoiceCaptureID is a branded NUMBER — a per-driver monotonic counter (this id
    // is only a reducer fencing token; it shares no namespace with the capture
    // window's own string captureId).
    this.mintCaptureID =
      deps.mintCaptureID ?? (() => ++this.captureSeq as unknown as VoiceCaptureID)
    this.output = deps.output ?? new VoiceOutputCoordinator()

    // The controller is constructed with the driver's event wiring so provider /
    // session lifecycle events map back into reducer events.
    this.hub = deps.createHub(this.hubEvents())

    const hostDeps: VoiceTurnHostDeps = {
      // The reducer's `stopCapture` effect disposes the driver's capture handle;
      // its own captureID namespace is opaque to us, so we ignore the argument.
      disposeCapture: () => this.disposeCapture(),
      hub: this.hub,
      interruptPlayback: (leaseID) => this.deps.interruptPlayback(leaseID),
      outputCoordinator: this.output,
      applyProjection: (projection) => this.onProjection(projection),
      restoreSystemAudio: deps.restoreSystemAudio ?? defaultRestoreSystemAudio,
      trackEvent: deps.trackEvent ?? defaultTrackEvent
    }
    this.host = new VoiceTurnHost(hostDeps)

    this.coordinator = new VoiceTurnCoordinator({
      scheduler: deps.scheduler,
      mintTurnID: deps.mintTurnID
    })
    this.coordinator.setEffectHandler(this.host.effectHandler)
    this.coordinator.configure(this.host.presenter)
  }

  /** Eagerly open the warm socket (bar summon / hover). Idempotent; a no-op when
   *  the flag is off. Warming is what makes `hub.isAvailable()` true so the next
   *  press routes to the hub instead of falling straight to the cascade. */
  warm(): void {
    if (this.prefs().pttHubEnabled !== true) return
    // Eager warm is best-effort fire-and-forget: swallow the rejection so a failed
    // mint (both providers down) OR a teardown-during-warm abort (HubWarmAbortedError,
    // e.g. sign-out mid-warm) never becomes an unhandled rejection. Matches the A7c
    // reconnect/beginTurn pattern; the next real press re-warms or falls back.
    void this.hub.ensureWarm().catch(() => {})
  }

  /** A7c item E — the machine woke / unlocked. A socket warmed before suspend is
   *  likely a zombie (the OS killed the TCP connection), so the next press would commit
   *  onto a dead session and hang. Proactively refresh the idle warm session. Gated on
   *  the same `pttHubEnabled` opt-out as `warm()` so wake never opens a socket for a
   *  disabled hub; the controller further no-ops when there's no session or a turn is
   *  active (deferring the refresh to that turn's termination). */
  requestSessionRefresh(reason: string): void {
    if (this.prefs().pttHubEnabled !== true) return
    this.hub.requestSessionRefresh(reason)
  }

  /** Drop the warm socket (kill-switch toggled off, or sign-out) without destroying
   *  the driver — a later `warm()` reconnects. Abandons any live turn first so its
   *  reducer state is released. Idempotent. */
  teardown(): void {
    if (this.turnID !== null) this.cancel()
    this.hub.teardownSession()
  }

  /** A bar hold delegated its turn to this driver (flag on). Begins a main-owned
   *  turn: barge-in, route selection, hub begin, and main-owned capture. */
  begin(payload: { backfillMs: number }): void {
    // Barge-in seam (Mac `PushToTalkManager.startListening` → interruptCurrentResponse):
    // a new hold cuts off a still-playing cascade/TTS reply. Safe no-op when idle.
    // Hub playback is instead cancelled by the superseding `beginTurn(interrupting)`.
    this.deps.interruptPlayback(null)

    const superseding = this.turnID !== null

    // Barge-in: record the turn being superseded (its partial user text + partial
    // reply) into chat BEFORE it's torn down and its accumulators are reset — macOS
    // recordInterruptedTurn. Exactly-once via turnRecorded; a no-op only if BOTH
    // sides are still empty (an interrupt before the user's transcript arrived and
    // before any reply). A user-only partial IS preserved, so an early barge-in no
    // longer silently drops the interrupted message.
    if (superseding) this.recordTurnIfUnrecorded(true)

    // `begin` mints the id and sends `start` (which terminates any prior turn as
    // interruptedByBargeIn — the reducer preserves a hub socket for the successor).
    const turnID = this.coordinator.begin('hold')
    this.turnID = turnID
    this.captureID = this.mintCaptureID()
    this.output.beginTurn(turnID)
    this.committed = false
    this.handedOff = false
    this.cascadeBuffer = []
    this.cascadeBufferBytes = 0
    this.sessionID = null
    this.orbLevel = 0
    this.turnTranscript = ''
    this.assistantText = ''
    this.turnRecorded = false
    this.voiced = ZERO_STATS
    // A prior turn's release watchdog must not fire into this fresh turn.
    this.watchdog?.cancel()
    this.watchdog = null

    // The HOST picks the route (the reducer never does): flag-gated kill-switch.
    const route = selectPttRoute(this.hub, this.prefs())
    this.route = route
    this.dispatch({ type: 'selectRoute', turnID, route })

    // A4: duck other apps' audio for this main-owned capture (pref-gated inside).
    this.muteForCapture()

    if (isHubRoute(route)) {
      // Buffered internally while the socket is still warming; a superseding hold
      // drives the provider's in-flight-reply cancel.
      this.hub.beginTurn(turnID, { interrupting: superseding })
    }

    // Capture ownership: issued from THIS (main) renderer, so owned PCM routes here.
    void this.deps
      .startCapture({
        backfillMs: payload.backfillMs,
        onChunk: (pcm) => this.onCaptureChunk(pcm)
      })
      .then((capture) => {
        if (this.turnID !== turnID) {
          // The turn ended/cancelled while the mic span up — drop the orphan.
          capture.dispose()
          return
        }
        this.capture = capture
        this.dispatch({ type: 'captureStarted', turnID, captureID: this.captureID! })
      })
      .catch((err: Error) => {
        if (this.turnID !== turnID) return
        this.dispatch({ type: 'captureFailed', turnID, captureID: null, message: err.message })
      })
  }

  /** The delegated hold was released — finalize + resolve the turn. */
  end(): void {
    const turnID = this.turnID
    if (turnID === null) return
    this.committed = true
    // The user has released: from here the turn MUST reach a terminal in bounded
    // time. Armed before any dispatch so even a wedged finalize chain is covered.
    this.armReleaseWatchdog(turnID)
    // `finalize` stops capture (host disposes the mic) and enters `finalizing`.
    this.dispatch({ type: 'finalize', turnID })

    if (this.handedOff) {
      // The hub lost the 1 s warm race while we were still holding; the turn is
      // already on the cascade. Transcribe what we retained.
      this.runCascadeTranscription(turnID)
      return
    }

    if (isHubRoute(this.route)) {
      // Release gate, hub lane (2026-07-18 short-press wedge): decide from the
      // captured PCM alone — BEFORE committing to the provider — whether this
      // turn is worth a hub response. Mirrors the cascade gate below exactly:
      // a 220–350 ms press (or a release that beat the capture spin-up, i.e.
      // zero samples) must ALWAYS finalize deterministically here, never commit
      // a near-empty turn the provider may silently never answer.
      //   too-short / dead-mic → terminal `tooShort` ("Hold longer to record");
      //   silent (real hold, live room, no speech) → terminal `silentRejected`
      //     (quiet discard — never hand silence to the model).
      // The terminal's `cancelHub` effect abandons the hub turn while KEEPING
      // the warm socket, so the next press is still instant.
      const hubGate = gateDecision(this.voiced)
      if (hubGate === 'too-short' || hubGate === 'dead-mic') {
        this.dispatch({ type: 'finish', turnID, reason: 'tooShort' })
        return
      }
      if (hubGate === 'silent') {
        this.dispatch({ type: 'finish', turnID, reason: 'silentRejected' })
        return
      }
      this.hub.commitTurn(turnID)
      if (this.hub.isWarm() && this.sessionID !== null) {
        // Warm hub: the commit is accepted now — advance to awaitingResponse.
        this.dispatch({
          type: 'hubCommitAccepted',
          turnID,
          sessionID: this.sessionID,
          responseID: null
        })
      } else {
        // Cold warm-wait: defer; `onConnected` (hubReady) + the controller's replay
        // drive acceptance, or the 1 s hubWarm deadline hands off to the cascade.
        this.dispatch({ type: 'hubCommitDeferred', turnID })
      }
      return
    }

    // omniSTT cascade: transcribe the retained buffer; the reply itself is a
    // normal chat turn on the main path (its orb animation comes from chat.status).
    this.runCascadeTranscription(turnID)
  }

  /** The delegated hold was aborted (Esc / focus loss). */
  cancel(): void {
    const turnID = this.turnID
    if (turnID === null) return
    // A cancel is a release too — the turn must terminate in bounded time.
    this.armReleaseWatchdog(turnID)
    this.dispatch({ type: 'cancel', turnID, reason: 'cancelled' })
  }

  // MARK: - Capture

  private onCaptureChunk(pcm: Int16Array): void {
    const turnID = this.turnID
    if (turnID === null) return

    // Orb loudness straight off the PCM peak — self-contained, so it works from the
    // first frame without waiting on the levels event or the capture handle.
    this.orbLevel = pcmPeakLevel(pcm)
    this.emit(false)

    // Accumulate this turn's voiced stats (capture-rate PCM) for the release gates.
    const stats = voicedStats(pcm)
    this.voiced = {
      totalSec: this.voiced.totalSec + stats.totalSec,
      voicedSec: this.voiced.voicedSec + stats.voicedSec,
      peak: Math.max(this.voiced.peak, stats.peak)
    }

    // Retain for the cascade route (and seed the fallback safety net).
    if (!isHubRoute(this.route)) this.retainForCascade(pcm)

    // Feed the hub (buffered internally during warm-wait; inert after handoff).
    if (isHubRoute(this.route) && !this.handedOff) {
      const rate = this.hub.requiredInputSampleRate()
      const frame =
        rate && rate !== CAPTURE_SAMPLE_RATE ? resamplePcm16(pcm, CAPTURE_SAMPLE_RATE, rate) : pcm
      this.hub.appendAudio(turnID, pcm16ToBytes(frame))
    }
  }

  private retainForCascade(pcm: Int16Array): void {
    this.cascadeBuffer.push(pcm)
    this.cascadeBufferBytes += pcm.byteLength
    while (this.cascadeBufferBytes > CASCADE_BUFFER_MAX_BYTES && this.cascadeBuffer.length > 1) {
      this.cascadeBufferBytes -= this.cascadeBuffer.shift()!.byteLength
    }
  }

  private disposeCapture(): void {
    this.capture?.dispose()
    this.capture = null
  }

  // MARK: - Cascade transcription (omniSTT route + hub warm-wait fallback)

  private runCascadeTranscription(turnID: VoiceTurnID): void {
    const buffer = concatInt16(this.cascadeBuffer)
    this.cascadeBuffer = []
    this.cascadeBufferBytes = 0
    // Release gate — macOS PushToTalkManager finalize parity: decide from the
    // captured PCM alone, BEFORE any network work, whether this turn is worth
    // transcribing. The local hook path has always gated here; the cascade lane
    // didn't, so a first-press-after-idle whose mic spin-up outlasted the hold
    // (zero captured samples) POSTed a zero-byte body → backend 400 "No audio
    // data provided", read by the user as "I spoke and nothing happened".
    //   too-short / dead-mic → terminal `tooShort` ("Hold longer to record",
    //     the same hint Mac shows when release beats capture spin-up — never a
    //     silent discard, and never an empty POST);
    //   silent (a real hold, live room, no speech) → terminal `silentRejected`
    //     (quiet reset — Mac discards silence without ceremony; STT models
    //     hallucinate phrases from silence, so it must never be sent).
    const decision = gateDecision(voicedStats(buffer))
    if (decision === 'too-short' || decision === 'dead-mic') {
      this.dispatch({ type: 'finish', turnID, reason: 'tooShort' })
      return
    }
    if (decision === 'silent') {
      this.dispatch({ type: 'finish', turnID, reason: 'silentRejected' })
      return
    }
    this.dispatch({ type: 'transcriptionStarted', turnID })
    void this.deps
      .transcribe(buffer)
      .then((text) => {
        if (this.turnID !== turnID) return
        this.dispatch({ type: 'transcriptionFinal', turnID, text })
        if (text) this.deps.onFinalText(text, turnID as unknown as string)
        // The user's capture+transcribe turn is done; the reply is a separate chat
        // turn on the main path. End the reducer turn (success) so the orb idles.
        this.dispatch({ type: 'providerTurnFinished', turnID, sessionID: null, responseID: null })
      })
      .catch((err: Error) => {
        if (this.turnID !== turnID) return
        this.dispatch({ type: 'transcriptionFailed', turnID, message: err.message })
      })
  }

  // MARK: - Hub session/provider event → reducer event mapping

  private hubEvents(): HubControllerEvents {
    return {
      onConnected: (sessionID) => {
        this.sessionID = sessionID
        const turnID = this.turnID
        if (turnID === null) return
        if (this.route.kind === 'hubWarmWait') {
          this.route = { kind: 'hub', sessionID }
          this.dispatch({ type: 'hubReady', turnID, sessionID })
          // The user released before the socket was ready (deferred commit): the
          // controller replays the commit on connect, so accept it into the reducer.
          if (this.committed) {
            this.dispatch({ type: 'hubCommitAccepted', turnID, sessionID, responseID: null })
          }
        }
      },
      onError: () => {
        const turnID = this.turnID
        if (turnID !== null) this.dispatch({ type: 'cancel', turnID, reason: 'providerFailed' })
      },
      onSpeakingStart: () => {
        const turnID = this.turnID
        if (turnID === null) return
        this.dispatch({
          type: 'providerResponseStarted',
          turnID,
          sessionID: this.sessionID,
          responseID: null
        })
        const decision = this.output.acquire('nativeRealtime', turnID)
        if (decision.kind === 'acquired') {
          this.dispatch({ type: 'playbackStarted', turnID, lease: decision.lease })
        }
      },
      onSpeakingEnd: () => {
        const turnID = this.turnID
        if (turnID === null) return
        const lease = this.output.snapshot().activeLease
        if (lease !== null) {
          this.dispatch({ type: 'playbackDrained', turnID, leaseID: lease.id })
        }
      },
      onTurnDone: () => {
        const turnID = this.turnID
        if (turnID !== null) {
          this.dispatch({
            type: 'providerTurnFinished',
            turnID,
            sessionID: this.sessionID,
            responseID: null
          })
          // Mac parity (RealtimeHubController.hubDidFinishTurn): record the completed
          // turn into the ONE chat engine the moment the provider finishes GENERATING,
          // NOT after the spoken reply finishes PLAYING. Windows had recorded only on
          // the terminal `success` edge, which waits for `playbackDrained` — so on a
          // long reply the user's own message surfaced 5–30s late. The dispatch above
          // may itself already have reached terminal success (playback drained before
          // turn-done) and recorded via dispatch()'s terminal path; because
          // recordTurnIfUnrecorded is idempotent (`turnRecorded`), this call is then a
          // no-op — preserving INV-CHAT-1 exactly-once. In the common still-playing
          // case this is the early record. Assistant text is fully accumulated by now:
          // both providers emit their final assistant marker immediately BEFORE
          // turn-done (geminiHubSession turnComplete / openaiHubSession response.done).
          this.recordTurnIfUnrecorded(false)
        }
      },
      onInputTranscript: (text, isFinal) => {
        const turnID = this.turnID
        if (turnID === null || !text) return
        // Accumulate the user transcript for chat recording (deltas add; a non-empty
        // final replaces with the full string). Kept separate from the reducer
        // dispatch below so the orb projection is unchanged.
        this.turnTranscript = isFinal ? text : this.turnTranscript + text
        this.dispatch({ type: 'transcriptChanged', turnID, text })
      },
      onAssistantText: (text, isFinal) => {
        if (this.turnID === null) return
        // Accumulate the reply text for chat recording. Empty-final guard: OpenAI GA
        // emits an EMPTY final transcript marker after the deltas — it must NOT wipe
        // what we accumulated, or the turn records with no assistant text.
        if (text) this.assistantText = isFinal ? text : this.assistantText + text
      },
      // The model requested a tool (PR-C). Dispatch it IN-PROCESS via the shared host
      // executor registry (control tools + serviceable product tools + spawn_agent),
      // then relay the result back to the provider so it can finish speaking. Parallel
      // calls each register in the reducer's pending set; the turn completes only once
      // every pending call resolves (or the 30 s pendingTools deadline fires).
      onToolRequest: (call) => {
        const turnID = this.turnID
        if (turnID === null) return
        if (!this.deps.executeTool) {
          // No executor wired (older host): satisfy the provider so its turn doesn't
          // hang, without entering awaitingTools (there is nothing to await).
          this.hub.sendToolResult(call.callId, call.name, 'Error: tools are not available')
          return
        }
        this.dispatch({
          type: 'toolStarted',
          turnID,
          callID: call.callId as unknown as VoiceToolCallID
        })
        this.executeVoiceTool(turnID, call)
      },
      // The warm-wait buffer lost the 1 s race — the reducer already moved the
      // route to deepgramBatch and kept the turn alive. Transcribe on the cascade.
      onCascadeHandoff: ({ frames, committed }) => {
        const turnID = this.turnID
        if (turnID === null) return
        this.handedOff = true
        this.route = { kind: 'deepgramBatch' }
        // Seed the cascade with what the hub buffered so no opening words are lost.
        this.seedCascadeFromFrames(frames)
        // Only transcribe now if the user already released; otherwise keep
        // capturing and `end()` will transcribe the full utterance.
        if (committed) this.runCascadeTranscription(turnID)
      }
    }
  }

  /** Run one voice tool call and relay its result to the provider (PR-C). The
   *  execution authority is entirely HOST-side (`executeHostTool` derives role/owner
   *  from the surface session); this driver only shuttles the request and the result.
   *  Never rejects the turn: a transport failure resolves the pending call with an
   *  `"Error: …"` string the model can recover from. */
  private executeVoiceTool(
    turnID: VoiceTurnID,
    call: { name: string; callId: string; argumentsJSON: string }
  ): void {
    const execute = this.deps.executeTool
    if (!execute) return
    const callID = call.callId as unknown as VoiceToolCallID
    const settle = (output: string): void => {
      // Turn-epoch gate: a barge-in / cancel superseded this turn while the tool ran.
      // Drop the stale result — never feed it to the now-different provider turn, and
      // don't dispatch toolFinished (the reducer already tore the old turn down; a
      // toolFinished for its callID would be a no-op `stale` anyway).
      if (this.turnID !== turnID) return
      this.hub.sendToolResult(call.callId, call.name, output)
      this.dispatch({ type: 'toolFinished', turnID, callID })
    }
    void execute(call.name, call.argumentsJSON).then(settle, (err: unknown) =>
      settle(`Error: ${err instanceof Error ? err.message : String(err)}`)
    )
  }

  private seedCascadeFromFrames(frames: readonly Uint8Array[]): void {
    // The hub buffers PCM at its required input rate; the cascade transcribes at
    // the capture rate. Convert each frame back to Int16 samples for the batch.
    for (const frame of frames) this.retainForCascade(bytesToPcm16(frame))
  }

  // MARK: - Dispatch + projection

  /** Every reducer event goes through here so terminal reconciliation (clearing
   *  the driver's per-turn state) happens exactly once, right after the send. */
  private dispatch(event: VoiceTurnEvent): void {
    this.coordinator.send(event)
    if (this.turnID !== null && this.coordinator.activeTurnID === null) {
      // Terminal reached: the host already ran stopCapture / cancelHub /
      // restoreSystemAudio via effects. A clean-success hub turn records its text
      // into the ONE chat engine here (INV-CHAT-1) — append-only, exactly-once.
      // (Cascade turns record via onFinalText → chat.send instead, and have no
      // accumulated assistantText, so recordTurnIfUnrecorded is a no-op for them.
      // A barge-in interrupted turn was already recorded in begin(). Non-success
      // terminals — cancel / providerFailed — are not recorded.)
      if (this.coordinator.model.lastTerminal?.reason === 'success') {
        this.recordTurnIfUnrecorded(false)
      }
      // Clear the driver's per-turn state and tell the bar to drop back to its
      // local orb (`active:false`).
      this.watchdog?.cancel()
      this.watchdog = null
      this.turnID = null
      this.captureID = null
      this.route = { kind: 'undecided' }
      this.sessionID = null
      this.cascadeBuffer = []
      this.cascadeBufferBytes = 0
      this.orbLevel = 0
      this.emit(true)
    }
  }

  // MARK: - Release watchdog (no turn may hold ownership forever)

  private armReleaseWatchdog(turnID: VoiceTurnID): void {
    this.watchdog?.cancel()
    this.watchdog = this.scheduleReleaseWatchdog(() => {
      this.watchdog = null
      this.fireReleaseWatchdog(turnID)
    })
  }

  /** RELEASE_WATCHDOG_MS after release the turn is still ours: decide whether the
   *  machine is wedged and, if so, force-finalize. Fires ONLY for a turn stuck in
   *  a pre-response phase (capture/finalizing — the phases the 2026-07-18 wedge
   *  froze in) or a driver↔coordinator desync; a turn that advanced to
   *  awaitingResponse/tools/playing is governed by the reducer's own deadlines
   *  and is deliberately left alone (a long spoken reply must never be cut). */
  private fireReleaseWatchdog(armedTurnID: VoiceTurnID): void {
    if (this.turnID !== armedTurnID) return
    const turn = this.coordinator.model.turn
    const phase = turn?.phase.kind
    const desynced = turn === null || turn.id !== armedTurnID
    const stuckPreResponse =
      phase === 'recording' ||
      phase === 'lockedRecording' ||
      phase === 'pendingLockDecision' ||
      phase === 'finalizing'
    if (!desynced && !stuckPreResponse) return

    console.error(
      `[hub-diag] release watchdog fired: turn stuck ${desynced ? 'desynced' : `in ${phase}`} ` +
        `${RELEASE_WATCHDOG_MS}ms after release — force-finalizing`
    )
    // Normal path first: a cleanup terminal runs the full host teardown (capture,
    // hub cancel, output lease, system-audio restore) and the reconciliation above
    // clears the driver's per-turn state.
    try {
      this.dispatch({ type: 'cleanup' })
    } catch {
      // The machinery is the thing that's broken — fall through to manual cleanup.
    }
    // Belt-and-braces: in the desync/wedge class the host teardown may have run
    // against the WRONG turn id (or not at all). Every call is idempotent.
    try {
      this.disposeCapture()
    } catch {
      /* keep going — release everything we can */
    }
    try {
      this.output.endTurn(armedTurnID)
    } catch {
      /* keep going */
    }
    try {
      this.hub.voiceTurnDidTerminate(armedTurnID)
    } catch {
      /* keep going */
    }
    try {
      this.restoreAudio()
    } catch {
      /* keep going */
    }
    if (this.turnID === armedTurnID) {
      // The dispatch above could not reconcile — force the driver idle by hand.
      this.turnID = null
      this.captureID = null
      this.route = { kind: 'undecided' }
      this.sessionID = null
      this.cascadeBuffer = []
      this.cascadeBufferBytes = 0
      this.orbLevel = 0
    }
    // Surface what happened instead of a silent idle, then auto-clear the hint.
    this.lastProjection = { ...IDLE_PROJECTION, hint: RELEASE_WATCHDOG_HINT }
    this.emit(true)
    setTimeout(() => {
      if (this.turnID === null && this.lastProjection.hint === RELEASE_WATCHDOG_HINT) {
        this.lastProjection = IDLE_PROJECTION
        this.emit(true)
      }
    }, HINT_MS)
  }

  /** Append this turn's user transcript + assistant reply to the ONE chat engine,
   *  exactly once (macOS turnRecorded). No-op if already recorded or if BOTH texts
   *  are empty (e.g. a cascade turn, or a barge-in before either side produced text). */
  private recordTurnIfUnrecorded(interrupted: boolean): void {
    if (this.turnRecorded) return
    const user = this.turnTranscript.trim()
    const assistant = this.assistantText.trim()
    // Record whenever AT LEAST one side has text (macOS records unconditionally at
    // hubDidFinishTurn). A one-sided turn is real: a near-silent/short hold the
    // provider returned no input transcription for, or a spoken reply with no text —
    // dropping it read to users as "my message never sent." Only a BOTH-empty turn is
    // skipped (matches the kernel handler's own guard in main/ipc/voiceHub.ts).
    if (!user && !assistant) return
    this.turnRecorded = true
    const turnId = this.turnID as unknown as string | null
    // The warm hub SAW this turn live — mark its id so the continuity seed refresh
    // doesn't treat it as an unseen turn and needlessly reconnect (thrash guard).
    if (turnId) this.hub.markSeedKeyProduced(turnId)
    this.deps.onRecordTurn?.(user, assistant, interrupted, turnId ?? undefined)
  }

  /** Refresh the hub's continuity seed (idle-only reconnect when it carries turns the
   *  warm session hasn't seen). Called by the host when the shared thread changes so
   *  the NEXT voice turn's realtime session is seeded with the latest typed/voice
   *  turns (macOS refreshes the seed via a full reconnect when stale). */
  refreshSeedContext(): void {
    this.hub.refreshSeedContext()
  }

  private onProjection(projection: VoiceTurnUIProjection): void {
    this.lastProjection = projection
    this.emit(true)
  }

  /** Publish the orb state to the bar. `force` (a reducer transition) always emits;
   *  the continuous loudness is throttled to `ORB_PUBLISH_INTERVAL_MS`. */
  private emit(force: boolean): void {
    const now = this.now()
    if (!force && now - this.lastOrbPublishAt < ORB_PUBLISH_INTERVAL_MS) return
    this.lastOrbPublishAt = now
    const p = this.lastProjection
    this.deps.publishState({
      active: this.turnID !== null,
      isListening: p.isListening,
      isThinking: p.isThinking,
      isResponseActive: p.isResponseActive,
      orbLevel: this.turnID !== null ? this.orbLevel : 0,
      // Forwarded UNCONDITIONALLY (not gated on an active turn): a terminal hint (e.g.
      // a post-commit provider death) is emitted on the same terminal transition that
      // drops `turnID` to null, so gating it on `active` would swallow it. Non-terminal
      // projections carry an empty hint, so this is inert during a normal turn. The
      // reducer's `hintVisibility` deadline later re-projects an empty hint to clear it.
      hint: p.hint
    })
  }
}

// MARK: - PCM helpers (pure, module-local)

/** Peak amplitude of a PCM16 frame, normalized to [0,1]. */
export function pcmPeakLevel(pcm: Int16Array): number {
  let peak = 0
  for (let i = 0; i < pcm.length; i++) {
    const v = pcm[i] < 0 ? -pcm[i] : pcm[i]
    if (v > peak) peak = v
  }
  return peak / 32768
}

/** Concatenate PCM16 frames into one contiguous buffer. */
export function concatInt16(frames: readonly Int16Array[]): Int16Array {
  let total = 0
  for (const f of frames) total += f.length
  const out = new Int16Array(total)
  let offset = 0
  for (const f of frames) {
    out.set(f, offset)
    offset += f.length
  }
  return out
}

/** View a PCM16 frame as raw little-endian bytes (exact window — a subarray view
 *  is sliced so it never carries the surrounding buffer). */
export function pcm16ToBytes(pcm: Int16Array): Uint8Array {
  return new Uint8Array(pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength))
}

/** Reinterpret raw little-endian PCM16 bytes as samples. Copies to guarantee
 *  2-byte alignment (a byte offset from a slice may not be Int16-aligned). */
export function bytesToPcm16(bytes: Uint8Array): Int16Array {
  const aligned = new Uint8Array(bytes.byteLength - (bytes.byteLength % 2))
  aligned.set(bytes.subarray(0, aligned.byteLength))
  return new Int16Array(aligned.buffer)
}

/** Linear-interpolation PCM16 resample (mono). Adequate for mic → provider input;
 *  the providers run their own front-end resampling too. */
export function resamplePcm16(pcm: Int16Array, srcRate: number, dstRate: number): Int16Array {
  if (srcRate === dstRate || pcm.length === 0) return pcm
  const ratio = dstRate / srcRate
  const outLen = Math.max(1, Math.round(pcm.length * ratio))
  const out = new Int16Array(outLen)
  for (let i = 0; i < outLen; i++) {
    const srcPos = i / ratio
    const i0 = Math.floor(srcPos)
    const i1 = Math.min(i0 + 1, pcm.length - 1)
    const frac = srcPos - i0
    out[i] = Math.round(pcm[i0] * (1 - frac) + pcm[i1] * frac)
  }
  return out
}
