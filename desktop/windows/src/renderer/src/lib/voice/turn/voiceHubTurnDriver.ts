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
import type { PttCapture, PttCaptureOptions } from '../../ptt/capture'
import {
  muteSystemAudioForHubCapture as defaultMuteForCapture,
  restoreSystemAudio as defaultRestoreSystemAudio
} from '../../ptt/systemAudioMute'
import type { VoiceHubBarState } from '../../../../../shared/types'
import type { HubController, HubControllerEvents } from '../hub/hubController'
import { VoiceOutputCoordinator } from './voiceOutputCoordinator'
import { selectPttRoute, VoiceTurnHost, type VoiceTurnHostDeps } from './voiceTurnHost'
import {
  VoiceTurnCoordinator,
  type VoiceTurnDeadlineScheduling
} from './voiceTurnCoordinator'
import {
  IDLE_PROJECTION,
  type VoiceCaptureID,
  type VoiceLeaseID,
  type VoiceSessionID,
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
  /** Commit the final user transcript to the chat engine (the main window's send). */
  onFinalText: (text: string) => void
  /** Pref-gated system-audio duck at capture start (defaults to the shipped A4 call). */
  muteForCapture?: () => void
  /** Unconditional, idempotent system-audio restore (defaults to shipped). */
  restoreSystemAudio?: () => void
  /** Shared fallback telemetry emitter (defaults to the renderer `trackEvent`). */
  trackEvent?: (event: string, properties: Record<string, unknown>) => void
  /** The live kill-switch pref (defaults to `getPreferences`). */
  prefs?: () => { pttHubEnabled?: boolean }
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

  // Projection state ----------------------------------------------------------
  private lastProjection: VoiceTurnUIProjection = IDLE_PROJECTION
  private orbLevel = 0
  private lastOrbPublishAt = 0

  constructor(deps: VoiceHubTurnDriverDeps) {
    this.deps = deps
    this.prefs = deps.prefs ?? getPreferences
    this.muteForCapture = deps.muteForCapture ?? defaultMuteForCapture
    this.now = deps.now ?? (() => Date.now())
    // VoiceCaptureID is a branded NUMBER — a per-driver monotonic counter (this id
    // is only a reducer fencing token; it shares no namespace with the capture
    // window's own string captureId).
    this.mintCaptureID = deps.mintCaptureID ?? (() => ++this.captureSeq as unknown as VoiceCaptureID)
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
   *  the flag is off. */
  warm(): void {
    if (this.prefs().pttHubEnabled !== true) return
    void this.hub.ensureWarm()
  }

  /** A bar hold delegated its turn to this driver (flag on). Begins a main-owned
   *  turn: barge-in, route selection, hub begin, and main-owned capture. */
  begin(payload: { backfillMs: number }): void {
    // Barge-in seam (Mac `PushToTalkManager.startListening` → interruptCurrentResponse):
    // a new hold cuts off a still-playing cascade/TTS reply. Safe no-op when idle.
    // Hub playback is instead cancelled by the superseding `beginTurn(interrupting)`.
    this.deps.interruptPlayback(null)

    const superseding = this.turnID !== null

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
    // `finalize` stops capture (host disposes the mic) and enters `finalizing`.
    this.dispatch({ type: 'finalize', turnID })

    if (this.handedOff) {
      // The hub lost the 1 s warm race while we were still holding; the turn is
      // already on the cascade. Transcribe what we retained.
      this.runCascadeTranscription(turnID)
      return
    }

    if (isHubRoute(this.route)) {
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

    // Retain for the cascade route (and seed the fallback safety net).
    if (!isHubRoute(this.route)) this.retainForCascade(pcm)

    // Feed the hub (buffered internally during warm-wait; inert after handoff).
    if (isHubRoute(this.route) && !this.handedOff) {
      const rate = this.hub.requiredInputSampleRate()
      const frame = rate && rate !== CAPTURE_SAMPLE_RATE ? resamplePcm16(pcm, CAPTURE_SAMPLE_RATE, rate) : pcm
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
    this.dispatch({ type: 'transcriptionStarted', turnID })
    const buffer = concatInt16(this.cascadeBuffer)
    this.cascadeBuffer = []
    this.cascadeBufferBytes = 0
    void this.deps
      .transcribe(buffer)
      .then((text) => {
        if (this.turnID !== turnID) return
        this.dispatch({ type: 'transcriptionFinal', turnID, text })
        if (text) this.deps.onFinalText(text)
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
        }
      },
      onInputTranscript: (text) => {
        const turnID = this.turnID
        if (turnID !== null && text) this.dispatch({ type: 'transcriptChanged', turnID, text })
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
      // restoreSystemAudio via effects. Clear the driver's per-turn state and tell
      // the bar to drop back to its local orb (`active:false`).
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
      orbLevel: this.turnID !== null ? this.orbLevel : 0
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
