/**
 * Shared fallback / resilience telemetry for the Windows main process.
 *
 * Same field contract as Python `record_fallback`, Swift
 * `DesktopDiagnosticsManager.recordFallback` and Rust `fallback::record_fallback`
 * (see docs/agents/fallback-telemetry.md).
 *
 * Why a structured log rather than a metric: the renderer's PostHog is unreachable
 * from main, and Sentry is for hard errors rather than fail-open degrades. Like the
 * desktop Rust backend, this emits one fixed-field record that log pipelines can
 * aggregate on. Call sites must route through this helper — do not invent ad-hoc warn
 * strings or a new `*_fallback_total` counter for a new fallback (#10240).
 *
 * Silent UX healing is allowed; silent ops is not.
 */

/** Closed outcome set matching the cross-platform contract. */
export type FallbackOutcome = 'recovered' | 'degraded' | 'exhausted'

/**
 * Closed component set. Unknown values bucket to `other` so a typo can never open a
 * new unbounded label. Add a component here when a new main-process call site needs
 * one — that keeps the vocabulary in a single reviewable place.
 */
const ALLOWED_COMPONENTS = ['ai_profile', 'ptt_audio_mute', 'rewind_embedding', 'other'] as const

/** Closed reason set, mirroring the shared bounded vocabulary. */
const ALLOWED_REASONS = [
  'timeout',
  'provider_5xx',
  'provider_429',
  'enqueue_failed',
  'config_incomplete',
  'circuit_open',
  'capability_mismatch',
  'auth',
  'quota',
  'local_heal',
  'policy',
  'byok',
  // Main-process call sites in this app; keep the vocabulary bounded but do not force
  // real diagnostics through `other`, which would erase why the degrade happened.
  'source_fetch_failed',
  'backend_sync_failed',
  'other',
  'none'
] as const

export type FallbackComponent = (typeof ALLOWED_COMPONENTS)[number]
export type FallbackReason = (typeof ALLOWED_REASONS)[number]

/** Trim + lowercase, falling back to `fallbackValue` when empty. */
function safeLabel(value: string | undefined, fallbackValue: string): string {
  const trimmed = (value ?? '').trim().toLowerCase()
  return trimmed.length > 0 ? trimmed : fallbackValue
}

function bucket(
  value: string | undefined,
  allowed: readonly string[],
  fallbackValue: string
): string {
  const label = safeLabel(value, fallbackValue)
  return allowed.includes(label) ? label : fallbackValue
}

export function bucketComponent(component: string | undefined): string {
  return bucket(component, ALLOWED_COMPONENTS, 'other')
}

export function bucketReason(reason: string | undefined): string {
  return bucket(reason, ALLOWED_REASONS, 'other')
}

export type FallbackEvent = {
  /** Subsystem taking the fallback. Unknown values bucket to `other`. */
  component: string
  /** Mode/provider left behind. Omit when there is no meaningful prior mode. */
  from?: string
  /** Mode/provider continued with. Omit when the path simply degrades in place. */
  to?: string
  /** Bounded reason. Unknown values bucket to `other`. */
  reason: string
  /** `recovered` (UX fully restored) | `degraded` (continues with a hit) | `exhausted` (no path left). */
  outcome: FallbackOutcome
  /** Optional bounded context. Keep it small — this is ops signal, not a debug dump. */
  detail?: Record<string, unknown>
}

/**
 * Record a fallback / resilience transition. Never throws: telemetry must not be able
 * to break the fail-open path it is reporting on.
 */
export function recordFallback(event: FallbackEvent): void {
  try {
    const record: Record<string, unknown> = {
      event: 'fallback',
      component: bucketComponent(event.component),
      from: safeLabel(event.from, 'none'),
      to: safeLabel(event.to, 'none'),
      reason: bucketReason(event.reason),
      outcome: event.outcome
    }
    if (event.detail && Object.keys(event.detail).length > 0) record.detail = event.detail
    console.warn('omi_fallback_event', record)
  } catch {
    // Never let telemetry break the caller's fallback path.
  }
}
