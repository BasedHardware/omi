// Per-turn silent-mic (dead-mic) escalation — the cross-turn counterpart to
// gate.ts's single-turn gateDecision. Port of the macOS PTTSilentMicRecoveryPolicy
// (PushToTalkManager.swift): count CONSECUTIVE dead-mic PTT turns and escalate — at
// 2 rebuild the capture stack, at 3 surface a stronger "check your mic / restart"
// hint and emit a distinct telemetry event. The counter resets on any completed
// turn that was NOT dead-mic (a good transcribe, a live-room silence, a too-short
// tap). Detection thresholds are unchanged — gate.ts still decides "dead-mic";
// this only accumulates that decision across turns.
import { trackEvent } from '../analytics'

/** Consecutive dead-mic turns that trigger a capture-stack rebuild (macOS
 *  PTTSilentMicRecoveryPolicy.consecutiveDeadTurnThreshold). */
export const DEAD_MIC_REBUILD_TURNS = 2
/** Consecutive dead-mic turns that escalate to the strong hint + a distinct
 *  telemetry event (macOS DesktopDiagnosticsManager.pttWatchdogThreshold). */
export const DEAD_MIC_ESCALATE_TURNS = 3

export type DeadMicAction = 'none' | 'rebuild' | 'escalate'

/** Stateful across turns — one instance per PTT hook. Records the terminal
 *  classification of each completed turn and returns the escalation action. */
export class DeadMicPolicy {
  private consecutive = 0

  /** @param dead — the completed turn was classed dead-mic (flat-line input). */
  record(dead: boolean): DeadMicAction {
    if (!dead) {
      this.consecutive = 0
      return 'none'
    }
    this.consecutive++
    if (this.consecutive === DEAD_MIC_ESCALATE_TURNS) return 'escalate'
    if (this.consecutive === DEAD_MIC_REBUILD_TURNS) return 'rebuild'
    return 'none'
  }

  get count(): number {
    return this.consecutive
  }
}

/** Which dead-mic hint to show (base guidance vs. the escalated restart prompt). */
export type DeadMicHint = 'dead-mic' | 'dead-mic-escalated'

/** Feed one completed FOREGROUND turn into the policy and fire the resulting
 *  effects: at 2 consecutive dead turns rebuild the capture stack (degraded
 *  telemetry); at 3 escalate + emit a distinct exhausted event. The hint escalates
 *  from turn 3 on. `rebuild`/`showHint` are injected — IPC + React state in the
 *  hook, spies in tests. */
export function applyDeadMicTurn(
  policy: DeadMicPolicy,
  dead: boolean,
  fx: { rebuild: () => void; showHint: (hint: DeadMicHint) => void }
): void {
  const action = policy.record(dead)
  if (action === 'rebuild') {
    fx.rebuild()
    trackEvent('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'rebuilt',
      reason: 'local_heal',
      outcome: 'degraded'
    })
  } else if (action === 'escalate') {
    trackEvent('fallback_triggered', {
      component: 'silent_mic',
      from: 'default_device',
      to: 'none',
      reason: 'local_heal',
      outcome: 'exhausted'
    })
  }
  if (dead) fx.showHint(policy.count >= DEAD_MIC_ESCALATE_TURNS ? 'dead-mic-escalated' : 'dead-mic')
}
