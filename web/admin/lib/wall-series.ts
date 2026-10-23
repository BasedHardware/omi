import {
  readRollup,
  preferRollup,
  rollupStatus,
  RollupRead,
  RollupStatus,
} from "./wall-rollup";
import { RollupRequest } from "./wall-rollup-sql";
/** Omi TV v3 chart series. Same definitions as the v2 snapshot (`wall-metrics`):
 * the snapshot's own complete periods are reused verbatim and win on every date
 * they cover, so each chart's latest point is the stat above it. Only older
 * periods and chart-only shapes are queried here, one bounded HogQL period at a
 * time on a single serial lane, memoized per UTC day by SQL text. Leg values,
 * reads and leases are shared across instances (`wall-series-store`); the only
 * durable writes are those aggregate cache docs.
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
import {
  fetchFinopsHistory,
  fetchInfraHistory,
  fetchModulateModelled,
  fetchPlanCostHistory,
  fetchStripeFeeHistory,
  fetchVendorBalanceHistory,
  FinopsHistory,
  HEALTH_COST_DAYS,
  InfraHistory,
  ModulateModelledDay,
  PlanCostHistory,
  StripeFeeHistory,
  VendorBalanceHistory,
} from "./wall-finops";
import { wallFailure } from "./wall-source-error";
import { COLD_STORE_WAIT, wallRefreshSettled } from "./wall-cache";
import {
  allInCost,
  CostDay,
  EstimateStatus,
  estimateStatus,
  FEES_UNAVAILABLE_REASON,
  sonioxBalanceInputs,
  sonioxSeriesBroken,
} from "./wall-cost";
import { createHash } from "crypto";
import {
  firestoreSeriesStore,
  INSTANCE_ID,
  LEASE_MS,
  LegDoc,
  memorySeriesStore,
  mergeLegDoc,
  readThroughStore,
  SeriesStore,
  StoredRead,
  WriteResult,
} from "./wall-series-store";

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
  /** Headline only: oldest leg's data-through day across all series. */
  status?: { through: string | null; text: string } | null;
}

export const GROWTH_WEEKS = 26;
export const COHORT_WEEKS = 12;
export const CURVE_COHORTS = 9;
export const MONEY_WEEKS = 8;
/** Daily unit-economics points (the board shows 35 days; FinOps book
 * snapshots are daily from 2026-09-18). */
export const UNIT_DAYS = 36;
const MAU_WEEKS = Math.ceil(UNIT_DAYS / 7);
const WEEK_OFFSETS = [0, 1, 2, 3, 4, 5, 6];
/** Invisible cohort-age tag on curve field names (the board's ramp matcher). */
export const CURVE_MARK = "\u200b";
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
  rollup?: RollupRead;
  rollupStatus?: () => Promise<RollupStatus>;
  shopify: typeof fetchShopifyWeek;
  billing: () => Promise<Billing>;
  finops: (today: string) => Promise<FinopsHistory>;
  planCost: (today: string) => Promise<PlanCostHistory>;
  /** Measured Stripe fees; throws while the fee table is dark (missing scope). */
  fees?: (today: string) => Promise<StripeFeeHistory>;
  /** Soniox balance-derived day-rate; throws while that table is dark. */
  vendorBalance?: (today: string) => Promise<VendorBalanceHistory>;
  /** Modulate modelled volume line; throws while its table is dark. */
  modulate?: (today: string) => Promise<{
    byDay: Record<string, ModulateModelledDay>;
    price: number | null;
    priceAsOf: string | null;
  }>;
  /** Mercury non-GCP infra run rate; throws while that table is dark. */
  infra?: (today: string) => Promise<InfraHistory>;
  /** Shared cross-instance state; process memory when absent (tests). */
  store?: SeriesStore;
  /** Lease holder id; one per process by default. */
  instance?: string;
}
export const defaultSeriesSources: SeriesSources = {
  query: queryPosthog,
  rollup: readRollup,
  rollupStatus,
  shopify: fetchShopifyWeek,
  billing: async () => {
    const { computeBillingInfraCosts } = await import(
      "@/app/api/omi/stats/infra-costs/route"
    );
    return computeBillingInfraCosts(90, 0, true);
  },
  finops: fetchFinopsHistory,
  planCost: fetchPlanCostHistory,
  fees: fetchStripeFeeHistory,
  vendorBalance: fetchVendorBalanceHistory,
  modulate: fetchModulateModelled,
  infra: fetchInfraHistory,
  // Writes only on Cloud Run, like the snapshot (`wallSnapshotStore`).
  store: process.env.K_REVISION
    ? firestoreSeriesStore
    : readThroughStore(firestoreSeriesStore),
};

/** Leg results. Each leg is complete, partial (some periods failed) or failed. */
export interface Legs {
  growth?: AggregateRows;
  activationHistory?: AggregateRows;
  captureSource?: AggregateRows;
  retainedHistory?: AggregateRows;
  establishedHistory?: AggregateRows;
  curve?: AggregateRows;
  /** 30-day MAU keyed by days before today: days 7–13 (headline priors) … */
  mauPrior?: Record<number, number>;
  /** … and every other day the unit-economics chart draws. Split so a slow
   * history read never holds back the headline. */
  mauDaily?: Record<number, number>;
  finops?: FinopsHistory;
  /** FinOps plan cost (margin by plan); settled about D−3. */
  planCost?: PlanCostHistory;
  /** Measured Stripe processing fees (missing = the leg is unavailable). */
  fees?: StripeFeeHistory;
  /** Soniox balance series (missing = the leg is unavailable). */
  vendorBalance?: VendorBalanceHistory;
  /** Modulate modelled volume line (missing = the leg is unavailable). */
  modulate?: {
    byDay: Record<string, ModulateModelledDay>;
    price: number | null;
    priceAsOf: string | null;
  };
  /** Mercury non-GCP infra run rate (missing = the leg is unavailable). */
  infra?: InfraHistory;
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
  headline: ["finops", "mauPrior", "billing"],
  growth: ["growth"],
  activation: ["activationHistory", "captureSource"],
  retention: ["curve", "retainedHistory", "establishedHistory", "growth"],
  revenue: ["finops", "mauPrior", "mauDaily", "shopify"],
  health: [
    "billing",
    "finops",
    "mauPrior",
    "mauDaily",
    "planCost",
    "fees",
    "vendorBalance",
    "modulate",
    "infra",
  ],
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
  const read = (request: RollupRequest, sql: string) =>
    preferRollup(sources.rollup, request, () => sources.query(sql));
  const back = (weeks: number) => shiftDay(end, -7 * weeks);
  // Snapshot periods 0–5 come from the wall payload; read only 6–11.
  const history = (
    build: (stop: Date, n: number) => string,
    stop: Date,
    request: (stop: Date, n: number) => RollupRequest
  ) => {
    const requests = new Map<string, RollupRequest>();
    return periodQueries(
      (sql) => read(requests.get(sql)!, sql),
      (stop, n) => {
        const sql = build(stop, n);
        requests.set(sql, request(stop, n));
        return sql;
      },
      shiftDay(stop, -7 * SNAPSHOT_PERIODS),
      7,
      COHORT_WEEKS - SNAPSHOT_PERIODS
    ).then((rows) => offsetRows(rows, SNAPSHOT_PERIODS));
  };
  // 30-day MAU for every day the unit-economics chart draws: one read per
  // week of seven daily offsets (one scan of 36 days, about the cost of one).
  // Day 0 is the snapshot's own MAU; cost/MAU (settled D−2) uses day + 1.
  const mauWeeks = async (weeks: number[]) => {
    const out: Record<number, number> = {};
    let failure: string | null = null;
    for (const week of weeks) {
      try {
        const rows = await read(
          { kind: "mau", end: back(week), offsets: WEEK_OFFSETS },
          mauOffsetsQuery(back(week), WEEK_OFFSETS)
        );
        for (const r of rows) out[7 * week + Number(r[0])] = Number(r[1]);
      } catch (error) {
        failure ||= wallFailure("PostHog", error);
      }
    }
    if (failure) throw new PartialLeg(out, failure);
    return out;
  };
  return {
    growth: () =>
      periods(GROWTH_WEEKS, (p) =>
        read(
          { kind: "growth", end: back(p), periods: 1 },
          weeklyGrowthQuery(back(p), 1)
        )
      ),
    activationHistory: () =>
      history(
        (stop, n) => cohortQuery(stop, 7, n),
        end,
        (end, periods) => ({ kind: "cohort", end, periods, maturity: 7 })
      ),
    captureSource: () =>
      read({ kind: "capture", end }, captureSourceQuery(end)),
    retainedHistory: () =>
      history(
        (stop, n) => cohortQuery(stop, 37, n),
        end,
        (end, periods) => ({ kind: "cohort", end, periods, maturity: 37 })
      ),
    establishedHistory: () =>
      history(establishedQuery, completeWeek(now).end, (end, periods) => ({
        kind: "established",
        end,
        periods,
      })),
    // One cohort per read; partial cohorts are kept and only the missing retried.
    curve: () =>
      periods(CURVE_COHORTS, (p) =>
        read(
          {
            kind: "curve",
            end: shiftDay(end, -7 * (p + 1)),
            periods: 1,
            observedEnd: end,
          },
          retentionCurveQuery(shiftDay(end, -7 * (p + 1)), 1, end)
        )
      ),
    mauPrior: () => mauWeeks([1]),
    mauDaily: () =>
      mauWeeks(
        Array.from({ length: MAU_WEEKS }, (_, w) => w).filter((w) => w !== 1)
      ),
    finops: () => sources.finops(isoDay(now)),
    planCost: () => sources.planCost(isoDay(now)),
    fees: () =>
      sources.fees
        ? sources.fees(isoDay(now))
        : Promise.reject(new Error("Stripe fee source unavailable")),
    vendorBalance: () =>
      sources.vendorBalance
        ? sources.vendorBalance(isoDay(now))
        : Promise.reject(new Error("Soniox balance source unavailable")),
    modulate: () =>
      sources.modulate
        ? sources.modulate(isoDay(now))
        : Promise.reject(new Error("Modulate modelled source unavailable")),
    infra: () =>
      sources.infra
        ? sources.infra(isoDay(now))
        : Promise.reject(new Error("Infra run-rate source unavailable")),
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

const mauAt = (legs: Legs, offset: number) =>
  legs.mauPrior?.[offset] ?? legs.mauDaily?.[offset] ?? null;

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

/** The board's shaded "maturing" span: from the newest cohort whose window
 * has closed (`stop` − 1, the cohort's label) to now. Cohorts roll daily, so
 * the line always ends `maturity` + 1 days back; nothing is pending a weekly
 * release. A hidden 0–1 axis draws it full height. */
function maturingBand(stop: Date, now: Date): Row[] {
  return [
    { date: ts(isoDay(shiftDay(stop, -1))), maturing: 1 },
    { date: now.toISOString(), maturing: 1 },
  ];
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

/** Bar labels: short enough for the narrow column, readable without a legend. */
const CAPTURE_LABELS: Record<(typeof CAPTURE_SEGMENTS)[number], string> = {
  "Omi pendant": "Omi pendant",
  "Multiple devices": "2+ devices",
  Limitless: "Limitless",
  "Apple Watch": "Apple Watch",
  "Other device": "Other device",
  "Omi, model unknown": "Other Omi",
  "Phone + Mac": "Phone + Mac",
  "Mac only": "Mac only",
  "Phone mic only": "Phone mic",
  "No capture": "No capture",
};

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
  // (the stat's cohort); users ride in the label, largest group first.
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
      source: `${CAPTURE_LABELS[name]} · ${people.toLocaleString("en-US")}`,
      activation: (100 * activated) / people,
      people,
    };
  });
  sources.sort((a, b) => b.people - a.people);
  return {
    activation,
    capture: captured,
    sources,
    maturing: maturingBand(stop, now),
  };
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
  // One frame per cohort age (`cohort_0` = newest): the board joins them in
  // date order (Grafana sorts one frame's fields by name, which put "Aug 8"
  // after "Aug 29"). Each name carries `age` invisible marks so the board can
  // color the joined fields on a ramp, newest strongest.
  // Nine week rows per loaded cohort (the x field must exist with its y
  // field); an unloaded age is an empty frame the panel skips.
  const curves: Record<string, Row[]> = {};
  for (let age = 0; age < CURVE_COHORTS; age++) {
    const i = cohorts.indexOf(age);
    curves[`cohort_${age}`] =
      i < 0
        ? []
        : Array.from({ length: 9 }, (_, k) => ({
            week: k,
            [labels[i] + CURVE_MARK.repeat(age)]:
              byCohort.get(age)?.[k] ?? null,
          }));
  }
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
    ...curves,
    established,
    retained,
    retainedMaturing: maturingBand(shiftDay(end, -37), now),
    power: growthFrames(legs, snapshot, now).power,
  };
}

function mrrTotal(day: Record<string, number> | undefined) {
  return day ? Object.values(day).reduce((s, v) => s + v, 0) : null;
}
/** FinOps book snapshotted on a day (by `snapshot_date`, as the MRR chart and
 * margin read it). A day without a snapshot is a gap, never a neighbour's book. */
function finopsMrr(f: FinopsHistory | undefined, day: Date) {
  return mrrTotal(f?.mrr[isoDay(day)]);
}

export function revenueFrames(
  legs: Legs,
  snapshot: WallPayload | null,
  now: Date
) {
  const end = utcDay(now);
  const live = usable(metric(snapshot, "revenue.mrr"));
  // The stat is the FinOps book now (coupons applied); the live-book row only
  // appears when the stat itself fell back to the live read.
  const liveFallback =
    live != null && (live.reason || "").includes("live renewal");
  const mrrPoints = new Map<string, Row>();
  for (const [day, plans] of Object.entries(legs.finops?.mrr || {})) {
    const row: Row = { source: "FinOps book" };
    for (const k of PLAN_KEYS) row[k] = round(plans[k] ?? 0, 0);
    row.total = round(mrrTotal(plans), 0);
    mrrPoints.set(day, row);
  }
  if (liveFallback) {
    const row: Row = { source: "Live Stripe book (fallback)" };
    for (const k of PLAN_KEYS) row[k] = live.breakdown?.[k] ?? 0;
    row.total = live.value;
    mrrPoints.set(isoDay(now), row);
  }
  const mrr: Row[] = Array.from(mrrPoints.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, row]) => ({ date: ts(date), ...row }));

  const mauNow = usable(metric(snapshot, "engagement.mau"));
  const arpLive = usable(metric(snapshot, "revenue.arpmau"));
  // Daily: the FinOps book at each day ÷ that day's 30-day MAU. Days without
  // a book snapshot (before 2026-09-18) are absent, never zero.
  const arpmau: Row[] = [];
  for (let k = UNIT_DAYS - 1; k >= 0; k--) {
    const mau = k === 0 ? mauNow?.value ?? null : mauAt(legs, k) ?? null;
    const book = finopsMrr(legs.finops, shiftDay(end, -k - 1));
    const finopsArp = mau && book != null ? book / mau : null;
    const value = k === 0 && arpLive ? arpLive.value : finopsArp;
    if (value == null) continue;
    arpmau.push({
      date: ts(isoDay(shiftDay(end, -k - 1))),
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
  // Same all-in model as the snapshot's cost stats (every cost line counted),
  // including the Soniox balance series and the Modulate modelled line so the
  // chart's STT matches the stat. The fee leg is unavailable, not zero, while
  // the FinOps fee table is dark.
  const feesUnavailable = legs.fees ? null : FEES_UNAVAILABLE_REASON;
  const vendor = {
    sttMeasured: legs.planCost?.sttMeasured,
    sonioxBalance: sonioxBalanceInputs(legs.vendorBalance ?? null, cutoff),
    modulateModelled: legs.modulate ?? undefined,
    sttCash: legs.planCost?.sttCash,
    saasMeasured: legs.planCost?.saasMeasured,
    infraMeasured: legs.infra?.infraMeasured,
    infraAnnualPartial: legs.infra?.infraAnnualPartial,
    infraStripeFeesCash: legs.infra?.infraStripeFeesCash,
    stripeFees: legs.fees?.fees,
  };
  const allIn = allInCost(
    (legs.billing?.daily || []).filter((d) => d.date <= cutoff),
    legs.billing?.summary.coverage,
    vendor,
    feesUnavailable
  );
  const latestCostDay = allIn.daily.find((d) => d.date === cutoff);
  // A Soniox series that stopped covering the cutoff day puts the dated
  // constant back in use: stale now, not once the constant ages out. An infra
  // day the dated constant floors is likewise priced by that constant.
  const estimates = estimateStatus(
    now,
    {
      STT: latestCostDay?.sttMeasured,
      SaaS: latestCostDay?.saasMeasured,
      Infra: latestCostDay?.infraMeasured && !latestCostDay.infraFloored,
    },
    {
      STT:
        !!latestCostDay &&
        sonioxSeriesBroken(vendor, latestCostDay.date) &&
        !latestCostDay.sttMeasured,
    }
  );
  // 1 when a manual estimate is older than its line's staleness threshold.
  const estimateStale = estimates.some((e) => e.stale) ? 1 : 0;
  const days = allIn.daily;
  const net = metric(snapshot, "cost.net_day");
  const snapshotTotals = new Map(
    (net?.trend || []).map((t) => [t.date, t.value])
  );
  const lastFeeDay =
    Object.keys(legs.fees?.fees || {})
      .sort()
      .at(-1) ?? null;
  // The fee/infra history reads cover every frame this renders (their shared
  // window constant), so a fee-dark day keeps its Mercury stripe_fees cash
  // however old it is.
  const cost = days.slice(-HEALTH_COST_DAYS).map((d) => {
    const book = finopsMrr(legs.finops, new Date(ts(d.date)));
    return {
      date: ts(d.date),
      gcp: d.gcp,
      vertexLlm: d.vertexLlm,
      openai: d.openai,
      // Counted only when the admin API reports spend; seats are SaaS cash.
      anthropic: d.anthropic != null && d.anthropic > 0 ? d.anthropic : null,
      stt: d.stt,
      sttSource: d.sttMeasured
        ? "measured"
        : d.sttCash
        ? "estimate+cash"
        : "estimate",
      // The measured series carries ONLY measured dollars: the Soniox balance
      // delta (or usage line) plus measured Deepgram. Modelled Modulate and
      // every dated constant stay out of it (they have their own series).
      sttEstimateUsd: d.sttSonioxMeasured ? null : d.sttSonioxUsd,
      sttMeasuredUsd:
        (d.sttSonioxMeasured ? d.sttSonioxUsd : 0) +
        (d.sttDeepgramMeasured ? d.sttDeepgramUsd : 0),
      sttModulateModelledUsd: d.sttModulateModelled ? d.sttModulateUsd : null,
      sttCashUsd: d.sttCash || null,
      saas: d.saas,
      saasSource: d.saasMeasured ? "measured" : "estimate",
      saasEstimateUsd: d.saasMeasured ? null : d.saas,
      saasMeasuredUsd: d.saasMeasured ? d.saas : null,
      // The infra base is measured only when the producer's run rate stands
      // on its own; a partial run rate the dated constant floors is priced by
      // that constant. Mercury stripe_fees cash counted here (fee line dark
      // for the day) rides in its own field so neither series absorbs it.
      infra: d.infra,
      infraSource: d.infraMeasured && !d.infraFloored ? "measured" : "estimate",
      infraEstimateUsd:
        d.infraMeasured && !d.infraFloored ? null : d.infra - d.infraFeesCash,
      infraMeasuredUsd:
        d.infraMeasured && !d.infraFloored ? d.infra - d.infraFeesCash : null,
      infraFeesCashUsd: d.infraFeesCash || null,
      estimateStale,
      fees: d.fees,
      feesUnavailable: d.fees == null ? 1 : 0,
      oneTimeExcluded: d.oneTime || null,
      // The snapshot uses estimates; measured vendor lines own the all-in total.
      total:
        d.sttMeasured || d.saasMeasured || d.infraMeasured
          ? d.total
          : snapshotTotals.get(d.date) ?? d.total,
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
  // Daily, settled D−2: day k's 30-day all-in cost ÷ the same window's MAU.
  const costPerMau: Row[] = [];
  for (let k = UNIT_DAYS - 1; k >= 1; k--) {
    const windowEnd = shiftDay(end, -k); // exclusive; D−2 inclusive at k = 1
    const window = Array.from({ length: 30 }, (_, i) =>
      byDay.get(isoDay(shiftDay(windowEnd, -30 + i)))
    );
    const mau = k === 1 ? live?.denominator ?? null : mauAt(legs, k);
    const settled = window.every((v) => v != null);
    const value =
      k === 1 && live
        ? live.value
        : settled && mau
        ? window.reduce<number>((s, v) => s + (v as number), 0) / mau
        : null;
    if (value == null) continue;
    const arpmau = arp.get(isoDay(shiftDay(windowEnd, -1)));
    costPerMau.push({
      date: ts(isoDay(shiftDay(windowEnd, -1))),
      costPerMau: value,
      goal: arpmau == null ? null : round(arpmau * (1 - MARGIN_GOAL)),
    });
  }
  const marginByPlan = marginFrames(legs, days, now);
  return {
    cost,
    costPerMau,
    marginByPlan,
    marginStatus: [
      {
        text:
          marginStatus(marginByPlan, days, now) +
          (feesUnavailable
            ? " · Stripe fees unavailable (finops key scope)"
            : ` · Stripe fees measured through ${
                lastFeeDay ? shortDay(lastFeeDay) : "—"
              }`),
      },
    ],
    estimates: estimates.map((e) => ({ ...e, stale: e.stale ? 1 : 0 })),
  };
}

/** Plans on the margin chart, as FinOps plan ids: Neo (legacy), Unlimited,
 * Pro, Plus, Architect, Free. Every other FinOps segment (`unattributed`,
 * `none`, a retired id) is the unattributed row. */
export const MARGIN_PLANS = [
  "unlimited",
  "unlimited_v2",
  "operator",
  "plus",
  "architect",
  "basic",
] as const;
export const MARGIN_DAYS = 35;

/** Allocated-estimate margin by plan (David 2026-10-17), one row per day that
 * has both a settled FinOps plan cost and that day's book snapshot; FinOps
 * plan cost settles about D−3, and a missing day is absent, never zero.
 * Plan cost = FinOps fully-loaded plan cost + a share of the shared remainder
 * (TV all-in total − FinOps fully loaded: BigQuery, STT, SaaS) in proportion
 * to the plan's cost-active user-days that day, so the plans and the
 * unattributed row sum to the all-in total. Revenue = that day's book ÷ 30.4.
 * Paid plans carry margin %; Free has no revenue, so only its −$/day. */
export function marginFrames(legs: Legs, allInDays: CostDay[], now: Date) {
  const allIn = new Map(allInDays.map((d) => [d.date, d.total]));
  const known = new Set<string>(MARGIN_PLANS);
  const rows: Row[] = [];
  for (let k = MARGIN_DAYS; k >= 1; k--) {
    const day = isoDay(shiftDay(utcDay(now), -k));
    const plans = legs.planCost?.plans[day];
    const book = legs.finops?.mrr[day];
    const total = allIn.get(day);
    if (!plans || !book || total == null) continue;
    const segments = Object.entries(plans);
    const finops = segments.reduce((s, [, p]) => s + p.usd, 0);
    const users = segments.reduce((s, [, p]) => s + p.users, 0);
    if (!users) continue;
    const shared = total - finops;
    const allocated = (p: { usd: number; users: number }) =>
      p.usd + (shared * p.users) / users;
    const row: Row = {
      date: ts(day),
      allInTotal: round(total),
      finopsTotal: round(finops),
      shared: round(shared),
    };
    for (const plan of MARGIN_PLANS) {
      const cost = allocated(plans[plan] ?? { usd: 0, users: 0 });
      const revenue = (book[plan] ?? 0) / DAYS_PER_MONTH;
      row[`${plan}Revenue`] = round(revenue);
      row[`${plan}Cost`] = round(cost);
      row[`${plan}Margin`] = round(revenue - cost);
      row[`${plan}Pct`] =
        revenue > 0 ? round((100 * (revenue - cost)) / revenue, 1) : null;
    }
    row.unattributedCost = round(
      segments
        .filter(([plan]) => !known.has(plan))
        .reduce((s, [, p]) => s + allocated(p), 0)
    );
    row.unattributedRevenue = round(
      Object.entries(book)
        .filter(([plan]) => !known.has(plan))
        .reduce((s, [, v]) => s + v / DAYS_PER_MONTH, 0)
    );
    rows.push(row);
  }
  return rows;
}

const shortDay = (day: string) =>
  new Date(`${day}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });

/** The margin chart's freshness line: its own data-through day (it lags the
 * rest of the wall) and how its STT, SaaS and Infra lines were priced. */
function marginStatus(rows: Row[], days: CostDay[], now: Date) {
  const through = rows.length ? String(rows.at(-1)!.date).slice(0, 10) : null;
  const day = through ? days.find((d) => d.date === through) : undefined;
  // A floored infra day is priced by the dated constant, so that line shows
  // its estimate (and the constant's age) rather than a measured label.
  const infraOwnsItsPrice = day?.infraMeasured && !day.infraFloored;
  const measuredByLine: Record<EstimateStatus["line"], boolean | undefined> = {
    STT: day?.sttMeasured,
    SaaS: day?.saasMeasured,
    Infra: infraOwnsItsPrice,
  };
  const estimates = estimateStatus(now, {
    STT: day?.sttMeasured,
    SaaS: day?.saasMeasured,
    Infra: infraOwnsItsPrice,
  });
  const shown = estimates.filter((e) => !measuredByLine[e.line]);
  const asOf = shown.map((e) => e.asOf).sort()[0];
  const stale = shown.some((e) => e.stale);
  const labels = [
    day?.sttMeasured ? "STT measured" : "STT estimate",
    day?.saasMeasured ? "measured SaaS (Mercury)" : "SaaS estimate",
    infraOwnsItsPrice
      ? "measured Infra non-GCP (Mercury)"
      : day?.infraMeasured
      ? "Infra non-GCP estimate (floors partial Mercury run rate)"
      : "Infra non-GCP estimate",
  ];
  const dated = asOf ? ` as of ${shortDay(asOf)}` : "";
  return [
    `Margin through ${through ? shortDay(through) : "—"}`,
    `${labels.join(" · ")}${dated}${stale ? " (stale)" : ""}`,
  ].join(" · ");
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
/** Every snapshot metric a headline stat draws (live MRR, per-user stats too). */
const HEADLINE_IDS = new Set<string>([
  ...HEADLINE.map(([, id]) => id),
  "revenue.mrr",
  "revenue.arpmau",
  "cost.per_mau_month",
  "cost.per_customer_month",
]);
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
  const missing = rows.length === 0 || rows.at(-1)?.value == null;
  const text = missing
    ? "—"
    : shown == null
    ? "no prior"
    : // Non-breaking spaces: a narrow stat must not wrap the glyph apart.
      `${shown > 0 ? "▲" : shown < 0 ? "▼" : "■"}\u00a0${Math.abs(
        shown
      ).toFixed(1)}${unit === "pp" ? "\u00a0pp" : "%"}${
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
  // Per-user stats compare with the point a week earlier (the charts are daily).
  const weekBefore = (rows: Row[]) => {
    const last = rows.at(-1);
    if (!last) return [undefined, undefined] as const;
    const day = isoDay(shiftDay(new Date(String(last.date)), -7));
    return [
      rows.find((r) => String(r.date).slice(0, 10) === day),
      last,
    ] as const;
  };
  const [arpPrior, arpNow] = weekBefore(revenue.arpmau);
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
  const [cpmPrior, cpmNow] = weekBefore(
    healthFrames(legs, snapshot, now).costPerMau
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
  // A missing stat keeps its slot (one null row → the stat shows "—"), so the
  // stat values and the strip below stay aligned column for column. The slot
  // is dated at the data-through day the stats describe, never today.
  const through = ts(isoDay(shiftDay(utcDay(now), -1)));
  for (const keys of Object.values(DELTA_STRIPS))
    for (const key of keys)
      if (!frames[key]?.length) frames[key] = [{ date: through, value: null }];
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
//
// The shared store (Firestore via `wall-series-store`) holds each leg's
// last-good value, retry schedule and the day's successful reads, so every
// Cloud Run instance serves the same data and a fill one instance abandons
// resumes on the next. One instance fills a leg at a time under a fenced
// lease; an unknown lease state never counts as ownership. Only when the store
// has failed repeatedly (STORE_FAIL_LIMIT within STORE_FAIL_WINDOW) does an
// instance fall back to filling from process memory, still single-flight.

interface LegEntry {
  day: string;
  at: number;
  value?: unknown;
  complete: boolean;
  reason?: string;
  retryAt: number;
  /** Consecutive incomplete refreshes; drives exponential backoff. */
  failures: number;
}
type Doc = LegDoc<LegEntry>;
interface LocalLeg {
  doc: Doc | null;
  readAt: number;
  flight?: Promise<void>;
  /** Another instance holds a live lease and the leg is due. */
  busy?: boolean;
  /** The lease could not be checked (timeout or store error). */
  storeDown?: boolean;
}
const SHARED_READ_MS = 10_000;
const STORE_WAIT = 2_000;
export const STORE_FAIL_LIMIT = 5;
export const STORE_FAIL_WINDOW = 10 * 60_000;
let local = new Map<LegName, LocalLeg>();
let localStore = memorySeriesStore();
let storeFailures: number[] = [];
let lane: Promise<unknown> = Promise.resolve();

const sqlHash = (sql: string) =>
  createHash("sha1").update(sql).digest("hex").slice(0, 16);

class StoreTimeout extends Error {}
class LeaseLost extends Error {}

function withTimeout<T>(work: Promise<T>, wait = STORE_WAIT): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  return Promise.race([
    work,
    new Promise<T>(
      (_, reject) =>
        (timer = setTimeout(() => reject(new StoreTimeout()), wait))
    ),
  ]).finally(() => clearTimeout(timer));
}

function storeOk() {
  storeFailures = [];
}
function storeFailed(now: number) {
  storeFailures = [
    ...storeFailures.filter((t) => now - t < STORE_FAIL_WINDOW),
    now,
  ];
}
/** The shared store is known unreachable: sustained failures, no success. */
function storeDown(now: number) {
  return (
    storeFailures.filter((t) => now - t < STORE_FAIL_WINDOW).length >=
    STORE_FAIL_LIMIT
  );
}

/** ok | partial | timeout | http_<status> | error, from a controlled reason. */
export function legOutcome(reason: string | undefined, complete: boolean) {
  if (!reason) return complete ? "ok" : "error";
  const status = /HTTP (\d{3})/.exec(reason);
  if (status) return `http_${status[1]}`;
  if (/timed out/i.test(reason)) return "timeout";
  return "error";
}

function rowCount(value: unknown) {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") {
    const daily = (value as { daily?: unknown }).daily;
    if (Array.isArray(daily)) return daily.length;
    return Object.keys(value).length;
  }
  return 0;
}

function log(event: string, instance: string, fields: Record<string, unknown>) {
  // Aggregates only: leg names, outcomes, timings and row counts.
  console.log(JSON.stringify({ event, instance, ...fields }));
}

/** Cached view of a leg's shared doc; every refresh probes the real store. */
async function legState(
  name: LegName,
  store: SeriesStore,
  now: number
): Promise<LocalLeg> {
  const cached = local.get(name);
  if (cached && (cached.flight || now - cached.readAt < SHARED_READ_MS))
    return cached;
  let doc = cached?.doc ?? null;
  try {
    // A fresh process's first read also opens the store channel.
    const shared = await withTimeout(
      store.read<LegEntry>(name),
      doc ? STORE_WAIT : COLD_STORE_WAIT
    );
    storeOk();
    if (shared) doc = shared;
  } catch {
    storeFailed(now); // keep serving the per-process last-good
  }
  const state: LocalLeg = { ...(cached || {}), doc, readAt: now };
  local.set(name, state);
  return state;
}

function nextEntry(
  previous: LegEntry | null,
  result: { value: unknown; complete: boolean; reason?: string },
  day: string,
  now: number
): LegEntry {
  const { value, complete, reason } = result;
  // A partial read with nothing in it is a failure, not an empty chart.
  const failed =
    value === undefined ||
    (Array.isArray(value)
      ? value.length === 0
      : typeof value === "object" &&
        value !== null &&
        Object.keys(value).length === 0 &&
        !complete);
  // Stale-good: a failed refresh keeps the last good value (≤24h). Times use
  // the request clock so cache ages and cooldowns follow `now`.
  const keep =
    failed && previous?.value !== undefined && now - previous.at < MAX_STALE;
  const failures = previous?.failures ?? 0;
  return {
    day: keep ? previous!.day : day,
    at: keep ? previous!.at : now,
    value: keep ? previous!.value : failed ? undefined : value,
    complete: complete && !failed,
    reason,
    failures: complete && !failed ? 0 : failures + 1,
    retryAt:
      now +
      Math.min(
        MAX_BACKOFF,
        (failed ? FAILURE_RETRY : PARTIAL_RETRY) * 2 ** failures
      ),
  };
}

/** In-process single flight for starting a leg. */
let starting = new Map<LegName, Promise<{ flight: Promise<void> } | null>>();
function ensureLeg(
  name: LegName,
  sources: SeriesSources,
  store: SeriesStore,
  day: string,
  nowDate: Date,
  retain: (work: Promise<unknown>) => void
) {
  const pending = starting.get(name);
  if (pending) return pending;
  const start = startLeg(name, sources, store, day, nowDate, retain).finally(
    () => starting.delete(name)
  );
  starting.set(name, start);
  return start;
}

async function startLeg(
  name: LegName,
  sources: SeriesSources,
  store: SeriesStore,
  day: string,
  nowDate: Date,
  retain: (work: Promise<unknown>) => void
): Promise<{ flight: Promise<void> } | null> {
  const now = nowDate.getTime();
  const holder = sources.instance ?? INSTANCE_ID;
  const state = await legState(name, store, now);
  if (state.flight) return { flight: state.flight };
  const entry = state.doc?.entry ?? null;
  const due =
    !(entry?.day === day && entry.complete) && now >= (entry?.retryAt ?? 0);
  state.busy = state.storeDown = false;
  if (!due) return null;

  // Fill through the shared store; process memory only once the shared store
  // is known down. Either way the fill needs a lease it positively acquired.
  const shared = store !== localStore;
  const fillStore = shared && storeDown(now) ? localStore : store;
  const attempt = fillStore.acquire(name, holder, now);
  const lease = await withTimeout(attempt).catch(() => {
    // Unknown outcome: never ownership. A late grant is handed back.
    attempt.then((late) => {
      if (late.status === "acquired") void fillStore.release(name, late.token);
    });
    return { status: "unavailable" as const };
  });
  if (fillStore === store && shared)
    lease.status === "unavailable" ? storeFailed(now) : storeOk();
  if (lease.status !== "acquired") {
    state.busy = lease.status === "contended";
    state.storeDown = lease.status === "unavailable";
    return null;
  }
  const token = lease.token;
  // Re-read under the lease: another holder may have just finished.
  let doc: Doc;
  try {
    doc = (await withTimeout(fillStore.read<LegEntry>(name))) ??
      (fillStore === localStore ? state.doc : null) ?? {
        entry: null,
        reads: { day, rows: {} },
      };
  } catch {
    if (fillStore === store && shared) storeFailed(now);
    void fillStore.release(name, token);
    state.storeDown = true;
    return null;
  }
  if (doc.entry?.day === day && doc.entry.complete) {
    state.doc = doc;
    void fillStore.release(name, token);
    return null;
  }
  const previous = doc.entry ?? state.doc?.entry ?? null;
  const reads: Record<string, StoredRead> =
    doc.reads?.day === day ? { ...doc.reads.rows } : {};
  const started = Date.now();
  const clock = () => now + (Date.now() - started);
  // Set when renewal fails or a fenced write is refused: stop at the next read.
  let lost = false;
  let saving: Promise<unknown> = Promise.resolve();
  const query: Query = async (sql) => {
    if (lost) throw new LeaseLost();
    const key = sqlHash(sql);
    const hit = reads[key];
    if (hit)
      return Object.assign(
        hit.rows.map((r) => [...r]),
        { sourceRefreshedAt: hit.refreshedAt }
      );
    const readStarted = Date.now();
    // One series PostHog read at a time per instance, after any snapshot refresh.
    const run = lane.then(wallRefreshSettled).then(() => {
      if (lost) throw new LeaseLost();
      return sources.query(sql);
    });
    lane = run.catch(() => undefined);
    try {
      const rows = await run;
      log("wall_series_read", holder, {
        leg: name,
        outcome: "ok",
        duration_ms: Date.now() - readStarted,
        rows: rows.length,
      });
      const read: StoredRead = {
        rows: rows.map((r) => [...r]),
        refreshedAt: rows.sourceRefreshedAt ?? null,
        at: Date.now(),
      };
      reads[key] = read;
      // Persist progress (fenced, merged) so another instance can resume.
      saving = saving
        .then(() =>
          fillStore.write(
            name,
            token,
            { reads: { day, rows: { [key]: read } } },
            clock()
          )
        )
        .then(
          (written) => {
            if (written !== "written") lost = true;
          },
          () => {
            lost = true;
          }
        );
      return rows;
    } catch (error) {
      if (error instanceof LeaseLost) throw error;
      const reason = wallFailure("PostHog", error);
      log("wall_series_read", holder, {
        leg: name,
        outcome: legOutcome(reason, false),
        error_class: reason,
        duration_ms: Date.now() - readStarted,
        rows: 0,
      });
      throw error;
    }
  };
  const renew = setInterval(() => {
    fillStore.renew(name, token, clock()).then(
      (ok) => {
        if (!ok) lost = true;
      },
      () => {
        lost = true;
      }
    );
  }, LEASE_MS / 3);
  const flight = legJobs({ ...sources, query }, nowDate)
    [name]()
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
    .then(async (result) => {
      clearInterval(renew);
      await saving;
      const next = nextEntry(previous, result, day, now);
      // The final write is awaited (off the request path, inside after())
      // before the lease is released, and only lands while my token holds.
      let outcome: WriteResult | "lease_lost" = "lease_lost";
      if (!lost)
        outcome = await fillStore
          .write(
            name,
            token,
            { entry: next, reads: { day, rows: reads } },
            clock()
          )
          .catch(() => "unavailable" as const);
      if (outcome === "written") {
        await fillStore.release(name, token);
        local.set(name, {
          doc: mergeLegDoc(doc, { entry: next, reads: { day, rows: reads } }),
          readAt: now,
        });
      } else {
        // Not mine any more: drop the local flight and re-read the shared doc.
        local.set(name, { doc: state.doc, readAt: 0 });
      }
      log("wall_series_leg", holder, {
        leg: name,
        outcome:
          outcome !== "written"
            ? outcome === "unavailable"
              ? "store_unavailable"
              : "lease_lost"
            : result.complete
            ? "ok"
            : result.value !== undefined && rowCount(result.value) > 0
            ? `partial:${legOutcome(result.reason, false)}`
            : legOutcome(result.reason, false),
        error_class: result.reason ?? null,
        duration_ms: Date.now() - started,
        rows: rowCount(result.value),
        served_stale: next.value !== undefined && next.day !== day,
        failures: next.failures,
        store: fillStore === localStore && shared ? "process" : "shared",
      });
    });
  state.flight = flight;
  retain(flight);
  return { flight };
}

/** Leg freshness for the TV's "data through" line. */
export function dataStatus(
  entries: (LegEntry | null | undefined)[],
  filling: number
) {
  const days = entries
    .filter((e): e is LegEntry => e?.value !== undefined)
    .map((e) => e.day);
  const oldest = days.sort()[0];
  const through = oldest
    ? isoDay(shiftDay(new Date(`${oldest}T00:00:00Z`), -1))
    : null;
  const label = through
    ? new Date(`${through}T00:00:00Z`).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        timeZone: "UTC",
      })
    : "—";
  return {
    through,
    text: `${label} (UTC)${filling ? ` · ${filling} filling` : ""}`,
  };
}

const ALL_LEGS = Array.from(new Set(Object.values(LEGS_FOR).flat()));

export async function seriesPayload(
  name: SeriesName,
  snapshot: Promise<WallPayload | null>,
  now = new Date(),
  sources: SeriesSources = defaultSeriesSources,
  retain: (work: Promise<unknown>) => void = () => {}
): Promise<SeriesPayload> {
  const day = isoDay(utcDay(now));
  const store = sources.store ?? localStore;
  const starts = await Promise.all(
    LEGS_FOR[name].map((leg) =>
      ensureLeg(leg, sources, store, day, now, retain)
    )
  );
  const flights = starts.flatMap((s) => (s ? [s.flight] : []));
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
  let refreshing = false;
  for (const leg of LEGS_FOR[name]) {
    const state = local.get(leg);
    const entry = state?.doc?.entry;
    const running = Boolean(state?.flight || state?.busy);
    refreshing ||= running;
    if (entry?.value !== undefined)
      (legs as Record<string, unknown>)[leg] = entry.value;
    if (entry?.day !== day && entry?.value !== undefined) cacheStale = true;
    if (entry?.value === undefined && running)
      gaps[leg] = "Series refresh running";
    if (entry?.reason) gaps[leg] = entry.reason;
    else if (entry?.value === undefined && !running)
      gaps[leg] = state?.storeDown
        ? "Shared series store unavailable"
        : "Series data unavailable";
  }
  // A snapshot with no value yet is still filling (or retrying): never settled,
  // so the proxy keeps re-polling instead of pinning the empty frames.
  if (wall && wall.metrics.every((m) => m.value == null)) {
    refreshing = true;
    gaps.snapshot = wall.refreshError || "Snapshot refresh running";
  } else if (wall?.refreshing || wall?.retryableFailures) refreshing = true;
  // A finished partial snapshot is retried in 30s: keep it unsettled so the
  // proxy does not pin the gap (or a retained stat) for its settled TTL.
  const frames = assembleSeries(name, legs, wall, now);
  let status: SeriesPayload["status"] = null;
  if (name === "headline") {
    const states = await Promise.all(
      ALL_LEGS.map((leg) => legState(leg, store, now.getTime()))
    );
    const filling = states.filter(
      (s) => s.doc?.entry?.value === undefined && (s.flight || s.busy)
    ).length;
    status = dataStatus(
      states.map((s) => s.doc?.entry),
      filling
    );
    // The TV's one freshness line (no diagnostics table on the wall); the
    // rollup detail below stays in the API's status and gaps.
    // A headline stat the cache kept from an earlier read is not current.
    const retained = (wall?.metrics || []).filter(
      (m) => m.retainedSince && HEADLINE_IDS.has(m.id)
    ).length;
    frames.through = [
      {
        text: `Data through ${status.text}${
          retained ? ` · ${retained} stat${retained > 1 ? "s" : ""} stale` : ""
        }`,
      },
    ];
    const rollup = await sources
      .rollupStatus?.()
      .catch(() => ({ through: null, reason: "unavailable" }));
    if (rollup)
      status.text += ` · rollup ${
        rollup.through || rollup.reason || "unavailable"
      }`;
    frames.gaps = [
      { metric: "Data through", missing: status.text, reason: "" },
      ...(frames.gaps || []),
    ];
  }
  return {
    name,
    definitionVersion: DEFINITION_VERSION,
    generatedAt: new Date().toISOString(),
    partial: Object.keys(gaps).length > 0,
    refreshing,
    cacheStale,
    status,
    frames,
    gaps,
  };
}

export function resetSeriesCache() {
  local = new Map();
  starting = new Map();
  storeFailures = [];
  localStore = memorySeriesStore();
  lane = Promise.resolve();
}
