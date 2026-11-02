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

/** Trailing-window basis for the settled days. Every numeric field is the SUM
 * over the window divided by the window's day count, a null day counting as
 * zero. A cash posting (a $399 Modulate top-up on one day) therefore becomes
 * its share of the window, about $57/day over seven days, not $399/day
 * (review r1). A field null on every day stays null; booleans and strings keep
 * the last day's value. */
export function trailingMean(days: CostDay[]): CostDay | null {
  if (days.length === 0) return null;
  const last = days[days.length - 1] as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { ...last };
  for (const key of Object.keys(last)) {
    const vals = days.map(
      (d) => (d as unknown as Record<string, unknown>)[key]
    );
    if (vals.every((v) => v == null || typeof v === "number"))
      out[key] =
        vals.reduce<number>((s, v) => s + (typeof v === "number" ? v : 0), 0) /
        days.length;
  }
  return out as unknown as CostDay;
}

/** The producer's document state for each live UTC day (today and yesterday):
 * fresh, early (a partial day before LIVE_MIN_FRACTION), missing, or stale
 * (the producer's last run is older than LIVE_STALE_MS, so every day is). */
export type LiveState = "fresh" | "early" | "missing" | "stale";
export function liveDayStates(
  doc: LiveDoc | null,
  now: number
): { date: string; state: LiveState; estimated: string[] }[] {
  const runFresh = liveRunFresh(doc, now);
  return liveDates(now).map((date) => {
    const day = doc?.days[date];
    const estimated = day?.estimated ?? [];
    if (!runFresh) return { date, state: "stale", estimated };
    if (!day) return { date, state: "missing", estimated };
    if (day.fraction < 1 && day.fraction < LIVE_MIN_FRACTION)
      return { date, state: "early", estimated };
    // A partial day whose own value is old (the run skipped it) is stale.
    if (day.fraction < 1 && now - Date.parse(day.producedAt) > LIVE_STALE_MS)
      return { date, state: "stale", estimated };
    return { date, state: "fresh", estimated };
  });
}

/** The producer's last run is recent enough to trust its values. */
export function liveRunFresh(doc: LiveDoc | null, now: number): boolean {
  if (!doc?.runAt) return false;
  return now - Date.parse(doc.runAt) <= LIVE_STALE_MS;
}

/** One live UTC day as a cost day. Metered lines are scaled from the covered
 * window to a full day; the other GCP lines are calibration constants; the
 * Soniox line is the measured 7-day rate; the dev project is metered nowhere,
 * so its trailing settled rate rides in the gcp total and is removed again by
 * the margin (dev stays out of margin and shows on its own line). Everything
 * else is the trailing base. */
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
  const dev = Math.max(0, base.gcpDev ?? 0);
  const gcp = gcpMetered + gke + carry + dev;
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
    gcpDev: dev,
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

/** The live days the margin may use: those in the document after the settled
 * end (`settledEnd`, default: yesterday and today only) and up to today. A
 * closed day is used while the producer run is fresh; a partial day also needs
 * LIVE_MIN_FRACTION of data and its own fresh value. A dead producer makes every
 * live day absent (its state is named by `liveDayStates`), never a silent $0. */
export function liveCostDays(
  doc: LiveDoc | null,
  base: CostDay | null,
  now: number,
  sonioxRate: number | null,
  settledEnd?: string
): CostDay[] {
  if (!doc || !base || !liveRunFresh(doc, now)) return [];
  const [yesterday, today] = liveDates(now);
  // Default lower bound: D-2, so only yesterday and today are read.
  const lower =
    settledEnd ??
    new Date(Date.parse(`${yesterday}T00:00:00Z`) - DAY_MS)
      .toISOString()
      .slice(0, 10);
  const dates = Object.keys(doc.days)
    .filter((d) => d <= today && d > lower)
    .sort();
  const out: CostDay[] = [];
  for (const date of dates) {
    const day = doc.days[date];
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
