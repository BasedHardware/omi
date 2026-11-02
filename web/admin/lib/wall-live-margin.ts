/** The live splice for the Omi TV margin (David 2026-11-02).
 *
 * Settled days (`allInCost`, billing truth) cover every day up to the D-2
 * cutoff. Live days (D-1 and today) come from the producer's metered document
 * (`wall-live.ts`) and the trailing-7-day settled mean for every line the
 * producer does not meter. `spliceCostDays` gives each UTC day to exactly one
 * source and throws if a day would be counted twice.
 */
import type { CostDay, VariableMarginPoint } from "./wall-cost";
import { variableMarginSeries, VARIABLE_MARGIN_RUN_DAYS } from "./wall-cost";
import RATES from "./omi-tv-live-rates.json";
import {
  isWeekendDay,
  LIVE_MIN_FRACTION,
  LiveDay,
  LiveDoc,
  liveDates,
  DAY_MS,
} from "./wall-live";

/** A partial day is used only while its producer run is this fresh. */
export const LIVE_STALE_MS = 20 * 60_000;

/** Element-wise mean of the given settled days (the trailing window). Numeric
 * fields average over the days that carry a number; a field null on every day
 * stays null; booleans and strings keep the last day's value. */
export function trailingMean(days: CostDay[]): CostDay | null {
  if (days.length === 0) return null;
  const last = days[days.length - 1] as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { ...last };
  for (const key of Object.keys(last)) {
    const vals = days.map(
      (d) => (d as unknown as Record<string, unknown>)[key]
    );
    const nums = vals.filter((v): v is number => typeof v === "number");
    if (nums.length && vals.every((v) => v == null || typeof v === "number"))
      out[key] = nums.reduce((s, v) => s + v, 0) / nums.length;
  }
  return out as unknown as CostDay;
}

/** One live UTC day as a cost day. Metered lines are scaled from the covered
 * window to a full day; the other GCP lines are calibration constants; the
 * Soniox line is the measured 7-day rate; everything else is the base mean. */
export function liveCostDay(
  live: LiveDay,
  base: CostDay,
  sonioxRate: number | null
): CostDay {
  const weekend = isWeekendDay(live.date);
  const scale = 1 / live.fraction;
  const m = live.metered;
  const gcpMetered = (m.cloudRun + m.firestore + m.gcs + m.logging) * scale;
  const gke = weekend ? RATES.gkePoolsDay.weekend : RATES.gkePoolsDay.weekday;
  const carry = weekend ? RATES.carryDay.weekend : RATES.carryDay.weekday;
  const gcp = gcpMetered + gke + carry;
  const vertexReserved = RATES.vertexReservedDay;
  const vertexLlm = vertexReserved + RATES.vertexPaygoDay;
  const soniox = sonioxRate ?? base.sttSonioxUsd;
  const stt = base.stt - base.sttSonioxUsd + soniox;
  const anthropic = Math.max(0, base.anthropic ?? 0);
  const total =
    gcp +
    vertexLlm +
    (base.openai ?? 0) +
    anthropic +
    stt +
    base.saas +
    base.infra +
    (base.fees ?? 0);
  return {
    ...base,
    date: live.date,
    gcp,
    vertexLlm,
    vertexReserved,
    gcpDev: 0,
    oneTime: 0,
    anthropic: base.anthropic,
    stt,
    sttSonioxUsd: soniox,
    sttSonioxMeasured: false,
    sttMeasured: false,
    sttFlag: null,
    sttModulateModelled: false,
    saasMeasured: false,
    infraMeasured: false,
    total,
  };
}

/** The live days the margin may use right now: yesterday (closed) and today
 * (partial, from LIVE_MIN_FRACTION of the day, and only while its producer run
 * is fresh). A stale or missing producer value is simply absent. */
export function liveCostDays(
  doc: LiveDoc | null,
  base: CostDay | null,
  now: number,
  sonioxRate: number | null
): CostDay[] {
  if (!doc || !base) return [];
  const out: CostDay[] = [];
  for (const date of liveDates(now)) {
    const day = doc.days[date];
    if (!day) continue;
    const closed = day.fraction >= 1;
    if (!closed) {
      if (day.fraction < LIVE_MIN_FRACTION) continue;
      if (now - Date.parse(day.producedAt) > LIVE_STALE_MS) continue;
    }
    out.push(liveCostDay(day, base, sonioxRate));
  }
  return out;
}

/** Settled days up to `cutoff`, live days after it, each day exactly once.
 * Settled days after the cutoff and live days on or before it are dropped
 * (the settled value wins). Throws if a single side carries a day twice. */
export function spliceCostDays(
  settled: CostDay[],
  live: CostDay[],
  cutoff: string
): CostDay[] {
  const out = [
    ...settled.filter((d) => d.date <= cutoff),
    ...live.filter((d) => d.date > cutoff),
  ].sort((a, b) => a.date.localeCompare(b.date));
  const seen = new Set<string>();
  for (const d of out) {
    if (seen.has(d.date))
      throw new Error(`cost day ${d.date} would be counted twice`);
    seen.add(d.date);
  }
  return out;
}

export interface LiveReconciliation {
  /** Settled cutoff day the comparison ends on (D-2). */
  through: string;
  /** Settled margin of the trailing window ending there. */
  settledPct: number | null;
  /** Live-estimated margin of the same window (stored live days). */
  livePct: number | null;
  /** livePct − settledPct, in points. null when either side is unavailable. */
  variancePp: number | null;
}

/** At D+2 the cutoff day is settled: compare the stored live days of the
 * trailing window with the settled values for the same days. A window with any
 * missing live day has no variance (never a partial comparison). */
export function reconcileLive(
  settled: CostDay[],
  doc: LiveDoc | null,
  cutoff: string,
  sonioxRate: number | null,
  mrrFor: (day: string) => number | null
): LiveReconciliation {
  const window = settled.filter((d) => d.date <= cutoff);
  const base = trailingMean(window.slice(-VARIABLE_MARGIN_RUN_DAYS));
  const settledPoint = variableMarginSeries(window, mrrFor, {}).find(
    (p) => p.date === cutoff
  );
  const settledPct = settledPoint?.marginPct ?? null;
  const days: CostDay[] = [];
  for (let k = VARIABLE_MARGIN_RUN_DAYS - 1; k >= 0; k--) {
    const date = new Date(Date.parse(`${cutoff}T00:00:00Z`) - k * DAY_MS)
      .toISOString()
      .slice(0, 10);
    const stored = doc?.days[date];
    if (!stored || !base || stored.fraction < 1)
      return {
        through: cutoff,
        settledPct,
        livePct: null,
        variancePp: null,
      };
    days.push(liveCostDay(stored, base, sonioxRate));
  }
  const livePoint: VariableMarginPoint | undefined = variableMarginSeries(
    days,
    mrrFor,
    {}
  ).at(-1);
  const livePct = livePoint?.marginPct ?? null;
  return {
    through: cutoff,
    settledPct,
    livePct,
    variancePp:
      livePct != null && settledPct != null ? livePct - settledPct : null,
  };
}
