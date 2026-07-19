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
// INERT ON HEALTHY TURNS — the design constraint that picked the timeout:
// every layer below self-terminates faster (reducer deadlines incl. the 30 s
// pendingTools budget, the cascade's 20 s batch-transcription budget, the
// driver's 45 s release watchdog) and each of those produces an observable
// terminal (a hint at worst) that disarms this watch. The supervisor may only
// fire when ALL of that machinery failed to produce anything a user can see —
// so its window must comfortably outlast the slowest legitimate interior bound
// (45 s), never race it. It adds one armed timer per release and nothing else:
// no added latency, no double-terminals.

/** Must exceed the driver's 45 s release watchdog (the slowest interior layer)
 *  with margin — see the header. Overridable for tests / tuning. */
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
    this.disarm()
    this.pendingLane = lane
    this.record('supervisor_arm', { lane, timeoutMs: this.timeoutMs })
    this.pending = this.schedule(() => {
      this.pending = null
      this.record('supervisor_fired', { lane: this.pendingLane })
      this.deps.onFire({ lane: this.pendingLane })
    }, this.timeoutMs)
  }

  /** The turn was aborted (Esc, focus loss, an external voice-plane reset):
   *  disarm, and swallow the release that may still be in flight behind the
   *  cancel (bar→main→bar state lag would otherwise re-arm on a dead turn). */
  noteCancel(): void {
    this.cancelledSincePress = true
    this.disarm()
  }

  /** ANY observable terminal — reply playback started, text entered the chat
   *  pipeline, a visible hint/error — satisfies the contract. */
  noteTerminal(kind: string): void {
    if (this.pending === null) return
    this.record('supervisor_terminal', { kind, lane: this.pendingLane })
    this.disarm()
  }

  dispose(): void {
    this.disposed = true
    this.disarm()
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
