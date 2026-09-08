// The voice-plane SUPERVISOR (2026-07-18) — the contract, enforced at the
// OUTERMOST seam: every completed press-and-release MUST produce, within a
// bounded window, exactly one observable terminal — reply playback started,
// text committed into the chat pipeline, or a visible hint/error. If none
// arrives, the plane is declared wedged: the host shows a failure chip, resets
// the ENTIRE voice stack (`resetVoicePlane`), and dumps the flight recorder.
//
// It lives on the BAR side, where the press originates — deliberately OUTSIDE
// the turn machine / driver / hub, so no interior failure (a wedged coordinator,
// a dead driver window, a broken IPC channel) can disable it. Voice died
// silently three different ways in one day; each interior fix was correct and
// each was insufficient, because variant N+1 always lands somewhere new. This
// class is pure (timers injected) so the contract itself is unit-tested.
//
// INERT ON HEALTHY TURNS — two mechanisms, both required (2026-07-18 audit
// M1/M2):
//   * "Machine reconciled" counts as a terminal. A silent hold is DISCARDED
//     quietly by design (hub `silentRejected` has no hint; the local lane's
//     silent gate likewise) — the machine returning to idle IS the observable
//     outcome at this seam, and a genuinely wedged turn never reconciles
//     (active/recording stays latched). Machine-level liveness is what this
//     seam can honestly judge; audibility beyond it belongs to INV-VOICE-1
//     and the mute/restore flight events.
//   * The window bounds time-since-last-OBSERVED-PROGRESS, not total turn
//     time. `noteProgress` (fed by the projection `seq`, which bumps only on
//     real reducer transitions) re-arms the watch, so a legitimate multi-round
//     tool turn — which can exceed any fixed total budget (each round re-arms
//     its own 20 s/30 s reducer deadlines) — keeps proving liveness, while a
//     wedged turn emits no transitions and its watch runs to the deadline.
//     Health = observed dataflow, not elapsed time (the Pipecat heartbeat
//     doctrine).
// The window must still comfortably exceed the LONGEST gap between observable
// events inside a healthy turn (worst known: the cascade's 20 s batch budget,
// and the driver's 45 s release watchdog which itself ends in an observable
// hint) — hence 60 s. The supervisor adds one armed timer per release and
// nothing else: no added latency, no double-terminals.

/** Must exceed the longest observable-event GAP in a healthy turn (the 45 s
 *  release watchdog is the slowest interior layer that still ends in a visible
 *  hint) — see the header. Overridable for tests / tuning. */
export const VOICE_SUPERVISOR_TIMEOUT_MS = 60_000

export type VoiceSupervisorLane = 'hub' | 'local'

export type VoicePlaneSupervisorDeps = {
  /** The plane produced NO observable terminal within the window after a
   *  completed release — reset it. */
  onFire: (info: { lane: VoiceSupervisorLane }) => void
  timeoutMs?: number
  /** Injectable timer (tests drive it manually). */
  schedule?: (fire: () => void, ms: number) => { cancel(): void }
  /** Observability tap (the flight recorder). Optional, throw-contained. */
  record?: (type: string, data?: Record<string, unknown>) => void
}

export class VoicePlaneSupervisor {
  private readonly deps: VoicePlaneSupervisorDeps
  private readonly timeoutMs: number
  private readonly schedule: (fire: () => void, ms: number) => { cancel(): void }
  private pending: { cancel(): void } | null = null
  private pendingLane: VoiceSupervisorLane = 'local'
  /** An abort (Esc / focus loss / plane reset) between press and release: the
   *  turn was never completed, so the release that follows owes no terminal.
   *  Consumed by exactly one noteRelease; cleared by the next press. */
  private cancelledSincePress = false
  private disposed = false

  constructor(deps: VoicePlaneSupervisorDeps) {
    this.deps = deps
    this.timeoutMs = deps.timeoutMs ?? VOICE_SUPERVISOR_TIMEOUT_MS
    this.schedule =
      deps.schedule ??
      ((fire, ms) => {
        const handle = setTimeout(fire, ms)
        return { cancel: () => clearTimeout(handle) }
      })
  }

  get armed(): boolean {
    return this.pending !== null
  }

  /** A new press supersedes any pending watch — the new turn's release re-arms. */
  notePress(): void {
    this.disarm()
    this.cancelledSincePress = false
  }

  /** A completed press-and-release with a live turn: from here the plane owes an
   *  observable terminal within the window. Ignored when the press was aborted
   *  (no turn to answer for) — an abort is not a completed press-and-release. */
  noteRelease(lane: VoiceSupervisorLane): void {
    if (this.disposed) return
    if (this.cancelledSincePress) {
      this.cancelledSincePress = false
      return
    }
    this.pendingLane = lane
    this.record('supervisor_arm', { lane, timeoutMs: this.timeoutMs })
    this.arm()
  }

  /** The turn was aborted (Esc, focus loss, an external voice-plane reset):
   *  disarm, and swallow the release that may still be in flight behind the
   *  cancel (bar→main→bar state lag would otherwise re-arm on a dead turn). */
  noteCancel(): void {
    this.cancelledSincePress = true
    this.disarm()
  }

  /** ANY observable terminal — reply playback started, text entered the chat
   *  pipeline, a visible hint/error, or the machine reconciling to idle —
   *  satisfies the contract. A `lane`-scoped terminal (e.g. the hub turn
   *  reconciling) only clears a watch armed for that lane, so one lane's
   *  reconcile can never absolve the other's stuck turn. */
  noteTerminal(kind: string, lane?: VoiceSupervisorLane): void {
    if (this.pending === null) return
    if (lane !== undefined && lane !== this.pendingLane) return
    this.record('supervisor_terminal', { kind, lane: this.pendingLane })
    this.disarm()
  }

  /** Observed phase progress (a reducer transition reached the bar): the turn
   *  is demonstrably alive, so the watch's clock restarts — the window bounds
   *  time-BETWEEN-observations, not total turn time (audit M2: a healthy
   *  multi-round tool turn legitimately outlives any fixed total budget). A
   *  wedged turn emits no transitions, so its watch still runs out. */
  noteProgress(lane?: VoiceSupervisorLane): void {
    if (this.disposed || this.pending === null) return
    if (lane !== undefined && lane !== this.pendingLane) return
    this.arm()
  }

  dispose(): void {
    this.disposed = true
    this.disarm()
  }

  /** (Re)start the watch's clock for the current pendingLane. */
  private arm(): void {
    this.disarm()
    this.pending = this.schedule(() => {
      this.pending = null
      this.record('supervisor_fired', { lane: this.pendingLane })
      this.deps.onFire({ lane: this.pendingLane })
    }, this.timeoutMs)
  }

  private disarm(): void {
    this.pending?.cancel()
    this.pending = null
  }

  private record(type: string, data?: Record<string, unknown>): void {
    try {
      this.deps.record?.(type, data)
    } catch {
      /* observability must never break the supervisor */
    }
  }
}
