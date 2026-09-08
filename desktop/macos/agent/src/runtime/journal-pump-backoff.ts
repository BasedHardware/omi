/**
 * Backoff schedule for the journal outbox pump timer.
 *
 * The pump drains durable outbox rows on a timer. If a row is poisoned (its
 * canonical hash diverges, a referenced journal row is missing, or any other
 * `require*` throws), the drain throws and the pump makes no progress. A fixed
 * 1s interval turns that into a hot loop that re-throws every second forever and
 * survives restarts — the class of bug that wedged chat mid-stream. Backing the
 * timer off on consecutive failures caps the blast radius of *any* such poison
 * to at most one attempt (and one log line) per minute, while a single clean
 * pump snaps the cadence straight back to base.
 */

/** Base cadence for a healthy pump. */
export const JOURNAL_PUMP_BASE_INTERVAL_MS = 1_000;

/** Upper bound on the pump interval while it keeps failing. */
export const JOURNAL_PUMP_MAX_INTERVAL_MS = 60_000;

/** Cap the doubling so the interval saturates at {@link JOURNAL_PUMP_MAX_INTERVAL_MS}. */
const MAX_BACKOFF_EXPONENT = 6;

/**
 * Next pump delay given the count of consecutive failed pump ticks. A streak of
 * 0 (healthy, or recovered) runs at the base cadence; each additional
 * consecutive failure doubles the delay up to the cap.
 */
export function nextJournalPumpDelayMs(failureStreak: number): number {
  if (!Number.isFinite(failureStreak) || failureStreak <= 0) {
    return JOURNAL_PUMP_BASE_INTERVAL_MS;
  }
  const exponent = Math.min(Math.floor(failureStreak) - 1, MAX_BACKOFF_EXPONENT);
  return Math.min(JOURNAL_PUMP_MAX_INTERVAL_MS, JOURNAL_PUMP_BASE_INTERVAL_MS * 2 ** exponent);
}
