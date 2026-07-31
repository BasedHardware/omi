// Shared main-process fallback/degrade telemetry sink.
//
// AGENTS.md ("Fallback / resilience telemetry") mandates a single shared emitter
// per language rather than one-off counters/events. The canonical emitters are
// Python/Swift/Rust; on the Windows main process there was until now no shared
// helper, so degrade paths each grew their own structured `console.warn` (see the
// tool_relay bridge's local `defaultRecordFallback`). This is that shared Windows
// emitter: a fixed-field structured line every fail-open/degrade site can route
// through, so the fields stay uniform and greppable (`[fallback]`).
//
// Deliberately just a structured console line — there is no Windows metrics
// pipeline to feed. It matches the established Windows pattern (billing.ts,
// aiUserProfile, toolRelayBridge). Callers that want a custom sink (tests) inject
// their own function; production uses this default.

/** Coarse subsystem the degrade happened in. Closed set → `other` (AGENTS.md). */
export type FallbackComponent =
  | 'backend_fetch'
  | 'sync_dispatch'
  | 'realtime_hub'
  | 'ptt_cascade'
  | 'tool_relay'
  | 'other'

/** What the degrade branch achieved. `recovered` = full UX restored, `degraded` =
 *  continues with a hit, `exhausted` = no path left (AGENTS.md outcome enum). */
export type FallbackOutcome = 'recovered' | 'degraded' | 'exhausted'

export interface FallbackEvent {
  component: FallbackComponent
  /** Prior provider/mode, or `none`. */
  from: string
  /** New provider/mode, or `none`. */
  to: string
  /** Bounded reason from the shared set → else `other`. */
  reason: string
  outcome: FallbackOutcome
  /** Optional extra context (counts, windows) — kept flat and small. */
  [extra: string]: unknown
}

export type RecordFallback = (event: FallbackEvent) => void

/** The production sink: one fixed-field structured warn line. */
export const recordFallback: RecordFallback = (event) => {
  console.warn('[fallback]', event)
}
