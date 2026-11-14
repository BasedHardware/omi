/**
 * Omi TV reader for the settled spend table (`omi_finops.spend_daily`, producer
 * PR1 #24872). Shadow only: nothing here is served on the board until the table
 * is populated and the 2026-11-04 parity check passes (all-in $3,549.21).
 *
 * Row contract (from the Firestore and margin lead, 2026-11-07): one row per
 * (date, line, source, status). `basis_class` is variable, fixed or excluded.
 * A missing row means unavailable, never $0, so callers must check coverage.
 *
 * Two bases, never mixed. `in_all_in` marks the all-in total's rows;
 * `in_margin_basis` marks the rows the margin basis counts. The producer writes
 * mutually exclusive alternatives that are BOTH `basis_class = 'variable'` on
 * the same day — Modulate cash vs modelled, and Stripe actual fees vs the
 * subscription-fee estimate — and only the two flags say which one counts. The
 * variable and listen sums below therefore gate on `in_margin_basis`; summing
 * `basis_class = 'variable'` alone double counts both pairs.
 */

export const SPEND_TABLE = "based-hardware.omi_finops.spend_daily";
export const SPEND_SKU_TABLE = "based-hardware.omi_finops.spend_daily_gcp_sku";
export const PAYING_TABLE = "based-hardware.omi_finops.plan_revenue_daily";

/** Parity anchor from the producer contract: the all-in total on this day. */
export const PARITY_DAY = "2026-11-04";
export const PARITY_ALL_IN_USD = 3549.21;

/** The contract's month factor (same as the margin: 30.44 days). */
export const DAYS_PER_MONTH = 30.44;

/** STT lines: the listen cost for the audio-hour metric. Definition is a
 * proposal until David confirms it in the render review (see PR body). */
export const LISTEN_LINE_PREFIX = "stt_";

/**
 * One day's totals from the settled table. `variableUsd` covers the
 * `basis_class = 'variable'` rows the margin basis counts (`in_margin_basis`),
 * so the cash/modelled and actual/estimated alternatives are never summed
 * together; `listenUsd` covers the STT lines within it; `allInUsd` covers rows
 * flagged `in_all_in`. `rows` is the row count, so a day with no rows is
 * distinguishable from a day that sums to $0.
 */
export interface SpendDay {
  day: string;
  variableUsd: number | null;
  listenUsd: number | null;
  allInUsd: number | null;
  rows: number;
}

/** Raw row shape returned by `spendDailyQuery`. */
export interface SpendDayRow {
  day: string;
  variable_usd: string | number | null;
  listen_usd: string | number | null;
  all_in_usd: string | number | null;
  rows: string | number;
}

/** A real ISO calendar date (YYYY-MM-DD), not just the right shape. */
export function isCalendarDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  const probe = new Date(Date.UTC(y, m - 1, d));
  return (
    probe.getUTCFullYear() === y &&
    probe.getUTCMonth() === m - 1 &&
    probe.getUTCDate() === d
  );
}

/**
 * Daily totals over `days` days ending on `end`. Dedupe first: the producer may
 * write the same (date, line, source, status) across runs, so keep the latest
 * `computed_at` for each key. Only then drop rows whose latest run is unsettled,
 * so an older settled row can never stand in for a newer unsettled one, and
 * drop provisional rows (the producer's parity gate rejects them).
 */
export function spendDailyQuery(end: string, days: number): string {
  // Interpolated into SQL: accept only a real ISO calendar date and a bounded window.
  if (!isCalendarDate(end)) throw new Error("bad end date");
  if (!Number.isInteger(days) || days < 1 || days > 400)
    throw new Error("bad window");
  return `
WITH latest AS (
  SELECT *
  FROM \`${SPEND_TABLE}\`
  WHERE date > DATE_SUB(DATE '${end}', INTERVAL ${days} DAY)
    AND date <= DATE '${end}'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY date, line, source, status ORDER BY computed_at DESC
  ) = 1
)
SELECT
  FORMAT_DATE('%F', date) AS day,
  SUM(IF(basis_class = 'variable' AND in_margin_basis, usd, NULL)) AS variable_usd,
  SUM(IF(basis_class = 'variable' AND in_margin_basis AND STARTS_WITH(line, '${LISTEN_LINE_PREFIX}'), usd, NULL)) AS listen_usd,
  SUM(IF(in_all_in, usd, NULL)) AS all_in_usd,
  COUNT(*) AS rows
FROM latest
WHERE inputs_settled AND status != 'provisional'
GROUP BY day
ORDER BY day`;
}

/** Turn raw rows into typed days. Missing sums stay null, never 0. */
export function spendDays(rows: SpendDayRow[]): SpendDay[] {
  const num = (v: string | number | null) => (v == null ? null : Number(v));
  return rows
    .map((r) => ({
      day: r.day,
      variableUsd: num(r.variable_usd),
      listenUsd: num(r.listen_usd),
      allInUsd: num(r.all_in_usd),
      rows: Number(r.rows),
    }))
    .sort((a, b) => (a.day < b.day ? -1 : a.day > b.day ? 1 : 0));
}

/** Parity: the all-in total for the anchor day against the producer's contract
 * value ($3,549.21). Returns the difference, or null when the anchor day is
 * absent (a gap, not a pass). The producer's own gate allows ±$2 all-in (±$1
 * per component), so the consumer decides the tolerance rather than assuming
 * exact-to-the-cent. */
export function parityDelta(days: SpendDay[]): number | null {
  const anchor = days.find((d) => d.day === PARITY_DAY);
  if (!anchor || anchor.allInUsd == null) return null;
  return Math.round((anchor.allInUsd - PARITY_ALL_IN_USD) * 100) / 100;
}

/** Listen $ per audio-hour over a window: STT variable cost ÷ wire audio hours.
 * Null when either side is missing or the hours are not positive. */
export function listenUsdPerAudioHour(
  listenUsd: number | null,
  audioHours: number | null
): number | null {
  if (listenUsd == null || audioHours == null || audioHours <= 0) return null;
  return listenUsd / audioHours;
}

/** Variable cost per paying user per month: the mean daily variable cost over
 * the covered days × 30.44, ÷ paying users. A day with no variable rows is a
 * gap, not a $0 day, so it is left out of the mean; the figure is only as
 * complete as the covered days (`rows` shows per-day coverage). Null when any
 * input is missing, the window is empty, or there are no paying users. */
export function variableCostPerPayingUserMonth(
  days: SpendDay[],
  payingUsers: number | null
): number | null {
  if (payingUsers == null || payingUsers <= 0) return null;
  const covered = days.filter((d) => d.variableUsd != null);
  if (covered.length === 0) return null;
  const meanDay =
    covered.reduce((sum, d) => sum + (d.variableUsd ?? 0), 0) / covered.length;
  return (meanDay * DAYS_PER_MONTH) / payingUsers;
}
