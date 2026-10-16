/** Omi TV v3 chart series. Same definitions as the v2 snapshot (`wall-metrics`):
 * the snapshot's own complete periods are reused verbatim and win on every date
 * they cover, so each chart's latest point is the stat above it. Only older
 * periods and chart-only shapes are queried here, one bounded HogQL period at a
 * time on a single serial lane, memoized per UTC day by SQL text. Process-local
 * and disposable like the wall cache; no durable writes.
 */
import {
  completeWeek,
  DEFINITION_VERSION,
  isoDay,
  shiftDay,
  utcDay,
} from "./qualified-activity";
import {
  AggregateRows,
  CAPTURE_SEGMENTS,
  captureSourceQuery,
  CHURNED_ROW,
  cohortQuery,
  DAYS_ROW_PREFIX,
  establishedQuery,
  mauOffsetsQuery,
  periodQueries,
  Query,
  queryPosthog,
  retentionCurveQuery,
  weeklyGrowthQuery,
} from "./wall-posthog";
import { aggregatePeriod, Metric, MetricId, WallPayload } from "./wall-metrics";
import { fetchShopifyWeek } from "./wall-shopify";
import { fetchFinopsHistory, FinopsHistory } from "./wall-finops";
import { wallFailure } from "./wall-source-error";
import { wallRefreshSettled } from "./wall-cache";
import { allInCost } from "./wall-cost";

export const SERIES_NAMES = [
  "headline",
  "growth",
  "activation",
  "retention",
  "revenue",
  "health",
] as const;
export type SeriesName = (typeof SERIES_NAMES)[number];
export type Row = Record<string, number | string | null>;
export interface SeriesPayload {
  name: SeriesName;
  definitionVersion: string;
  generatedAt: string;
  partial: boolean;
  refreshing: boolean;
  cacheStale: boolean;
  frames: Record<string, Row[]>;
  /** Frame or leg → controlled reason it is incomplete or unavailable. */
  gaps: Record<string, string>;
}

export const GROWTH_WEEKS = 26;
export const COHORT_WEEKS = 12;
export const CURVE_COHORTS = 9;
export const MONEY_WEEKS = 8;
/** Mobile allowlisted events (Memory Created, tab/list clicks, mic starts) begin
 * the week of 2026-05-04 in PostHog; earlier periods undercount mobile, so the
 * growth series starts at the first fully instrumented period. */
export const QUALIFIED_TELEMETRY_START = "2026-05-04";
const SNAPSHOT_PERIODS = 6;
const COLD_WAIT = 5_000;
const PARTIAL_RETRY = 2 * 60_000;
const FAILURE_RETRY = 60_000;
const MAX_BACKOFF = 30 * 60_000;
const MAX_STALE = 24 * 60 * 60_000;
const DAYS_PER_MONTH = 365.25 / 12;
/** 60% blended margin goal: cost may be at most 40% of revenue per MAU. */
export const MARGIN_GOAL = 0.6;
export const PLAN_KEYS = [
  "unlimited",
  "unlimited_v2",
  "operator",
  "plus",
  "architect",
  "other",
] as const;

type Billing = {
  daily: {
    date: string;
    total: number;
    components?: Record<string, unknown>;
  }[];
  summary: {
    costSource?: string;
    coverage?: { openai?: boolean; anthropic?: boolean };
  };
} | null;
export interface SeriesSources {
  query: Query;
  shopify: typeof fetchShopifyWeek;
  billing: () => Promise<Billing>;
  finops: (today: string) => Promise<FinopsHistory>;
}
export const defaultSeriesSources: SeriesSources = {
  query: queryPosthog,
  shopify: fetchShopifyWeek,
  billing: async () => {
    const { computeBillingInfraCosts } = await import(
      "@/app/api/omi/stats/infra-costs/route"
    );
    return computeBillingInfraCosts(90, 0, true);
  },
  finops: fetchFinopsHistory,
};

/** Leg results. Each leg is complete, partial (some periods failed) or failed. */
export interface Legs {
  growth?: AggregateRows;
  activationHistory?: AggregateRows;
  captureSource?: AggregateRows;
  retainedHistory?: AggregateRows;
  establishedHistory?: AggregateRows;
  curve?: AggregateRows;
  mau?: Record<number, number>;
  finops?: FinopsHistory;
  billing?: Billing;
  shopify?: {
    date: string;
    units: number;
    hardwareUsd: number;
    prepayUsd: number;
  }[];
}
type LegName = keyof Legs;
const LEGS_FOR: Record<SeriesName, LegName[]> = {
  headline: ["finops", "mau", "billing"],
  growth: ["growth"],
  activation: ["activationHistory", "captureSource"],
  retention: ["curve", "retainedHistory", "establishedHistory", "growth"],
  revenue: ["finops", "mau", "shopify"],
  health: ["billing", "finops", "mau"],
};

/** Shift period numbers of a chunk read at an older end date. */
function offsetRows(rows: AggregateRows, offset: number): AggregateRows {
  return Object.assign(
    rows.map((r) => [Number(r[0]) + offset, ...r.slice(1)]),
    { sourceRefreshedAt: rows.sourceRefreshedAt ?? null }
  );
}

class PartialLeg extends Error {
  constructor(readonly value: unknown, readonly reason: string) {
    super(reason);
  }
}

/** Run period reads newest-first; keep what succeeded and report the rest. */
async function periods(
  count: number,
  read: (period: number) => Promise<AggregateRows>,
  first = 0
): Promise<AggregateRows> {
  const rows: unknown[][] = [];
  let failure: string | null = null;
  let streak = 0;
  // Two consecutive failures mean the source is saturated: stop, keep what
  // succeeded, and let the leg's backoff decide when to try again.
  for (let period = first; period < count && streak < 2; period++) {
    try {
      rows.push(...offsetRows(await read(period), period));
      streak = 0;
    } catch (error) {
      failure ||= wallFailure("PostHog", error);
      streak++;
    }
  }
  const result = Object.assign(rows, { sourceRefreshedAt: null });
  if (failure) throw new PartialLeg(result, failure);
  return result;
}

export function legJobs(
  sources: SeriesSources,
  now: Date
): Record<LegName, () => Promise<unknown>> {
  const end = utcDay(now);
  const back = (weeks: number) => shiftDay(end, -7 * weeks);
  // Snapshot periods 0–5 come from the wall payload; read only 6–11.
  const history = (build: (stop: Date, n: number) => string, stop: Date) =>
    periodQueries(
      sources.query,
      build,
      shiftDay(stop, -7 * SNAPSHOT_PERIODS),
      7,
      COHORT_WEEKS - SNAPSHOT_PERIODS
    ).then((rows) => offsetRows(rows, SNAPSHOT_PERIODS));
  return {
    growth: () =>
      periods(GROWTH_WEEKS, (p) =>
        sources.query(weeklyGrowthQuery(back(p), 1))
      ),
    activationHistory: () => history((stop, n) => cohortQuery(stop, 7, n), end),
    captureSource: () => sources.query(captureSourceQuery(end)),
    retainedHistory: () => history((stop, n) => cohortQuery(stop, 37, n), end),
    establishedHistory: () => history(establishedQuery, completeWeek(now).end),
    // One cohort per read; partial cohorts are kept and only the missing retried.
    curve: () =>
      periods(CURVE_COHORTS, (p) =>
        sources.query(retentionCurveQuery(shiftDay(end, -7 * (p + 1)), 1, end))
      ),
    mau: async () => {
      // Week 0 is the snapshot's own MAU; read 30-day windows at the earlier
      // week ends (ARPMAU) and one day earlier (cost/MAU, settled D−2).
      const out: Record<number, number> = {};
      let failure: string | null = null;
      for (let week = 1; week < MONEY_WEEKS; week++) {
        try {
          const rows = await sources.query(mauOffsetsQuery(back(week), [0, 1]));
          for (const r of rows) out[7 * week + Number(r[0])] = Number(r[1]);
        } catch (error) {
          failure ||= wallFailure("PostHog", error);
        }
      }
      if (failure) throw new PartialLeg(out, failure);
      return out;
    },
    finops: () => sources.finops(isoDay(now)),
    billing: async () => {
      const bill = await sources.billing();
      if (!bill || bill.summary.costSource !== "billing")
        throw new Error("Settled billing aggregate unavailable");
      return bill;
    },
    shopify: async () => {
      const weeks: NonNullable<Legs["shopify"]> = [];
      let failure: string | null = null;
      for (let k = MONEY_WEEKS - 1; k >= 0; k--) {
        const week = completeWeek(now, k);
        try {
          const v = await sources.shopify(isoDay(week.start), isoDay(week.end));
          weeks.push({
            date: isoDay(shiftDay(week.end, -1)),
            units: v.units,
            hardwareUsd: v.hardwareUsd,
            prepayUsd: v.prepayUsd,
          });
        } catch (error) {
          failure ||= wallFailure("Shopify", error);
        }
      }
      if (failure) throw new PartialLeg(weeks, failure);
      return weeks;
    },
  };
}

// ---------------------------------------------------------------- assembly

const round = (v: number | null, digits = 2) =>
  v == null || !Number.isFinite(v)
    ? null
    : Math.round(v * 10 ** digits) / 10 ** digits;
const ts = (day: string) => `${day}T00:00:00Z`;
function metric(snapshot: WallPayload | null, id: MetricId): Metric | null {
  return snapshot?.metrics.find((m) => m.id === id) ?? null;
}
const usable = (m: Metric | null) =>
  m != null && m.value != null && !m.fixture ? m : null;

/** Series points by date, oldest first; snapshot trend points win. */
function mergeSnapshot(
  points: Map<string, Row>,
  m: Metric | null,
  project: (point: Metric["trend"][number]) => Row
) {
  for (const point of m?.trend || [])
    if (point.value != null) points.set(point.date, project(point));
  return Array.from(points.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, row]) => ({ date: ts(date), ...row }));
}

function cohortRow(
  value: number | null,
  split: Metric["split"] | undefined,
  n: number | null | undefined
): Row {
  return {
    total: value,
    macos: split?.macos ?? null,
    mobile: split?.mobile ?? null,
    other: split?.other ?? null,
    n: n ?? null,
  };
}

function cohortSeries(
  history: AggregateRows | undefined,
  m: Metric | null,
  stop: Date,
  numeratorIndex: number,
  denominatorIndex: number
) {
  const points = new Map<string, Row>();
  for (let p = SNAPSHOT_PERIODS; p < COHORT_WEEKS; p++) {
    if (!history) break;
    const a = aggregatePeriod(history, p, numeratorIndex, denominatorIndex);
    if (a.observed)
      points.set(
        isoDay(shiftDay(stop, -7 * p - 1)),
        cohortRow(a.value, a.split, a.den)
      );
  }
  return mergeSnapshot(points, m, (t) =>
    cohortRow(t.value, t.split, t.denominator)
  );
}

export function growthFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const end = utcDay(now);
  const rows = legs.growth || [];
  const points = new Map<string, Row>();
  const integrationsSeen = rows
    .filter((r) => r[1] === "integrations")
    .map((r) => Number(r[0]));
  const oldestMcp = integrationsSeen.length
    ? Math.max(...integrationsSeen)
    : -1;
  const lcurve: Record<number, Record<string, number>> = {};
  for (let p = GROWTH_WEEKS - 1; p >= 0; p--) {
    const people = rows.filter(
      (r) => Number(r[0]) === p && !String(r[1]).startsWith("__")
    );
    if (!people.length) continue;
    if (isoDay(shiftDay(end, -7 * (p + 1))) < QUALIFIED_TELEMETRY_START)
      continue;
    // Marker history: before the first observed MCP-only week, MCP is unknown.
    const a = aggregatePeriod(people, p, 2, undefined, true, p <= oldestMcp);
    const total = a.num;
    const sum = (i: number) => people.reduce((s, r) => s + Number(r[i]), 0);
    const retained = sum(4),
      fresh = sum(5);
    const resurrected = total - retained - fresh;
    const churned = Number(
      rows.find((r) => Number(r[0]) === p && r[1] === CHURNED_ROW)?.[2] ?? 0
    );
    lcurve[p] = {};
    for (const r of rows)
      if (Number(r[0]) === p && String(r[1]).startsWith(DAYS_ROW_PREFIX))
        lcurve[p][String(r[1]).slice(DAYS_ROW_PREFIX.length)] = Number(r[2]);
    points.set(isoDay(shiftDay(end, -7 * p - 1)), {
      total,
      macos: a.split.macos,
      mobile: a.split.mobile,
      other: a.split.other,
      mcp: a.split.mcp ?? null,
      new: fresh,
      resurrected,
      retained,
      churned: -churned,
      quickRatio: churned ? round((fresh + resurrected) / churned) : null,
      stickiness: total ? round((100 * sum(3)) / (7 * total), 1) : null,
    });
  }
  const wau = metric(snapshot, "growth.wau");
  const weekly = mergeSnapshot(points, wau, (t) => ({
    ...(points.get(t.date) || {}),
    total: t.value,
    macos: t.split?.macos ?? null,
    mobile: t.split?.mobile ?? null,
    other: t.split?.other ?? null,
    mcp: t.split?.mcp ?? null,
  }));
  const share = (p: number, d: number) => {
    const all = Object.values(lcurve[p] || {}).reduce((s, n) => s + n, 0);
    return all && lcurve[p]?.[d] != null
      ? round((100 * lcurve[p][d]) / all, 1)
      : null;
  };
  const power = lcurve[0]
    ? Array.from({ length: 7 }, (_, i) => ({
        days: `${i + 1}d`,
        "This week": share(0, i + 1),
        "4 weeks earlier": share(4, i + 1),
      }))
    : [];
  return { weekly, power };
}

export function activationFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const stop = shiftDay(utcDay(now), -7);
  const rate = metric(snapshot, "activation.rate");
  const capture = metric(snapshot, "activation.capture_week1_share");
  const activation = cohortSeries(legs.activationHistory, rate, stop, 3, 2);
  const captured = cohortSeries(legs.activationHistory, capture, stop, 8, 2);
  // Activation by first-week capture source for the latest matured cohort
  // (the stat's cohort); people ride in the label, segments in a fixed order.
  const counts = new Map(
    (legs.captureSource || []).map((r) => [
      String(r[0]),
      [Number(r[1]), Number(r[2])],
    ])
  );
  const sources = CAPTURE_SEGMENTS.filter(
    (name) => (counts.get(name)?.[0] ?? 0) > 0
  ).map((name) => {
    const [people, activated] = counts.get(name)!;
    return {
      source: `${name} · ${people.toLocaleString("en-US")}`,
      activation: (100 * activated) / people,
      people,
    };
  });
  return { activation, capture: captured, sources };
}

export function retentionFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const end = utcDay(now);
  const cohortEnd = shiftDay(end, -7);
  const curveRows = legs.curve || [];
  const labels: string[] = [];
  const byCohort = new Map<number, Record<number, number | null>>();
  for (const r of curveRows) {
    const [p, k, observed, active] = r.map(Number);
    if (!byCohort.has(p)) byCohort.set(p, {});
    byCohort.get(p)![k] = observed ? round((100 * active) / observed, 1) : null;
  }
  const cohorts = Array.from(byCohort.keys()).sort((a, b) => b - a);
  for (const p of cohorts)
    labels.push(
      new Date(shiftDay(cohortEnd, -7 * (p + 1))).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      })
    );
  // Always nine week rows, so the x field exists even before cohorts load.
  const curve = Array.from({ length: 9 }, (_, k) => {
    const row: Row = { week: k };
    cohorts.forEach((p, i) => (row[labels[i]] = byCohort.get(p)?.[k] ?? null));
    return row;
  });
  const established = cohortSeries(
    legs.establishedHistory,
    metric(snapshot, "retention.established_week"),
    completeWeek(now).end,
    3,
    2
  );
  const retained = cohortSeries(
    legs.retainedHistory,
    metric(snapshot, "retention.if_activated"),
    shiftDay(end, -37),
    4,
    3
  );
  return {
    curve,
    established,
    retained,
    power: growthFrames(legs, snapshot, now).power,
  };
}

function mrrTotal(day: Record<string, number> | undefined) {
  return day ? Object.values(day).reduce((s, v) => s + v, 0) : null;
}
/** FinOps book at or just before a day (snapshots are daily, may lag a day). */
function finopsMrr(f: FinopsHistory | undefined, day: Date) {
  for (const back of [0, 1]) {
    const v = mrrTotal(f?.mrr[isoDay(shiftDay(day, -back))]);
    if (v != null) return v;
  }
  return null;
}

export function revenueFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const end = utcDay(now);
  const live = usable(metric(snapshot, "revenue.mrr"));
  const mrrPoints = new Map<string, Row>();
  for (const [day, plans] of Object.entries(legs.finops?.mrr || {})) {
    const row: Row = { source: "FinOps book" };
    for (const k of PLAN_KEYS) row[k] = round(plans[k] ?? 0, 0);
    row.total = round(mrrTotal(plans), 0);
    mrrPoints.set(day, row);
  }
  if (live) {
    const row: Row = { source: "Live Stripe book" };
    for (const k of PLAN_KEYS) row[k] = live.breakdown?.[k] ?? 0;
    row.total = live.value;
    mrrPoints.set(isoDay(now), row);
  }
  const mrr: Row[] = Array.from(mrrPoints.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, row]) => ({ date: ts(date), ...row }));

  const mauNow = usable(metric(snapshot, "engagement.mau"));
  const arpLive = usable(metric(snapshot, "revenue.arpmau"));
  const arpmau: Row[] = [];
  for (let k = MONEY_WEEKS - 1; k >= 0; k--) {
    const mau = k === 0 ? mauNow?.value ?? null : legs.mau?.[7 * k] ?? null;
    const book = finopsMrr(legs.finops, shiftDay(end, -7 * k));
    const finopsArp = mau && book != null ? book / mau : null;
    const value = k === 0 && arpLive ? arpLive.value : finopsArp;
    if (value == null) continue;
    arpmau.push({
      date: ts(isoDay(shiftDay(end, -7 * k - 1))),
      arpmau: value,
      finopsArpmau: round(finopsArp),
      mau,
    });
  }

  const hw = usable(metric(snapshot, "revenue.hardware_usd_week"));
  const units = usable(metric(snapshot, "revenue.hardware_units_week"));
  const hardware = (legs.shopify || []).map((w) => ({
    date: ts(w.date),
    hardwareUsd:
      hw && hw.trend.at(-1)?.date === w.date
        ? hw.value
        : round(w.hardwareUsd, 0),
    units: units && units.trend.at(-1)?.date === w.date ? units.value : w.units,
    prepayUsd: round(w.prepayUsd, 0),
  }));
  return { mrr, arpmau, hardware };
}

export function healthFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const end = utcDay(now);
  const cutoff = isoDay(shiftDay(end, -2));
  // Same all-in model as the snapshot's cost stats (every cost line counted).
  const allIn = allInCost(
    (legs.billing?.daily || []).filter((d) => d.date <= cutoff),
    legs.finops?.stt ?? null,
    legs.billing?.summary.coverage
  );
  const days = allIn.daily;
  const net = metric(snapshot, "cost.net_day");
  const snapshotTotals = new Map(
    (net?.trend || []).map((t) => [t.date, t.value])
  );
  const cost = days.slice(-60).map((d) => {
    const book = finopsMrr(legs.finops, shiftDay(new Date(ts(d.date)), 1));
    return {
      date: ts(d.date),
      gcp: d.gcp,
      vertexLlm: d.vertexLlm,
      openai: d.openai,
      anthropic: d.anthropic,
      stt: d.stt,
      saas: d.saas,
      oneTimeExcluded: d.oneTime || null,
      total: snapshotTotals.get(d.date) ?? d.total,
      revenuePerDay: book == null ? null : book / DAYS_PER_MONTH,
    };
  });
  const byDay = new Map(days.map((d) => [d.date, d.total]));
  const arp = new Map(
    revenueFrames(legs, snapshot, now).arpmau.map((r) => [
      String(r.date).slice(0, 10),
      r.arpmau as number,
    ])
  );
  const live = usable(metric(snapshot, "cost.per_mau_month"));
  const costPerMau: Row[] = [];
  for (let k = MONEY_WEEKS - 1; k >= 0; k--) {
    const windowEnd = shiftDay(end, -1 - 7 * k); // exclusive; D−2 inclusive
    const window = Array.from({ length: 30 }, (_, i) =>
      byDay.get(isoDay(shiftDay(windowEnd, -30 + i)))
    );
    const mau = k === 0 ? live?.denominator ?? null : legs.mau?.[7 * k + 1];
    const settled = window.every((v) => v != null);
    const value =
      k === 0 && live
        ? live.value
        : settled && mau
        ? window.reduce<number>((s, v) => s + (v as number), 0) / mau
        : null;
    if (value == null) continue;
    const arpmau = arp.get(isoDay(shiftDay(end, -7 * k - 1)));
    costPerMau.push({
      date: ts(isoDay(shiftDay(windowEnd, -1))),
      costPerMau: value,
      goal: arpmau == null ? null : round(arpmau * (1 - MARGIN_GOAL)),
    });
  }
  return { cost, costPerMau };
}

const HEADLINE: [string, MetricId][] = [
  ["wau", "growth.wau"],
  ["dau", "engagement.dau"],
  ["mau", "engagement.mau"],
  ["activation", "activation.rate"],
  ["capture", "activation.capture_week1_share"],
  ["retained", "retention.if_activated"],
  ["established", "retention.established_week"],
  ["hardware", "revenue.hardware_usd_week"],
  ["netCost", "cost.net_day"],
];
/** Sourceless wall metrics: one-line TV labels (contract audit 2026-10-15); the
 * route's full classified reason stays in the hidden `reason` column. */
export const COVERAGE_GAPS: [MetricId, string, string][] = [
  ["health.crash_free", "Crash-free (macOS)", "No Sentry read path"],
  ["health.thumbs_positive", "Positive answers", "No ratings aggregate"],
  ["revenue.payer_churn", "Payer churn", "Payer history from Nov"],
  ["revenue.activated_paid_30d", "Activated → paid", "No billing↔person join"],
  ["cost.gross_margin_pct", "Gross margin", "STT/fees not invoiced"],
];
/** Headline keys shown in each column's stat, in order. */
export const DELTA_STRIPS: Record<string, string[]> = {
  growth: ["wau", "dau", "mau"],
  activation: ["activation", "capture"],
  retention: ["retained", "established"],
  revenue: ["mrr", "arpmau", "hardware"],
  health: ["netCost", "costPerMau"],
};
const RATE_KEYS = new Set(["activation", "capture", "retained", "established"]);
const UP_IS_BAD = new Set(["netCost", "costPerMau"]);
/** Invisible tone markers the Grafana strip colors by (regex value mappings). */
export const GOOD_MARK = "\u200b";
export const BAD_MARK = "\u2060";

export function headlineDelta(key: string, rows: Row[]) {
  const unit = RATE_KEYS.has(key) ? "pp" : "%";
  const [prior, current] =
    rows.length === 2 ? rows.map((r) => r.value as number) : [null, null];
  const delta =
    prior == null || current == null
      ? null
      : unit === "pp"
      ? current - prior
      : prior === 0
      ? null
      : (100 * (current - prior)) / Math.abs(prior);
  const shown = delta == null ? null : Math.round(delta * 10) / 10;
  const tone =
    shown == null || shown === 0
      ? null
      : shown > 0 !== UP_IS_BAD.has(key)
      ? "good"
      : "bad";
  const text =
    shown == null
      ? "no prior"
      : `${shown > 0 ? "▲" : shown < 0 ? "▼" : "■"} ${Math.abs(shown).toFixed(
          1
        )}${unit === "pp" ? " pp" : "%"}${
          tone === "good" ? GOOD_MARK : tone === "bad" ? BAD_MARK : ""
        }`;
  return { key, prior, current, delta, unit, tone, text };
}

/** Two-row stat frames: [prior, current]. Grafana's percent change is
 * (last − first) / first, so the prior row sets the comparison. */
export function headlineFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const frames: Record<string, Row[]> = {};
  const pair = (
    prior: { date: string; value: number | null } | undefined,
    current: { date: string; value: number | null }
  ) =>
    current.value == null
      ? []
      : [
          ...(prior?.value != null
            ? [{ date: ts(prior.date), value: prior.value }]
            : []),
          { date: ts(current.date), value: current.value },
        ];
  for (const [key, id] of HEADLINE) {
    const m = metric(snapshot, id);
    const t = m?.trend || [];
    frames[key] =
      m && t.length
        ? pair(t.at(-2), { date: t.at(-1)!.date, value: m.value })
        : [];
  }
  // Money: the live book is the stat; the delta is the same-source FinOps
  // 7-day change, so the known FinOps gaps do not show up as growth.
  const revenue = revenueFrames(legs, snapshot, now);
  const book = revenue.mrr.filter((r) => r.source === "FinOps book");
  const ref = book.at(-1);
  const weekAgo = ref
    ? book.find(
        (r) =>
          String(r.date).slice(0, 10) ===
          isoDay(shiftDay(new Date(String(ref.date)), -7))
      )
    : undefined;
  const lastMrr = revenue.mrr.at(-1);
  frames.mrr = lastMrr
    ? pair(
        weekAgo && ref
          ? {
              date: String(weekAgo.date).slice(0, 10),
              value:
                ((lastMrr.total as number) * (weekAgo.total as number)) /
                (ref.total as number),
            }
          : undefined,
        {
          date: String(lastMrr.date).slice(0, 10),
          value: lastMrr.total as number,
        }
      )
    : [];
  const [arpPrior, arpNow] = revenue.arpmau.slice(-2);
  frames.arpmau = arpNow
    ? pair(
        arpPrior && arpNow.finopsArpmau
          ? {
              date: String(arpPrior.date).slice(0, 10),
              value:
                ((arpNow.arpmau as number) *
                  (arpPrior.finopsArpmau as number)) /
                (arpNow.finopsArpmau as number),
            }
          : undefined,
        {
          date: String(arpNow.date).slice(0, 10),
          value: arpNow.arpmau as number,
        }
      )
    : [];
  const [cpmPrior, cpmNow] = healthFrames(legs, snapshot, now).costPerMau.slice(
    -2
  );
  frames.costPerMau = cpmNow
    ? pair(
        cpmPrior && {
          date: String(cpmPrior.date).slice(0, 10),
          value: cpmPrior.costPerMau as number,
        },
        {
          date: String(cpmNow.date).slice(0, 10),
          value: cpmNow.costPerMau as number,
        }
      )
    : [];
  // Prior-period change per stat: percentage points for rates, relative % for
  // counts and money (David 2026-10-16). Grafana's native percent change is
  // relative only, so the API carries the delta and its text.
  frames.deltas = [];
  for (const [column, keys] of Object.entries(DELTA_STRIPS)) {
    const strip: Row = {};
    for (const key of keys) {
      const d = headlineDelta(key, frames[key] || []);
      frames.deltas.push(d);
      strip[key] = d.text;
    }
    frames[`strip_${column}`] = [strip];
  }
  frames.gaps = COVERAGE_GAPS.flatMap(([id, label, missing]) => {
    const m = metric(snapshot, id);
    return m && m.value == null
      ? [
          {
            metric: label,
            missing,
            reason: (m.reason || "Source missing").split(";")[0],
          },
        ]
      : [];
  });
  return frames;
}

const ASSEMBLE: Record<
  SeriesName,
  (legs: Legs, snapshot: WallPayload | null, now: Date) => Record<string, Row[]>
> = {
  headline: headlineFrames,
  growth: growthFrames,
  activation: activationFrames,
  retention: retentionFrames,
  revenue: revenueFrames,
  health: healthFrames,
};
export function assembleSeries(
  name: SeriesName,
  legs: Legs,
  snapshot: WallPayload | null,
  now = new Date()
) {
  return ASSEMBLE[name](legs, snapshot, now);
}

// ------------------------------------------------------------------- cache

interface LegEntry {
  day: string;
  at: number;
  value?: unknown;
  complete: boolean;
  reason?: string;
  retryAt: number;
  /** Consecutive incomplete refreshes; drives exponential backoff. */
  failures: number;
  flight?: Promise<void>;
}
let legCache = new Map<LegName, LegEntry>();
let memo = new Map<string, { day: string; rows: AggregateRows }>();
let lane: Promise<unknown> = Promise.resolve();

/** One series PostHog read at a time; successes memoized for the UTC day. */
function serialQuery(query: Query, day: string): Query {
  return (sql) => {
    const hit = memo.get(sql);
    if (hit?.day === day) return Promise.resolve(hit.rows);
    // Low priority: the snapshot's own refresh always runs first.
    const run = lane.then(wallRefreshSettled).then(() => query(sql));
    lane = run.catch(() => undefined);
    return run.then((rows) => {
      memo.set(sql, { day, rows });
      return rows;
    });
  };
}

function startLeg(
  name: LegName,
  job: () => Promise<unknown>,
  day: string,
  now: number,
  retain: (work: Promise<unknown>) => void
) {
  const entry = legCache.get(name);
  if (entry?.flight) return entry.flight;
  if ((entry?.day === day && entry.complete) || now < (entry?.retryAt ?? 0))
    return null;
  const previous = entry;
  const flight = job()
    .then(
      (value) => ({ value, complete: true, reason: undefined }),
      (error) =>
        error instanceof PartialLeg
          ? { value: error.value, complete: false, reason: error.reason }
          : {
              value: undefined,
              complete: false,
              reason: wallFailure(name, error),
            }
    )
    .then(({ value, complete, reason }) => {
      // A partial read with nothing in it is a failure, not an empty chart.
      const failed =
        value === undefined ||
        (Array.isArray(value)
          ? value.length === 0
          : typeof value === "object" &&
            value !== null &&
            Object.keys(value).length === 0 &&
            !complete);
      // Stale-good: a failed refresh keeps the last good value (≤24h). Times
      // use the request clock so cache ages and cooldowns follow `now`.
      const keep =
        failed &&
        previous?.value !== undefined &&
        now - previous.at < MAX_STALE;
      legCache.set(name, {
        day: keep ? previous!.day : day,
        at: keep ? previous!.at : now,
        value: keep ? previous!.value : failed ? undefined : value,
        complete: complete && !failed,
        reason,
        failures: complete && !failed ? 0 : (previous?.failures ?? 0) + 1,
        retryAt:
          now +
          Math.min(
            MAX_BACKOFF,
            (failed ? FAILURE_RETRY : PARTIAL_RETRY) *
              2 ** (previous?.failures ?? 0)
          ),
      });
      if (reason)
        console.warn(
          JSON.stringify({
            event: "wall_series_leg_incomplete",
            leg: name,
            reason,
          })
        );
    });
  legCache.set(name, {
    ...(previous || { day, at: 0, complete: false, retryAt: 0, failures: 0 }),
    flight,
  });
  retain(flight);
  return flight;
}

export async function seriesPayload(
  name: SeriesName,
  snapshot: Promise<WallPayload | null>,
  now = new Date(),
  sources: SeriesSources = defaultSeriesSources,
  retain: (work: Promise<unknown>) => void = () => {}
): Promise<SeriesPayload> {
  const day = isoDay(utcDay(now));
  const jobs = legJobs(
    { ...sources, query: serialQuery(sources.query, day) },
    now
  );
  const flights = LEGS_FOR[name]
    .map((leg) => startLeg(leg, jobs[leg], day, now.getTime(), retain))
    .filter(Boolean) as Promise<void>[];
  let timer: ReturnType<typeof setTimeout> | undefined;
  const [wall] = await Promise.all([
    snapshot.catch(() => null),
    flights.length
      ? Promise.race([
          Promise.all(flights),
          new Promise((resolve) => (timer = setTimeout(resolve, COLD_WAIT))),
        ])
      : null,
  ]);
  if (timer) clearTimeout(timer);
  const legs: Legs = {};
  const gaps: Record<string, string> = {};
  let cacheStale = Boolean(wall?.cacheStale);
  for (const leg of LEGS_FOR[name]) {
    const entry = legCache.get(leg);
    if (entry?.value !== undefined)
      (legs as Record<string, unknown>)[leg] = entry.value;
    if (entry?.day !== day && entry?.value !== undefined) cacheStale = true;
    if (!entry || entry.flight) gaps[leg] = "Series refresh running";
    if (entry?.reason) gaps[leg] = entry.reason;
  }
  return {
    name,
    definitionVersion: DEFINITION_VERSION,
    generatedAt: new Date().toISOString(),
    partial: Object.keys(gaps).length > 0,
    refreshing: LEGS_FOR[name].some((leg) => legCache.get(leg)?.flight),
    cacheStale,
    frames: assembleSeries(name, legs, wall, now),
    gaps,
  };
}

export function resetSeriesCache() {
  legCache = new Map();
  memo = new Map();
  lane = Promise.resolve();
}
