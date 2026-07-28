// The VoiceTurn HOST — the coordinator's `effectHandler` (Track 2 / A5 PR-6).
//
// The reducer (`voiceTurnMachine.ts`) decides WHAT happens; the coordinator
// (`voiceTurnCoordinator.ts`) owns timers, the timeline, and effect delivery; the
// host is where each reducer effect finally becomes a real subsystem call. It is
// the ONLY new module that reaches shipped runtime (capture dispose, hub cancel,
// playback interrupt, output-lease end, system-audio restore) — so every
// collaborator is an INJECTED seam. That makes the whole host exercisable against
// fakes, and makes the kill-switch structural: when `pttHubEnabled` is off the
// route is `omniSTT`, the host is never asked to cancel a hub or hand off a warm
// buffer, and none of its hub-facing calls fire (see `selectPttRoute`).
//
// Effect → action (ported EXACTLY from the port plan §C/§D "PR 6" table):
//   stopCapture             → dispose the capture-window mic capture
//   cancelHub               → hubController.cancelTurn(turnID)     [route dropped, see below]
//   fallbackToTranscription → hubController.handoffWarmWaitToCascade(turnID) — the turn
//                             CONTINUES on the cascade; nothing here terminates it. The
//                             controller already emits the `degraded` fallback telemetry,
//                             so the host does NOT re-emit it (no double count).
//   stopPlayback            → interruptCurrentResponse(leaseID) (voiceController)
//   terminal                → outputCoordinator.endTurn + hubController.voiceTurnDidTerminate
//                             + A4 system-audio restore (exactly once — one terminal per turn)
//                             + host per-turn cleanup; plus an `exhausted` fallback event when
//                             the terminal reason is a no-path-left provider/warm failure.
//   scheduleDeadline / cancelDeadline / cancelAllDeadlines / staleEventDropped /
//   invalidTransition       → IGNORED. The coordinator already armed/cancelled the timer
//                             and recorded the anomaly; the host must not re-handle them
//                             (and must never `assertNever`, or a timer effect throws out
//                             of the coordinator's drain).
//
// Windows deviation: the `cancelHub` effect carries the PRE-terminal route so a
// host COULD pick a transport to tear down, but the Windows `HubController` owns
// exactly one warm session at a time and its `cancelTurn(turnID)` needs no route —
// so the host drops the route argument. (macOS's facade multiplexed transports;
// ours does not.)

import type { HubControllerError } from '../hub/hubController'
import { trackEvent as defaultTrackEvent } from '../../analytics'
import { restoreSystemAudio as defaultRestoreSystemAudio } from '../../ptt/systemAudioMute'
import { getPreferences } from '../../preferences'
import {
  projectionOf,
  VOICE_TURN_TERMINAL_REASON_RAW,
  type VoiceCaptureID,
  type VoiceLeaseID,
  type VoiceTurnEffect,
  type VoiceTurnID,
  type VoiceTurnModel,
  type VoiceTurnRoute,
  type VoiceTurnTerminalReason,
  type VoiceTurnUIProjection
} from './voiceTurnMachine'
import type { VoiceTurnPresenter } from './voiceTurnCoordinator'

// MARK: - Route selection (the kill-switch seam)

/** What the host needs to know about the warm hub to pick a route. `HubController`
 *  satisfies this structurally. */
export type PttHubAvailability = {
  isAvailable(): boolean
  isWarm(): boolean
}

/** The single choke point of the `pttHubEnabled` kill-switch. When the pref is off
 *  (the default), this ALWAYS returns `omniSTT` — the shipped cascade route — no
 *  matter the hub's state, so the reducer drives today's byte-for-byte path and the
 *  host's hub-facing effects never fire. Only when the pref is on AND the hub is
 *  available does a PTT press take the warm lane (`hub` when already warm, else
 *  `hubWarmWait`, which the reducer's 1 s `hubWarm` deadline degrades back to the
 *  cascade — never worse than today). The HOST picks the route; the reducer never
 *  does (port plan §C.6). */
export function selectPttRoute(
  hub: PttHubAvailability,
  prefs: { pttHubEnabled?: boolean } = getPreferences()
): VoiceTurnRoute {
  if (prefs.pttHubEnabled !== true || !hub.isAvailable()) {
    return { kind: 'omniSTT' }
  }
  return hub.isWarm() ? { kind: 'hub', sessionID: null } : { kind: 'hubWarmWait' }
}

// MARK: - Injected collaborators

/** The subset of `HubController` the host drives from reducer effects. The real
 *  controller satisfies it structurally; tests pass a spy. */
export type VoiceTurnHubPort = {
  cancelTurn(turnID: VoiceTurnID): void
  handoffWarmWaitToCascade(turnID: VoiceTurnID): void
  voiceTurnDidTerminate(turnID: VoiceTurnID): void
}

/** The subset of `VoiceOutputCoordinator` the host ends on terminal. */
export type VoiceTurnOutputPort = {
  endTurn(turnID: VoiceTurnID): boolean
}

export type VoiceTurnHostDeps = {
  /** Dispose the capture window's mic capture for a turn (`stopCapture` effect). */
  disposeCapture: (turnID: VoiceTurnID, captureID: VoiceCaptureID | null) => void
  /** The warm-hub controller (may be a thin IPC proxy in the bar; the controller
   *  itself lives in the MAIN window per decision D1). */
  hub: VoiceTurnHubPort
  /** Stop the current spoken reply for a lease (`stopPlayback` effect). In the bar
   *  this hops to the MAIN window's `voiceController.interruptCurrentResponse`. */
  interruptPlayback: (leaseID: VoiceLeaseID | null) => void
  /** The turn-scoped audible-output lease owner (`terminal` → `endTurn`). */
  outputCoordinator: VoiceTurnOutputPort
  /** Broadcast the reducer projection to the bar orb/hint. */
  applyProjection: (projection: VoiceTurnUIProjection) => void
  /** Unconditional, idempotent system-audio restore (A4). Defaults to the shipped
   *  `restoreSystemAudio`; injectable so the "exactly one restore" test can spy. */
  restoreSystemAudio?: () => void
  /** Shared fallback telemetry emitter (defaults to the renderer `trackEvent`). */
  trackEvent?: (event: string, properties: Record<string, unknown>) => void
  /** The A7c connect/error surface, forwarded straight through. A5 wires it to a
   *  no-op host handler so A7c (reconnect/failover/wake) is a body change later. */
  onHubConnected?: (sessionID: unknown) => void
  onHubError?: (error: HubControllerError) => void
}

/** Terminal reasons that represent a fully-exhausted warm-hub path (no fallback
 *  left) — the ONLY terminals the host reports to the shared fallback helper, as
 *  `outcome:'exhausted'`. Every other terminal is either a clean success or a hard
 *  failure the reducer's hint already covers (a hard failure is NOT a fallback —
 *  see the AGENTS.md decision table). `hub_warm_timeout` as a *terminal* is
 *  defensive: the reducer's 1 s `hubWarm` deadline is non-terminal (it degrades),
 *  so this reason terminates in practice only if a future path chooses it. */
const EXHAUSTED_TERMINAL_REASONS: ReadonlySet<VoiceTurnTerminalReason> = new Set([
  'providerFailed',
  'providerNoResponse',
  'hubWarmTimeout'
])

// MARK: - Host

export class VoiceTurnHost {
  private readonly deps: VoiceTurnHostDeps
  private readonly restore: () => void
  private readonly track: (event: string, properties: Record<string, unknown>) => void
  /** The turn whose one A4 restore has already fired — so a terminal (or a later
   *  effect) can never restore twice for the same turn. */
  private restoredTurnID: VoiceTurnID | null = null

  constructor(deps: VoiceTurnHostDeps) {
    this.deps = deps
    this.restore = deps.restoreSystemAudio ?? defaultRestoreSystemAudio
    this.track = deps.trackEvent ?? defaultTrackEvent
  }

  /** Wire as `coordinator.setEffectHandler(host.effectHandler)`. Bound so the
   *  coordinator can hold it directly. */
  readonly effectHandler = (effect: VoiceTurnEffect): void => {
    switch (effect.kind) {
      case 'stopCapture':
        this.deps.disposeCapture(effect.turnID, effect.captureID)
        // A4 restore belongs to CAPTURE END, not turn end (2026-07-18 muted-reply
        // fix). The helper mutes the DEFAULT OUTPUT ENDPOINT — the same device the
        // hub reply plays through — and the mute exists only to keep other apps'
        // audio out of the mic while it is open. Restoring here (release/cancel/
        // teardown all emit stopCapture) re-opens the speakers BEFORE the provider
        // reply starts; restoring only on `terminal` left the endpoint muted for
        // the entire hub-route reply, so every reply played into a muted device
        // and users heard nothing while every internal signal read healthy.
        this.restoreSystemAudioOnce(effect.turnID)
        return
      case 'cancelHub':
        // The route is informational on Windows (single warm session) — dropped.
        this.deps.hub.cancelTurn(effect.turnID)
        return
      case 'fallbackToTranscription':
        // Hand the warm-wait buffer to the cascade and KEEP THE TURN ALIVE. The
        // controller emits the `degraded` fallback telemetry on this call, so the
        // host stays silent here (no double emit).
        this.deps.hub.handoffWarmWaitToCascade(effect.turnID)
        return
      case 'stopPlayback':
        this.deps.interruptPlayback(effect.leaseID)
        return
      case 'terminal':
        this.handleTerminal(effect.record.turnID, effect.record.reason)
        return
      // The coordinator already armed/cancelled these timers and recorded the
      // anomalies — the host deliberately ignores them. Never `assertNever`.
      case 'scheduleDeadline':
      case 'cancelDeadline':
      case 'cancelAllDeadlines':
      case 'staleEventDropped':
      case 'invalidTransition':
        return
    }
  }

  /** Wire as `coordinator.configure(host.presenter)` — the reducer projection is
   *  broadcast to the bar orb/hint on every published transition. */
  readonly presenter: VoiceTurnPresenter = {
    apply: (projection) => this.deps.applyProjection(projection)
  }

  /** Optional `coordinator.setSnapshotHandler` seam — projects the authoritative
   *  model to the bar. Redundant with `presenter` (both derive the same projection);
   *  provided for hosts that prefer the snapshot seam. */
  readonly snapshotHandler = (model: VoiceTurnModel): void => {
    this.deps.applyProjection(projectionOf(model))
  }

  /** A7c seam pass-through (unused in A5 — a no-op host handler keeps the wiring in
   *  place so reconnect/failover/wake is a later body change, not new IPC). */
  readonly hubEvents = {
    onConnected: (sessionID: unknown): void => this.deps.onHubConnected?.(sessionID),
    onError: (error: HubControllerError): void => this.deps.onHubError?.(error)
  }

  private handleTerminal(turnID: VoiceTurnID, reason: VoiceTurnTerminalReason): void {
    // Order matches the port plan: release the output lease, release the hub's
    // per-turn state (KEEPING the warm socket), restore system audio, clean up.
    // The restore here is the idempotent BACKSTOP — the primary restore fires at
    // `stopCapture` (capture end), so a turn that never opened a capture (or a
    // teardown path that skipped stopCapture) is still never left muted.
    this.deps.outputCoordinator.endTurn(turnID)
    this.deps.hub.voiceTurnDidTerminate(turnID)
    this.restoreSystemAudioOnce(turnID)

    if (EXHAUSTED_TERMINAL_REASONS.has(reason)) {
      // Fully-exhausted warm-hub path (no fallback left). Shared telemetry
      // contract (AGENTS.md): closed enums, no new counter, do not duplicate the
      // controller's `degraded` handoff event (a different moment on a different
      // outcome).
      this.track('fallback_triggered', {
        component: 'ptt_cascade',
        from: 'hub',
        to: 'none',
        reason: VOICE_TURN_TERMINAL_REASON_RAW[reason],
        outcome: 'exhausted'
      })
    }
  }

  /** A4: exactly ONE restore per turn, fired at the FIRST capture-end signal.
   *  `stopCapture` (release / cancel / teardown / orphan kill) is the primary
   *  site; `terminal` is the backstop for turns that never opened a capture.
   *  `terminate()` emits `stopCapture` then `terminal` back-to-back, so the
   *  turn-ID guard is what keeps that pair a single restore. */
  private restoreSystemAudioOnce(turnID: VoiceTurnID): void {
    if (this.restoredTurnID === turnID) return
    this.restoredTurnID = turnID
    this.restore()
  }
}
