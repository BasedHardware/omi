/**
 * Visit coordinator — port of macOS ContextVisitCoordinator: the serialized
 * state machine that opens and closes context visits as the user moves between
 * windows, with startup reconcile, 24-hour GC cadence, sleep/wake handling,
 * and staleFence recovery (drop in-memory state, force re-reconcile).
 *
 * Serialization uses a promise-chain turn queue (the actor-FIFO analog): every
 * public operation runs to completion before the next starts, so a burst of
 * context switches can never interleave finalize/start pairs.
 */

import type { ContextVisitFence, StartVisitInput } from '../../ipc/contextBucketStore'
import type { WorkHandle } from './workHandles'

export const VISIT_QUALIFICATION_MS = 1_000
export const GC_INTERVAL_MS = 24 * 60 * 60 * 1000

export interface VisitCoordinatorDeps {
  startVisit(input: StartVisitInput): ContextVisitFence
  finalizeVisit(
    fence: ContextVisitFence,
    opts: {
      outcome: 'completed' | 'discarded' | 'interrupted'
      exitReason: string
      endedAt: number
      lastFrameId: number | null
    }
  ): boolean
  reconcileInterruptedVisits(now: number): number
  reconcileAbandonedDeliveries(now: number): number
  runDeterministicGC(now: number): void
  poolEpoch(): number
  now(): number
}

export interface TransitionInput {
  toApp: string
  toWindowTitle: string | null
  handles: WorkHandle[]
  processName: string | null
  departingFrameId: number | null
}

export interface TransitionResult {
  departed: { fence: ContextVisitFence; outcome: 'completed' | 'discarded' } | null
  arriving: ContextVisitFence
}

export class ContextVisitCoordinator {
  private readonly deps: VisitCoordinatorDeps
  private active: ContextVisitFence | null = null
  private generation = 0
  private reconciled = false
  private lastGCAt = 0
  private queue: Promise<unknown> = Promise.resolve()

  constructor(deps: VisitCoordinatorDeps) {
    this.deps = deps
  }

  /** Serialize an operation on the turn queue. */
  private enqueue<T>(fn: () => T): Promise<T> {
    const turn = this.queue.then(() => fn())
    // The queue never rejects: a failed turn must not poison later turns.
    this.queue = turn.then(
      () => undefined,
      () => undefined
    )
    return turn
  }

  private ensureReconciled(now: number): void {
    if (this.reconciled) return
    this.deps.reconcileInterruptedVisits(now)
    this.deps.reconcileAbandonedDeliveries(now)
    this.deps.runDeterministicGC(now)
    this.lastGCAt = now
    this.reconciled = true
  }

  private maybeGC(now: number): void {
    if (now - this.lastGCAt < GC_INTERVAL_MS) return
    this.deps.runDeterministicGC(now)
    this.deps.reconcileAbandonedDeliveries(now)
    this.lastGCAt = now
  }

  /** Close the active visit: completed at >= 1s dwell, discarded below it. */
  private finalizeActive(
    exitReason: string,
    endedAt: number,
    lastFrameId: number | null
  ): { fence: ContextVisitFence; outcome: 'completed' | 'discarded' } | null {
    const departing = this.active
    if (departing === null) return null
    this.active = null
    const qualified = endedAt - departing.startedAt >= VISIT_QUALIFICATION_MS
    const outcome = qualified ? 'completed' : 'discarded'
    const ok = this.deps.finalizeVisit(departing, { outcome, exitReason, endedAt, lastFrameId })
    if (!ok) {
      // staleFence: drop state and force a re-reconcile on the next turn.
      this.reconciled = false
      return null
    }
    return { fence: departing, outcome }
  }

  transition(input: TransitionInput): Promise<TransitionResult> {
    return this.enqueue(() => {
      const now = this.deps.now()
      this.ensureReconciled(now)
      this.maybeGC(now)
      const departed = this.finalizeActive('context_switch', now, input.departingFrameId)
      this.generation += 1
      const arriving = this.deps.startVisit({
        contextGeneration: this.generation,
        poolEpoch: this.deps.poolEpoch(),
        appName: input.toApp,
        windowTitle: input.toWindowTitle,
        handles: input.handles,
        processName: input.processName,
        startedAt: now
      })
      this.active = arriving
      return { departed, arriving }
    })
  }

  /** Switch into a privacy-excluded context: close the visit, open nothing. */
  leaveForExcludedContext(departingFrameId: number | null): Promise<void> {
    return this.enqueue(() => {
      const now = this.deps.now()
      this.ensureReconciled(now)
      this.finalizeActive('excluded_context', now, departingFrameId)
    })
  }

  /** Sleep/lock interrupts the active visit — guarded so a delayed event can
   *  never kill a visit opened after it. */
  interruptForSleep(eventTime: number): Promise<void> {
    return this.enqueue(() => {
      const departing = this.active
      if (departing === null) return
      if (departing.startedAt > eventTime) return
      this.active = null
      const ok = this.deps.finalizeVisit(departing, {
        outcome: 'interrupted',
        exitReason: 'system_sleep',
        endedAt: this.deps.now(),
        lastFrameId: null
      })
      if (!ok) this.reconciled = false
    })
  }

  /** Wake/unlock: finalize any leftover visit, then reopen the still-frontmost
   *  context as a fresh visit. */
  rearmAfterSystemResume(input: TransitionInput): Promise<ContextVisitFence> {
    return this.enqueue(() => {
      const now = this.deps.now()
      this.ensureReconciled(now)
      this.finalizeActive('system_resume', now, input.departingFrameId)
      this.generation += 1
      const arriving = this.deps.startVisit({
        contextGeneration: this.generation,
        poolEpoch: this.deps.poolEpoch(),
        appName: input.toApp,
        windowTitle: input.toWindowTitle,
        handles: input.handles,
        processName: input.processName,
        startedAt: now
      })
      this.active = arriving
      return arriving
    })
  }

  /** Owner or pool change: drop in-memory state; the next turn re-reconciles. */
  reset(): Promise<void> {
    return this.enqueue(() => {
      this.active = null
      this.reconciled = false
    })
  }

  activeFence(): ContextVisitFence | null {
    return this.active
  }
}
