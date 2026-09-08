const DAY_MS = 86_400_000

// Apps not foregrounded within the retention window are pruned from app_usage.
// macOS keeps no usage history at all; we keep a bounded, user-selectable window
// so the table can't grow unbounded and stale apps stop influencing the ranking.
// Because total_seconds is cumulative and never decays, this window is the
// feature's only recency control — hence it's exposed in Settings.
export const DEFAULT_RETENTION_DAYS = 45
export const MIN_RETENTION_DAYS = 7
export const MAX_RETENTION_DAYS = 365

// Presets surfaced in the Settings dropdown. Any value persists (clamped), these
// are just the convenient choices.
export const RETENTION_PRESETS: readonly number[] = [30, 45, 60, 90, 180]

// Timestamp (ms epoch) before which app_usage rows are considered stale. A row
// whose last_used is < this should be pruned.
export function usageCutoff(now: number, retentionDays = DEFAULT_RETENTION_DAYS): number {
  return now - retentionDays * DAY_MS
}

// Coerce an arbitrary persisted/UI value into a valid retention window: rounds to
// whole days, clamps to [MIN, MAX], and falls back to the default for anything
// non-numeric. Single source of truth for both the settings store and the prune.
export function normalizeRetentionDays(value: unknown): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) return DEFAULT_RETENTION_DAYS
  const r = Math.round(value)
  if (r < MIN_RETENTION_DAYS) return MIN_RETENTION_DAYS
  if (r > MAX_RETENTION_DAYS) return MAX_RETENTION_DAYS
  return r
}
