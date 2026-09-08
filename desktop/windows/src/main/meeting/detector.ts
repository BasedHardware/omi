// Pure meeting-detection state machine. NO Electron, NO koffi, NO timers — the
// orchestrator (meetingMonitor.ts) feeds it signals + `now` and schedules a
// re-step at the returned `deadline`. Exhaustively unit-testable with fake
// signals (detector.test.ts).
//
//   idle ──tier1──► candidate ──tier1+tier2 agree, debounced──► active
//   active ──tier2 quiet──► ending ──quiet ≥ endGraceMs──► (ended) ──► idle
//   ending ──tier2 back──► active
//
// Once active, Tier 1 is no longer required (the user may switch away from the
// Meet tab mid-meeting); staying active / ending is driven purely by Tier 2
// (is the meeting app still holding the mic?). The machine latches the agreed
// app's `tier2Key`, so "same app" correlation is exact.
//
// Mode policy (off / ask / auto, with per-app overrides) is resolved HERE so
// the whole decision surface is pure-tested: entering active emits a
// 'meeting-started' effect carrying the effective mode ('ask' | 'auto'), or no
// effect at all when the effective mode is 'off' (the state still latches so
// the same meeting isn't re-evaluated every step).
import type { AgreedMatch } from './patterns'
// Type-only import — the machine stays pure (no Electron, no runtime deps).
import type { MeetingMode } from '../../shared/types'

export type { MeetingMode }

export type DetectorConfig = {
  /** Tier1+Tier2 must agree continuously this long before 'active' (~3s). */
  debounceMs: number
  /** Tier 2 quiet this long ends the meeting (default 2 min). */
  endGraceMs: number
  /** Global mode. */
  mode: MeetingMode
  /** Per-app overrides, keyed by pattern id ('zoom', 'meet-web', …). */
  perApp: Record<string, MeetingMode>
}

/** One evaluation of the world, computed by the orchestrator from a process
 *  snapshot + foreground window (Tier 1) and the mic ConsentStore (Tier 2). */
export type DetectorSignals = {
  /** Any Tier 1 match present (conferencing app running / meeting tab title). */
  candidate: boolean
  /** The Tier1+Tier2-correlated match, when both tiers point at the same app. */
  agreed: AgreedMatch | null
  /** All ConsentStore ids currently capturing the mic (lowercase). */
  tier2Ids: string[]
}

export type DetectorState =
  | { phase: 'idle' }
  | { phase: 'candidate'; agreed: AgreedMatch | null; agreedSince: number | null }
  | { phase: 'active'; match: AgreedMatch }
  | { phase: 'ending'; match: AgreedMatch; quietSince: number }

export type DetectorEffect =
  | { type: 'meeting-started'; match: AgreedMatch; mode: 'ask' | 'auto' }
  | { type: 'meeting-ended'; match: AgreedMatch }

export type StepResult = {
  state: DetectorState
  effects: DetectorEffect[]
  /** Absolute time at which the orchestrator should re-step (debounce or end
   *  grace expiry), or null when no timer is needed. */
  deadline: number | null
}

export const initialDetectorState: DetectorState = { phase: 'idle' }

export function effectiveMode(match: AgreedMatch, cfg: DetectorConfig): MeetingMode {
  return cfg.perApp[match.id] ?? cfg.mode
}

/** Advance the machine with fresh signals at time `now`. Pure. */
export function step(
  state: DetectorState,
  sig: DetectorSignals,
  now: number,
  cfg: DetectorConfig
): StepResult {
  switch (state.phase) {
    case 'idle': {
      if (sig.agreed || sig.candidate) {
        // Agreement can appear without a plain candidate flag (packaged apps
        // are only visible via Tier 2) — treat it as candidacy either way.
        return step(
          { phase: 'candidate', agreed: null, agreedSince: null },
          sig,
          now,
          cfg
        )
      }
      return { state, effects: [], deadline: null }
    }

    case 'candidate': {
      if (!sig.candidate && !sig.agreed) {
        return { state: initialDetectorState, effects: [], deadline: null }
      }
      if (!sig.agreed) {
        // Tier 1 still present but agreement dropped — reset the debounce.
        return {
          state: { phase: 'candidate', agreed: null, agreedSince: null },
          effects: [],
          deadline: null
        }
      }
      const sameApp = state.agreed?.id === sig.agreed.id
      const since = sameApp && state.agreedSince !== null ? state.agreedSince : now
      if (now - since >= cfg.debounceMs) {
        const mode = effectiveMode(sig.agreed, cfg)
        return {
          state: { phase: 'active', match: sig.agreed },
          // 'off' latches active silently: no toast, no capture, no re-eval churn.
          effects:
            mode === 'off' ? [] : [{ type: 'meeting-started', match: sig.agreed, mode }],
          deadline: null
        }
      }
      return {
        state: { phase: 'candidate', agreed: sig.agreed, agreedSince: since },
        effects: [],
        deadline: since + cfg.debounceMs
      }
    }

    case 'active': {
      if (sig.tier2Ids.includes(state.match.tier2Key)) {
        return { state, effects: [], deadline: null }
      }
      return {
        state: { phase: 'ending', match: state.match, quietSince: now },
        effects: [],
        deadline: now + cfg.endGraceMs
      }
    }

    case 'ending': {
      if (sig.tier2Ids.includes(state.match.tier2Key)) {
        // Mic came back within the grace window — same meeting continues.
        return { state: { phase: 'active', match: state.match }, effects: [], deadline: null }
      }
      if (now - state.quietSince >= cfg.endGraceMs) {
        const ended: StepResult = {
          state: initialDetectorState,
          effects: [{ type: 'meeting-ended', match: state.match }],
          deadline: null
        }
        // Re-arm immediately: if signals already show a NEW meeting, start its
        // candidacy in the same step (effects concatenate).
        const next = step(ended.state, sig, now, cfg)
        return {
          state: next.state,
          effects: [...ended.effects, ...next.effects],
          deadline: next.deadline
        }
      }
      return { state, effects: [], deadline: state.quietSince + cfg.endGraceMs }
    }
  }
}
