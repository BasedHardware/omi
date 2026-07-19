// The VoiceTurn coordinator — a 1:1 port of macOS `VoiceTurnCoordinator.swift`.
//
// It owns everything the reducer deliberately does not: ID minting, the clock,
// deadline timers, the diagnostics timeline, and effect delivery. It performs no
// I/O of its own beyond timers — the real capture / hub / playback transports are
// driven by the injected `effectHandler`, which PR-5/PR-6 supply.
//
// Effect-forwarding deviation (port plan §B.3): macOS CONSUMES the three timer
// effects — `VoiceTurnCoordinator.swift:222-227` arms/cancels the timer and does
// not call `effectHandler` for them; only the remaining effects reach the host.
// Here EVERY effect is forwarded, timer effects included. That is a superset, so
// a host must tolerate `scheduleDeadline` / `cancelDeadline` / `cancelAllDeadlines`
// arriving — never `assertNever` on the effect kind, or a timer will throw out of
// `send()`.
//
// Port notes (the traps a "natural" TS translation gets wrong):
//   * `send()` is FIFO and NON-REENTRANT. An event dispatched from inside an
//     effect or snapshot handler is APPENDED to the pending queue and drained
//     after the in-flight event has fully published — the call stack never
//     recurses. The index-based loop over a growing array IS the mechanism; a
//     `shift()`-based queue or a recursive call breaks it.
//   * Collaborator callbacks are CONTAINED (2026-07-18 wedge fix): a throwing
//     `effectHandler` / presenter / snapshot handler is caught per-call and the
//     drain continues. Before this, one synchronous throw mid-drain skipped the
//     remaining effects — INCLUDING deadline scheduling — and dropped every
//     queued event (`finally` clears the queue), leaving a turn stranded in a
//     capture phase with no timer to ever free it (the "stuck on Listening"
//     PTT wedge). State transitions and timers are the coordinator's own and
//     must never be hostage to a collaborator's exception.
//   * `apply()` publishes one event atomically: reduce → assign model → timeline
//     → effects (in emission order) → presenter → snapshot. No event is ever
//     reduced against a half-applied model.
//   * Deadline handles are keyed by {turnID, deadline}, so a cancelled handle can
//     never fire into a later turn — and a rogue timer that does fire is rejected
//     by the reducer's turn guard anyway.
//
// Windows deviation (macOS has one global `Deadlines` config): deadlines are
// ROUTE-AWARE — see `deadlinesForVoiceTurnRoute`.

import { BATCH_TIMEOUT_MS } from '../../ptt/constants'
import {
  DEFAULT_VOICE_TURN_DEADLINES,
  IDLE_PROJECTION,
  IDLE_VOICE_TURN_MODEL,
  diagnosticLabel,
  isTerminal,
  projectionOf,
  reduceVoiceTurn,
  turnIDOf,
  VOICE_OUTPUT_LANE_RAW,
  VOICE_TURN_TERMINAL_REASON_RAW,
  type VoiceTurnDeadline,
  type VoiceTurnDeadlines,
  type VoiceTurnEffect,
  type VoiceTurnEvent,
  type VoiceTurnID,
  type VoiceTurnIntent,
  type VoiceTurnModel,
  type VoiceTurnPhase,
  type VoiceTurnRoute,
  type VoiceTurnTerminalReason,
  type VoiceTurnUIProjection
} from './voiceTurnMachine'

// MARK: - Route-aware deadlines (decision D2)

/** The shipped cascade's transcription budget. macOS uses 12 s for every route;
 *  the Windows `omniSTT` cascade already ships a 20 s batch timeout, and porting
 *  12 s blindly would kill slow batch transcriptions that succeed today. */
export const CASCADE_VOICE_TURN_DEADLINES: VoiceTurnDeadlines = {
  ...DEFAULT_VOICE_TURN_DEADLINES,
  transcription: BATCH_TIMEOUT_MS / 1000
}

/** Cascade transports (all of them go through the batch/stream STT path on
 *  Windows) get the cascade budget; the hub route gets macOS's. */
export function deadlinesForVoiceTurnRoute(route: VoiceTurnRoute): VoiceTurnDeadlines {
  switch (route.kind) {
    case 'omniSTT':
    case 'deepgramBatch':
    case 'deepgramLive':
      return CASCADE_VOICE_TURN_DEADLINES
    default:
      return DEFAULT_VOICE_TURN_DEADLINES
  }
}

// MARK: - Injected ports

export type VoiceTurnDeadlineCancellation = { cancel(): void }

/** Tests inject a manual clock; production wraps `setTimeout`. */
export type VoiceTurnDeadlineScheduling = {
  schedule(
    deadline: VoiceTurnDeadline,
    afterSeconds: number,
    fire: () => void
  ): VoiceTurnDeadlineCancellation
}

export const timeoutVoiceTurnScheduler: VoiceTurnDeadlineScheduling = {
  schedule(_deadline, afterSeconds, fire) {
    const handle = setTimeout(fire, afterSeconds * 1000)
    return { cancel: () => clearTimeout(handle) }
  }
}

export type VoiceTurnEffectHandler = (effect: VoiceTurnEffect) => void
export type VoiceTurnSnapshotHandler = (model: VoiceTurnModel) => void

/** The bar/orb store. macOS's `PTTBarPresenter` is the same seam. */
export type VoiceTurnPresenter = { apply(projection: VoiceTurnUIProjection): void }

export type VoiceTurnDiagnostics = {
  recordVoiceTurnTerminal(entry: {
    reason: string
    route: string
    staleEventCount: number
    invalidTransitionCount: number
  }): void
  recordVoiceTurnAnomaly(entry: { kind: string; phase: string; route: string }): void
}

/** macOS's `PTTBarPresenter` expand rule (`VoiceTurnCoordinator.swift:58`): the
 *  pill stays expanded while listening AND while a terminal hint is visible. */
export function expandsBarForVoice(projection: VoiceTurnUIProjection): boolean {
  return projection.isListening || projection.hint !== ''
}

// MARK: - Timeline

export type VoiceTurnTimelineEntry = {
  readonly sequence: number
  readonly turnID: VoiceTurnID | null
  /** `diagnosticLabel(event)` — a bounded label, never a payload. */
  readonly event: string
  readonly phaseBefore: VoiceTurnPhase | null
  readonly phaseAfter: VoiceTurnPhase | null
  readonly route: VoiceTurnRoute | null
  readonly terminalReason: VoiceTurnTerminalReason | null
  readonly staleEventCount: number
  readonly invalidTransitionCount: number
}

export function voiceTurnPhaseLabel(phase: VoiceTurnPhase): string {
  switch (phase.kind) {
    case 'idle':
      return 'idle'
    case 'pendingLockDecision':
      return 'pending_lock_decision'
    case 'recording':
      return 'recording'
    case 'lockedRecording':
      return 'locked_recording'
    case 'finalizing':
      return 'finalizing'
    case 'awaitingResponse':
      return 'awaiting_response'
    case 'awaitingTools':
      return 'awaiting_tools'
    case 'playing':
      return `playing_${VOICE_OUTPUT_LANE_RAW[phase.lane]}`
    case 'terminal':
      return `terminal_${VOICE_TURN_TERMINAL_REASON_RAW[phase.reason]}`
  }
}

export function voiceTurnRouteLabel(route: VoiceTurnRoute): string {
  switch (route.kind) {
    case 'undecided':
      return 'undecided'
    case 'hubWarmWait':
      return 'hub_warm_wait'
    case 'hub':
      return 'hub'
    case 'omniSTT':
      return 'omni_stt'
    case 'deepgramBatch':
      return 'deepgram_batch'
    case 'deepgramLive':
      return 'deepgram_live'
    case 'agentFollowUp':
      return 'agent_follow_up'
  }
}

// MARK: - Coordinator

export type VoiceTurnCoordinatorOptions = {
  model?: VoiceTurnModel
  scheduler?: VoiceTurnDeadlineScheduling
  timelineLimit?: number
  /** The ONLY place a real PTT press manufactures a turn identity. */
  mintTurnID?: () => VoiceTurnID
  diagnostics?: VoiceTurnDiagnostics
}

const deadlineKey = (turnID: VoiceTurnID, deadline: VoiceTurnDeadline): string =>
  `${turnID}\u0000${deadline}`

export class VoiceTurnCoordinator {
  private readonly scheduler: VoiceTurnDeadlineScheduling
  private readonly timelineLimit: number
  private readonly mintTurnID: () => VoiceTurnID
  private readonly diagnostics: VoiceTurnDiagnostics | null

  private readonly deadlineCancellations = new Map<
    string,
    { turnID: VoiceTurnID; cancellation: VoiceTurnDeadlineCancellation }
  >()
  private presenter: VoiceTurnPresenter | null = null
  private effectHandler: VoiceTurnEffectHandler | null = null
  private snapshotHandler: VoiceTurnSnapshotHandler | null = null
  private timeline: VoiceTurnTimelineEntry[] = []
  private timelineSequence = 0
  private pendingEvents: VoiceTurnEvent[] = []
  private isDrainingEvents = false

  model: VoiceTurnModel

  constructor(options: VoiceTurnCoordinatorOptions = {}) {
    this.model = options.model ?? IDLE_VOICE_TURN_MODEL
    this.scheduler = options.scheduler ?? timeoutVoiceTurnScheduler
    this.timelineLimit = Math.max(1, options.timelineLimit ?? 256)
    this.mintTurnID = options.mintTurnID ?? (() => crypto.randomUUID() as VoiceTurnID)
    this.diagnostics = options.diagnostics ?? null
  }

  /** `null` whenever the turn is terminal — hosts must never treat a terminal
   *  turn as active (A7c's `canReplaceSession` is built on this). */
  get activeTurnID(): VoiceTurnID | null {
    const turn = this.model.turn
    return turn !== null && !isTerminal(turn.phase) ? turn.id : null
  }

  get activeTurn(): VoiceTurnModel['turn'] {
    const turn = this.model.turn
    return turn !== null && !isTerminal(turn.phase) ? turn : null
  }

  get projection(): VoiceTurnUIProjection {
    return projectionOf(this.model)
  }

  configure(presenter: VoiceTurnPresenter | null): void {
    this.presenter = presenter
    this.contain('presenter', () => presenter?.apply(this.projection))
  }

  setEffectHandler(handler: VoiceTurnEffectHandler | null): void {
    this.effectHandler = handler
  }

  setSnapshotHandler(handler: VoiceTurnSnapshotHandler | null): void {
    this.snapshotHandler = handler
    this.contain('snapshot_handler', () => handler?.(this.model))
  }

  /** The only place a `VoiceTurnID` is manufactured for a real PTT press. */
  begin(intent: VoiceTurnIntent, id: VoiceTurnID = this.mintTurnID()): VoiceTurnID {
    if (this.model.turn !== null && isTerminal(this.model.turn.phase)) {
      this.send({ type: 'reset' })
    }
    this.send({ type: 'start', turnID: id, intent })
    return id
  }

  /**
   * FIFO, non-reentrant. A `send` from inside an effect or snapshot handler
   * appends and returns immediately — the outer loop reaches it at the next
   * index, so callback depth stays 1 and no event is reduced against a
   * half-published transition.
   */
  send(event: VoiceTurnEvent): void {
    this.pendingEvents.push(event)
    if (this.isDrainingEvents) return

    this.isDrainingEvents = true
    try {
      // Index-based on purpose: the array is EXPECTED to grow during iteration.
      for (let index = 0; index < this.pendingEvents.length; index += 1) {
        this.apply(this.pendingEvents[index])
      }
    } finally {
      // Swift clears + unsets in a `defer`, so a throwing handler still leaves
      // the coordinator drainable instead of wedging PTT permanently.
      this.pendingEvents = []
      this.isDrainingEvents = false
    }
  }

  timelineSnapshot(): VoiceTurnTimelineEntry[] {
    return [...this.timeline]
  }

  refreshPresentation(): void {
    this.presenter?.apply(this.projection)
  }

  /** Non-PTT chat playback shares the pill but must not bypass the presentation
   *  owner: a late chat callback cannot clear an active turn's glow. */
  setUnscopedResponseActive(active: boolean): void {
    if (this.activeTurnID !== null) return
    this.presenter?.apply({
      ...this.projection,
      isResponseWaiting: false,
      isResponseActive: active
    })
  }

  reset(): void {
    if (this.model.turn !== null) {
      this.send({ type: 'cleanup' })
      this.send({ type: 'reset' })
    }
    for (const { cancellation } of this.deadlineCancellations.values()) cancellation.cancel()
    this.deadlineCancellations.clear()
    this.presenter?.apply(IDLE_PROJECTION)
  }

  /** Applies one event atomically before any callback can advance the machine. */
  private apply(event: VoiceTurnEvent): void {
    const before = this.model
    const reduction = reduceVoiceTurn(
      before,
      event,
      deadlinesForVoiceTurnRoute(this.routeFor(event))
    )
    this.model = reduction.model
    this.appendTimeline(event, before, this.model)
    this.process(reduction.effects)
    this.contain('presenter', () => this.presenter?.apply(this.projection))
    this.contain('snapshot_handler', () => this.snapshotHandler?.(this.model))
  }

  /** Run one collaborator callback, containing any synchronous throw so it can
   *  never abort the drain (skip deadline scheduling / later effects / the
   *  projection publish) or drop queued events — the permanent-wedge class. */
  private contain(kind: string, call: () => void): void {
    try {
      call()
    } catch (err) {
      console.error(
        `[voice-turn] ${kind} threw; containing so the turn machine keeps running:`,
        err
      )
      this.diagnostics?.recordVoiceTurnAnomaly({
        kind: `${kind}_threw`,
        phase: this.model.turn ? voiceTurnPhaseLabel(this.model.turn.phase) : 'idle',
        route: this.model.turn ? voiceTurnRouteLabel(this.model.turn.route) : 'none'
      })
    }
  }

  /** The route this event's deadlines belong to. `selectRoute` and a fired
   *  `hubWarm` (which hands the buffer to the cascade and arms its transcription
   *  deadline in the same reduce) change the route DURING the reduce, so the
   *  pre-event route would pick the wrong budget for exactly those two. */
  private routeFor(event: VoiceTurnEvent): VoiceTurnRoute {
    if (event.type === 'selectRoute') return event.route
    if (event.type === 'deadlineFired' && event.deadline === 'hubWarm') {
      return { kind: 'deepgramBatch' }
    }
    return this.model.turn?.route ?? { kind: 'undecided' }
  }

  /** Timers + diagnostics only. State transitions are the reducer's job. Every
   *  effect is then forwarded to the host — including the three timer effects,
   *  which macOS consumes instead (see the deviation note at the top). */
  private process(effects: VoiceTurnEffect[]): void {
    for (const effect of effects) {
      switch (effect.kind) {
        case 'scheduleDeadline':
          this.scheduleDeadline(effect.turnID, effect.deadline, effect.after)
          break
        case 'cancelDeadline':
          this.cancelDeadline(effect.turnID, effect.deadline)
          break
        case 'cancelAllDeadlines':
          this.cancelAllDeadlines(effect.turnID)
          break
        case 'terminal':
          this.diagnostics?.recordVoiceTurnTerminal({
            reason: VOICE_TURN_TERMINAL_REASON_RAW[effect.record.reason],
            route: voiceTurnRouteLabel(effect.record.route),
            staleEventCount: this.model.staleEventCount,
            invalidTransitionCount: this.model.invalidTransitionCount
          })
          break
        case 'staleEventDropped':
          this.diagnostics?.recordVoiceTurnAnomaly({
            kind: 'stale_event',
            phase: this.model.turn ? voiceTurnPhaseLabel(this.model.turn.phase) : 'idle',
            route: this.model.turn ? voiceTurnRouteLabel(this.model.turn.route) : 'none'
          })
          break
        case 'invalidTransition':
          this.diagnostics?.recordVoiceTurnAnomaly({
            kind: 'invalid_transition',
            phase: effect.phase ? voiceTurnPhaseLabel(effect.phase) : 'idle',
            route: this.model.turn ? voiceTurnRouteLabel(this.model.turn.route) : 'none'
          })
          break
        default:
          break
      }
      this.contain('effect_handler', () => this.effectHandler?.(effect))
    }
  }

  private scheduleDeadline(
    turnID: VoiceTurnID,
    deadline: VoiceTurnDeadline,
    afterSeconds: number
  ): void {
    const key = deadlineKey(turnID, deadline)
    // Re-scheduling a held deadline resets the timer — drop the old handle first.
    this.deadlineCancellations.get(key)?.cancellation.cancel()
    const cancellation = this.scheduler.schedule(deadline, afterSeconds, () => {
      this.deadlineCancellations.delete(key)
      this.send({ type: 'deadlineFired', turnID, deadline })
    })
    this.deadlineCancellations.set(key, { turnID, cancellation })
  }

  private cancelDeadline(turnID: VoiceTurnID, deadline: VoiceTurnDeadline): void {
    const key = deadlineKey(turnID, deadline)
    const held = this.deadlineCancellations.get(key)
    if (held === undefined) return
    this.deadlineCancellations.delete(key)
    held.cancellation.cancel()
  }

  private cancelAllDeadlines(turnID: VoiceTurnID): void {
    for (const [key, held] of [...this.deadlineCancellations.entries()]) {
      if (held.turnID !== turnID) continue
      this.deadlineCancellations.delete(key)
      held.cancellation.cancel()
    }
  }

  private appendTimeline(
    event: VoiceTurnEvent,
    before: VoiceTurnModel,
    after: VoiceTurnModel
  ): void {
    this.timelineSequence += 1
    const eventTurnID = turnIDOf(event)
    // Swift uses a DIFFERENT id expression for each of these two (`:291` vs
    // `:296`): the terminal match deliberately has no `before` fallback, so a
    // `reset` (which clears the turn) does not re-stamp the old terminal reason.
    const turnID = eventTurnID ?? after.turn?.id ?? before.turn?.id ?? null
    const terminalMatchID = eventTurnID ?? after.turn?.id ?? null
    this.timeline.push({
      sequence: this.timelineSequence,
      turnID,
      event: diagnosticLabel(event),
      phaseBefore: before.turn?.phase ?? null,
      phaseAfter: after.turn?.phase ?? null,
      route: after.turn?.route ?? null,
      terminalReason:
        after.lastTerminal !== null &&
        terminalMatchID !== null &&
        after.lastTerminal.turnID === terminalMatchID
          ? after.lastTerminal.reason
          : null,
      staleEventCount: after.staleEventCount,
      invalidTransitionCount: after.invalidTransitionCount
    })
    if (this.timeline.length > this.timelineLimit) {
      this.timeline = this.timeline.slice(this.timeline.length - this.timelineLimit)
    }
  }
}
