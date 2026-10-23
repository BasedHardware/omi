import {
  completeWeek,
  completeWindow,
  COVERAGE_REASON,
  DEFINITION_VERSION,
  freshness,
  isoDay,
  shiftDay,
  utcDay,
} from "./qualified-activity";
import {
  AggregateRows,
  activityQuery,
  cohortQuery,
  establishedQuery,
  Query,
  queryPosthog,
  periodQueries,
} from "./wall-posthog";
import {
  MCP_ACTIVITY_VERSION,
  MCP_MARKER_MISSING,
  MCP_MARKER_STATUS_ROW,
} from "./wall-mcp";
import { WallSourceError, wallFailure } from "./wall-source-error";
import { fetchShopifyWeek } from "./wall-shopify";
import {
  fetchFinopsHistory,
  fetchInfraHistory,
  fetchModulateModelled,
  fetchPlanCostHistory,
  fetchStripeFeeHistory,
  fetchVendorBalanceHistory,
  FinopsHistory,
  InfraHistory,
  ModulateModelledDay,
  PlanCostHistory,
  StripeFeeHistory,
  VendorBalanceHistory,
} from "./wall-finops";
import { WallJobCache } from "./wall-job-cache";
import {
  allInCost,
  estimateStatus,
  FEES_UNAVAILABLE_REASON,
  INFRA_AS_OF,
  INFRA_MONTHLY_USD,
  MODULATE_UNAVAILABLE_REASON,
  modulateReconciliation,
  SAAS_AS_OF,
  SAAS_MONTHLY_USD,
  sonioxBalanceInputs,
  SONIOX_GAP_FLAG,
  SONIOX_UNAVAILABLE_REASON,
  sonioxSeriesBroken,
  STT_MONTHLY_USD,
  STT_SOURCE,
} from "./wall-cost";

export const WALL_DEFINITIONS = [
  ["growth.wau", "WAU", "people", "Growth"],
  ["growth.true_new_7d", "New users", "people", "Growth"],
  ["activation.rate", "Activation · ≥2 days", "percent", "Activation"],
  ["retention.if_activated", "Retained if activated", "percent", "Retention"],
  ["retention.recovery", "Recovery", "percent", "Retention"],
  ["retention.day1_return", "Day-1 return", "percent", "Retention"],
  [
    "retention.established_week",
    "Established retention",
    "percent",
    "Retention",
  ],
  ["engagement.dau", "DAU", "people", "Growth"],
  ["engagement.mau", "MAU", "people", "Growth"],
  ["engagement.saved_creators", "Saved creators", "people", "Activation"],
  ["engagement.assistant_success", "Assistant success", "people", "Activation"],
  ["revenue.arpmau", "ARPMAU", "USD/person/month", "Revenue"],
  ["revenue.mrr", "Omi-plan MRR", "USD/month", "Revenue"],
  ["revenue.activated_paid_30d", "Activated → paid", "percent", "Activation"],
  ["revenue.payer_churn", "Payer churn", "percent", "Revenue"],
  ["revenue.hardware_units_week", "Hardware units", "devices", "Revenue"],
  ["revenue.hardware_usd_week", "Hardware sales", "USD", "Revenue"],
  ["cost.net_day", "All-in cost / day", "USD/day", "Health"],
  ["cost.per_mau_month", "All-in cost / MAU", "USD/person/30d", "Health"],
  [
    "cost.per_customer_month",
    "Software cost / paying customer",
    "USD/customer/30d",
    "Health",
  ],
  ["cost.gross_margin_pct", "Gross margin · goal 60%", "percent", "Revenue"],
  ["health.crash_free", "Crash-free · macOS", "percent", "Health"],
  ["health.thumbs_positive", "Positive answers", "percent", "Health"],
  ["revenue.plan_prepay_usd_week", "Plan prepay sold · cash", "USD", "Revenue"],
  [
    "activation.capture_week1_share",
    "Capture in week 1",
    "percent",
    "Activation",
  ],
] as const;
export type MetricId = (typeof WALL_DEFINITIONS)[number][0];
export interface Split {
  macos: number | null;
  mobile: number | null;
  other: number | null;
  /** Additive MCP-only people: no qualified app activity in the same window. */
  mcp?: number | null;
}
export interface Metric {
  id: MetricId;
  label: string;
  column: string;
  value: number | null;
  prev: number | null;
  unit: string;
  split: Split;
  mcpReason?: string;
  numerator: number | null;
  denominator: number | null;
  splitCounts:
    | (Record<
        "macos" | "mobile" | "other",
        { numerator: number; denominator: number }
      > & { mcp?: { numerator: number; denominator: number } })
    | null;
  fixture?: boolean;
  materialGap?: boolean;
  status: "exact" | "proxy" | "null";
  reason: string | null;
  dataThrough: string | null;
  sourceRefreshedAt: string | null;
  definitionVersion: string;
  stale: boolean;
  /** Controlled source error; only failed nulls may retain last-good values. */
  retryableFailure?: string;
  /** Any controlled source failure: the cache keeps the last good value. */
  sourceFailure?: string;
  retainedSince?: string;
  partial: boolean;
  windowStart: string | null;
  windowEnd: string | null;
  /** Complete periods, oldest first. Splits/counts are present for observed periods. */
  /** Revenue only: live MRR by FinOps plan key, summing to `value`. */
  breakdown?: Record<string, number>;
  trend: {
    date: string;
    value: number | null;
    split?: Split;
    numerator?: number;
    denominator?: number | null;
  }[];
}
const emptySplit = (): Split => ({ macos: null, mobile: null, other: null });
const bucket = (p: unknown): "macos" | "mobile" | "other" =>
  p === "macos" ? "macos" : p === "ios" || p === "android" ? "mobile" : "other";
export interface WallSources {
  query: Query;
  shopify: typeof fetchShopifyWeek;
  planCost?: (today: string) => Promise<PlanCostHistory>;
  /** FinOps Stripe book history (MRR/paying by snapshot day). */
  finops?: (today: string) => Promise<FinopsHistory>;
  /** Measured Stripe processing fees; throws while the fee table is dark. */
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
  stripe: () => Promise<{
    usd: number;
    byPlan?: Record<string, number>;
    partial: boolean;
    unmappedProducts: number;
    unsupportedItems: number;
    fixture?: boolean;
    dataThrough?: string;
    sourceRefreshedAt?: string;
  }>;
  billing: () => Promise<{
    daily: {
      date: string;
      total: number;
      components?: Record<string, unknown>;
    }[];
    generatedAt: number;
    summary: {
      costSource?: string;
      partial: boolean;
      windowEnd?: string;
      coverage?: { openai?: boolean; anthropic?: boolean };
    };
  } | null>;
}
export const defaultWallSources: WallSources = {
  query: queryPosthog,
  shopify: fetchShopifyWeek,
  planCost: fetchPlanCostHistory,
  finops: fetchFinopsHistory,
  fees: fetchStripeFeeHistory,
  vendorBalance: fetchVendorBalanceHistory,
  modulate: fetchModulateModelled,
  infra: fetchInfraHistory,
  stripe: async () => {
    const { getOptionalStripeRead } = await import("./stripe");
    const { fetchWallSubscriptionBook, wallSubscriptionBook } = await import(
      "./stripe-subscriptions"
    );
    if (process.env.OMI_TV_LOCAL_STRIPE_FIXTURE_PATH) {
      if (
        process.env.NODE_ENV === "production" ||
        process.env.DEV_BYPASS_AUTH !== "1"
      )
        throw new Error("Stripe fixture requires development bypass");
      const { readFile } = await import("node:fs/promises");
      const fixture = JSON.parse(
        await readFile(process.env.OMI_TV_LOCAL_STRIPE_FIXTURE_PATH, "utf8")
      );
      return {
        ...wallSubscriptionBook(fixture.subscriptions),
        partial: false,
        fixture: true,
        dataThrough: fixture.dataThrough,
        sourceRefreshedAt: fixture.sourceRefreshedAt,
      };
    }
    const stripe = getOptionalStripeRead();
    if (!stripe)
      throw new Error(
        "Stripe read key unavailable (STRIPE_READ_API_KEY or STRIPE_SECRET_KEY)"
      );
    return fetchWallSubscriptionBook(stripe);
  },
  billing: async () => {
    const { computeBillingInfraCosts } = await import(
      "@/app/api/omi/stats/infra-costs/route"
    );
    return computeBillingInfraCosts(60, 0, true);
  },
};
const NULL_REASONS: Partial<Record<MetricId, string>> = {
  "revenue.mrr":
    "Stripe plan book unavailable; restricted read credentials required",
  "revenue.arpmau": "Corrected same-cutoff MRR snapshot unavailable",
  "cost.per_customer_month":
    "Paying-customer book unavailable; FinOps plan revenue required",
  "revenue.activated_paid_30d":
    "Paid-person billing join missing; signup linkage required",
  "revenue.payer_churn":
    "Payer month/lapse history missing; distinct-payer snapshots required",
  "cost.gross_margin_pct":
    "Revenue/cost coverage incomplete; recognized revenue, STT and fees required; 60% is a goal",
  "health.crash_free":
    "Crash reporting coverage unverified; zero crash events cannot prove 100% crash-free",
  "health.thumbs_positive":
    "Ratings aggregate source missing; message creation/vote linkage required",
};
export function emptyWallMetrics() {
  return Object.fromEntries(
    WALL_DEFINITIONS.map(([id, label, unit, column]) => [
      id,
      {
        id,
        label,
        unit,
        column,
        value: null,
        prev: null,
        split: emptySplit(),
        numerator: null,
        denominator: null,
        splitCounts: null,
        status: "null",
        reason:
          NULL_REASONS[id] ||
          (id.startsWith("cost.")
            ? "Settled billing aggregate not refreshed"
            : "PostHog aggregate not refreshed"),
        dataThrough: null,
        sourceRefreshedAt: null,
        definitionVersion: DEFINITION_VERSION,
        stale: true,
        partial: false,
        windowStart: null,
        windowEnd: null,
        trend: [],
      } as Metric,
    ])
  ) as Record<MetricId, Metric>;
}
/** One complete period of a snapshot aggregate: headline value, additive splits
 * and split counts. Shared by the snapshot and the v3 series so a series point
 * and the matching stat are the same computation over the same rows.
 */
export function aggregatePeriod(
  rows: unknown[][],
  period: number,
  numeratorIndex = 2,
  denominatorIndex?: number,
  mcpActivity = false,
  markerSeen = false
) {
  const subset = rows.filter(
    (r) => Number(r[0]) === period && r[1] !== MCP_MARKER_STATUS_ROW
  );
  const num = subset.reduce((a, r) => a + Number(r[numeratorIndex]), 0);
  const den =
    denominatorIndex == null
      ? null
      : subset.reduce((a, r) => a + Number(r[denominatorIndex]), 0);
  const value =
    subset.length === 0
      ? null
      : den == null
      ? num
      : den > 0
      ? (100 * num) / den
      : null;
  const counts = {
    macos: { numerator: 0, denominator: 0 },
    mobile: { numerator: 0, denominator: 0 },
    other: { numerator: 0, denominator: 0 },
    mcp: { numerator: 0, denominator: 0 },
  };
  for (const r of subset) {
    const b =
      counts[mcpActivity && r[1] === "integrations" ? "mcp" : bucket(r[1])];
    b.numerator += Number(r[numeratorIndex]);
    b.denominator += denominatorIndex == null ? 0 : Number(r[denominatorIndex]);
  }
  const split: Split = {
    macos: null,
    mobile: null,
    other: null,
    ...(mcpActivity ? { mcp: markerSeen ? counts.mcp.numerator : null } : {}),
  };
  for (const key of ["macos", "mobile", "other"] as const)
    split[key] =
      den == null
        ? counts[key].numerator
        : counts[key].denominator
        ? (100 * counts[key].numerator) / counts[key].denominator
        : null;
  return { value, num, den, counts, split, observed: subset.length > 0 };
}
export async function computeWall(
  sources: WallSources = defaultWallSources,
  now = new Date(),
  jobCache?: WallJobCache
) {
  const metrics = emptyWallMetrics();
  const end = utcDay(now);
  function stamp(
    m: Metric,
    start: Date,
    stop: Date,
    reason = COVERAGE_REASON,
    refreshed: string | null = new Date().toISOString()
  ) {
    m.status = m.value == null ? "null" : "proxy";
    m.reason = reason;
    m.windowStart = start.toISOString();
    m.windowEnd = stop.toISOString();
    m.dataThrough = shiftDay(stop, -1).toISOString().slice(0, 10);
    m.sourceRefreshedAt = refreshed;
    m.stale = freshness(refreshed, m.dataThrough, "hourly", now).stale;
  }
  function fromCounts(
    id: MetricId,
    rows: AggregateRows,
    stop: Date,
    days: number,
    numeratorIndex = 2,
    denominatorIndex?: number
  ) {
    const m = metrics[id];
    const mcpActivity = [
      "growth.wau",
      "engagement.dau",
      "engagement.mau",
    ].includes(id);
    const markerSeen = mcpActivity && rows.some((r) => Number(r[3]) > 0);
    for (let period = 5; period >= 0; period--) {
      const { value, num, den, counts, split, observed } = aggregatePeriod(
        rows,
        period,
        numeratorIndex,
        denominatorIndex,
        mcpActivity,
        markerSeen
      );
      m.trend.push({
        date: isoDay(shiftDay(stop, -days * period - 1)),
        value,
        ...(observed ? { split, numerator: num, denominator: den } : {}),
      });
      if (period === 1) m.prev = value;
      if (period !== 0) continue;
      m.value = value;
      m.numerator = num;
      m.denominator = den;
      m.splitCounts = {
        macos: counts.macos,
        mobile: counts.mobile,
        other: counts.other,
        ...(markerSeen ? { mcp: counts.mcp } : {}),
      };
      m.split = split;
    }
    stamp(
      m,
      shiftDay(stop, -days),
      stop,
      COVERAGE_REASON +
        (rows.sourceRefreshedAt
          ? ""
          : " Source refresh watermark unavailable."),
      rows.sourceRefreshedAt ?? null
    );
    if (mcpActivity) {
      m.definitionVersion = MCP_ACTIVITY_VERSION;
      m.mcpReason = markerSeen
        ? "MCP-only: no qualified app activity in window; daily cadence screen (cross-day bursts deferred)"
        : MCP_MARKER_MISSING;
      m.reason += ` ${m.mcpReason}.`;
    }
    if (m.value == null)
      m.reason =
        (denominatorIndex == null
          ? "No observed PostHog activity in period; "
          : "Zero cohort denominator; ") + COVERAGE_REASON;
  }
  let retryableFailures = 0;
  // Set by the billing job for the derived per-customer stat (same invocation).
  let windowPlans: PlanCostHistory | null = null;
  let windowFinops: FinopsHistory | null = null;
  const jobs: (() => Promise<void>)[] = [];
  const guarded =
    (ids: MetricId[], source: string, job: () => Promise<void>) => async () => {
      const restored = jobCache?.restore(ids, metrics, isoDay(end));
      if (restored) {
        if (restored === "retryable") retryableFailures++;
        return;
      }
      try {
        await job();
        jobCache?.store(ids, metrics, isoDay(end));
      } catch (error) {
        const retryable =
          (error instanceof WallSourceError && error.retryable) ||
          (error instanceof Error &&
            ["TimeoutError", "AbortError"].includes(error.name));
        if (retryable) retryableFailures++;
        const reason = wallFailure(source, error);
        for (const id of ids)
          if (metrics[id].value == null) {
            metrics[id].reason = reason;
            metrics[id].sourceFailure = reason;
            if (retryable) metrics[id].retryableFailure = reason;
          }
        // Configuration/non-retryable failures retain the normal TTL too.
        jobCache?.store(ids, metrics, isoDay(end), retryable);
        console.warn(
          JSON.stringify({
            event: "wall_source_failed",
            source,
            metrics: ids,
            reason,
          })
        );
      }
    };
  const activityJob = (
    id: MetricId,
    days: 1 | 7 | 30,
    kind: "active" | "saved" | "assistant"
  ) =>
    guarded([id], "PostHog", async () =>
      fromCounts(
        id,
        days === 30
          ? await periodQueries(
              sources.query,
              (stop) => activityQuery(stop, 30, kind, 1),
              end,
              30,
              2,
              1
            )
          : await sources.query(activityQuery(end, days, kind)),
        end,
        days
      )
    );
  const cohortJob = (maturity: 2 | 7 | 37) =>
    guarded(
      maturity === 2
        ? ["retention.day1_return"]
        : maturity === 7
        ? ["activation.rate", "activation.capture_week1_share"]
        : ["retention.if_activated", "retention.recovery"],
      "PostHog",
      async () => {
        const rows = await periodQueries(
          sources.query,
          (stop, count) => cohortQuery(stop, maturity, count),
          end,
          7
        );
        const stop = shiftDay(end, -maturity);
        if (maturity === 2)
          fromCounts("retention.day1_return", rows, stop, 7, 7, 2);
        if (maturity === 7) {
          fromCounts("activation.rate", rows, stop, 7, 3, 2);
          fromCounts("activation.capture_week1_share", rows, stop, 7, 8, 2);
        }
        if (maturity === 37) {
          fromCounts("retention.if_activated", rows, stop, 7, 4, 3);
          fromCounts("retention.recovery", rows, stop, 7, 6, 5);
        }
      }
    );
  // Headline stats first (the TV's stats and their deltas), then the v2-only
  // tiles, so a cold refresh fills what the wall shows before the rest.
  jobs.push(
    activityJob("growth.wau", 7, "active"),
    activityJob("engagement.dau", 1, "active"),
    activityJob("engagement.mau", 30, "active"),
    cohortJob(7),
    cohortJob(37)
  );
  jobs.push(
    guarded(["retention.established_week"], "PostHog", async () => {
      const stop = completeWeek(now).end;
      fromCounts(
        "retention.established_week",
        await periodQueries(sources.query, establishedQuery, stop, 7),
        stop,
        7,
        3,
        2
      );
    })
  );
  jobs.push(cohortJob(2));
  jobs.push(
    guarded(["growth.true_new_7d"], "PostHog", async () => {
      const rows = await periodQueries(
        sources.query,
        (stop, count) => cohortQuery(stop, 0, count),
        end,
        7
      ); // latest complete 7d; no future query bounds
      fromCounts("growth.true_new_7d", rows, end, 7, 2);
      metrics["growth.true_new_7d"].reason =
        "Interim first-seen proxy, bounded 180-day history; " + COVERAGE_REASON;
    })
  );
  jobs.push(
    activityJob("engagement.saved_creators", 1, "saved"),
    activityJob("engagement.assistant_success", 1, "assistant")
  );
  // At most two PostHog reads at a time, in the order above: a pool, so one
  // slow job never holds the next back. Stripe and Shopify run alongside.
  const queue = [...jobs];
  const posthog = Promise.all(
    [0, 1].map(async () => {
      for (let job = queue.shift(); job; job = queue.shift()) await job();
    })
  ).then(() => {
    // Cohort period labels describe the denominator; dataThrough describes the
    // fully observed outcome cutoff. Keep both rather than aging a mature cohort.
    const cohortIds: MetricId[] = [
      "activation.rate",
      "activation.capture_week1_share",
      "retention.if_activated",
      "retention.recovery",
      "retention.day1_return",
    ];
    for (const id of cohortIds) {
      const m = metrics[id];
      if (m.value != null) {
        m.dataThrough = isoDay(shiftDay(end, -1));
        m.reason = `First-seen cohort ${m.windowStart?.slice(
          0,
          10
        )} to ${m.windowEnd?.slice(0, 10)} (exclusive end); ${m.reason}`;
      }
    }
  });
  const week = completeWeek(now);
  await Promise.allSettled([
    guarded(
      [
        "revenue.hardware_units_week",
        "revenue.hardware_usd_week",
        "revenue.plan_prepay_usd_week",
      ],
      "Shopify",
      async () => {
        const snapshots = await Promise.allSettled(
          [0, 1].map(async (i) =>
            sources.shopify(
              isoDay(shiftDay(week.start, -7 * i)),
              isoDay(shiftDay(week.end, -7 * i))
            )
          )
        );
        if (snapshots[0].status === "rejected") throw snapshots[0].reason;
        for (const [id, key] of [
          ["revenue.hardware_units_week", "units"],
          ["revenue.hardware_usd_week", "hardwareUsd"],
          ["revenue.plan_prepay_usd_week", "prepayUsd"],
        ] as const) {
          const current = snapshots[0],
            previous = snapshots[1];
          const m = metrics[id];

          m.value = current.value[key];
          m.prev = previous.status === "fulfilled" ? previous.value[key] : null;
          stamp(
            m,
            week.start,
            week.end,
            `Shopify net of refunds; USD shop currency; title/SKU mapping proxy (${current.value.unmappedLines} other lines). Platform attribution unavailable. Prepay is cash, never MRR.`
          );
          m.partial = true;
          m.trend = [
            ...(previous.status === "fulfilled"
              ? [{ date: isoDay(shiftDay(week.start, -1)), value: m.prev }]
              : []),
            { date: isoDay(shiftDay(week.end, -1)), value: m.value },
          ];
        }
      }
    )(),
    guarded(["revenue.mrr"], "Stripe", async () => {
      const m = metrics["revenue.mrr"];
      // The FinOps book is the source of truth (David 2026-10-22): coupons
      // applied, annual ÷ 12, trialing $0, refreshed daily by the producer.
      // The live Stripe read stays only as a freshness cross-check — it ignores
      // discounts, so a gap between the two is the coupon effect made visible.
      const finopsSource = sources.finops;
      const [finopsResult, liveResult] = await Promise.allSettled([
        finopsSource
          ? Promise.resolve().then(() => finopsSource(isoDay(now)))
          : Promise.resolve(null),
        Promise.resolve()
          .then(() => sources.stripe())
          .catch((error) => error as Error),
      ]);
      const finops =
        finopsResult.status === "fulfilled" ? finopsResult.value : null;
      const book =
        liveResult.status === "fulfilled" &&
        !(liveResult.value instanceof Error)
          ? liveResult.value
          : null;
      const liveError =
        liveResult.status === "fulfilled" && liveResult.value instanceof Error
          ? liveResult.value
          : finopsResult.status === "rejected"
          ? (finopsResult.reason as Error)
          : null;
      // Latest complete-day book: never today's half-written snapshot.
      const snapshotDays = Object.keys(finops?.mrr || {})
        .filter((day) => day <= isoDay(shiftDay(end, -1)))
        .sort();
      const snap = snapshotDays.at(-1);
      windowFinops = finops;
      if (finops && snap) {
        const plans = finops.mrr[snap];
        const usd = Object.values(plans).reduce((s, v) => s + v, 0);
        const nonUsd = finops.nonUsdPaying[snap] ?? 0;
        m.value = usd;
        m.numerator = usd;
        // Distinct paying customers; the item-based plan sum is only a
        // pre-migration fallback (labelled below).
        const customers = finops.payingCustomers[snap];
        m.denominator = customers ?? (finops.paying[snap] || null);
        m.breakdown = plans;
        // Non-USD payers are counted but their MRR is not in the USD figure.
        m.partial = nonUsd > 0;
        const refreshed = finops.refreshed[snap] ?? null;
        stamp(
          m,
          shiftDay(new Date(`${snap}T00:00:00Z`), 1),
          shiftDay(new Date(`${snap}T00:00:00Z`), 1),
          `FinOps Stripe book snapshot ${snap}: coupons applied, annual ÷ 12, trialing excluded, produced ${
            refreshed?.slice(0, 10) ?? "unknown time"
          }.` +
            (nonUsd
              ? ` ${nonUsd} non-USD paying subscription${
                  nonUsd === 1 ? "" : "s"
                } counted but excluded from MRR (native currency, no implicit FX).`
              : "") +
            (customers == null
              ? " Denominator is the subscription-item sum (table predates paying_customers)."
              : "") +
            (book
              ? ` Live Stripe cross-check $${Math.round(
                  book.usd
                ).toLocaleString("en-US")} (${book.usd >= usd ? "+" : ""}${
                  usd ? ((100 * (book.usd - usd)) / usd).toFixed(1) : "?"
                }%: live read applies no coupons).`
              : " Live Stripe cross-check unavailable."),
          refreshed
        );
        m.dataThrough = `${snap}T00:00:00Z`;
        m.stale = freshness(refreshed, snap, "daily", now).stale;
      } else if (book) {
        m.fixture = book.fixture === true;
        m.value =
          book.usd === 0 &&
          (book.partial ||
            book.unmappedProducts > 0 ||
            book.unsupportedItems > 0)
            ? null
            : book.usd;
        m.partial =
          book.partial ||
          book.unmappedProducts > 0 ||
          book.unsupportedItems > 0;
        if (m.value != null && book.byPlan) m.breakdown = book.byPlan;
        m.status = m.value == null ? "null" : "proxy";
        m.sourceRefreshedAt = new Date().toISOString();
        m.dataThrough = now.toISOString();
        m.stale = false;
        m.reason = `FinOps book unavailable; live renewal run-rate shown instead (no coupon handling): ${
          liveError ? wallFailure("FinOps", liveError) : "no snapshot found"
        }. ${book.unmappedProducts} unmapped product items, ${
          book.unsupportedItems
        } tiered/non-USD items excluded; JPY stays yen, no implicit FX. Shopify cash excluded.`;
        const sameCutoff =
          book.dataThrough === isoDay(shiftDay(end, -1)) &&
          Boolean(book.sourceRefreshedAt);
        if (sameCutoff)
          stamp(
            m,
            shiftDay(end, -1),
            end,
            `${
              book.fixture ? "LOCAL STRIPE FIXTURE · " : ""
            }Omi-plan renewal run-rate snapshot; Shopify cash excluded; USD/approved FX only`,
            book.sourceRefreshedAt
          );
      } else {
        throw (
          liveError || new WallSourceError("Stripe plan book unavailable", true)
        );
      }
    })(),
    // Billing's cost/MAU denominator is a PostHog read: after the pool.
    posthog.then(
      guarded(
        ["cost.net_day", "cost.per_mau_month", "cost.per_customer_month"],
        "Billing",
        async () => {
          const planCostSource = sources.planCost;
          const feesSource = sources.fees;
          const vendorBalanceSource = sources.vendorBalance;
          const modulateSource = sources.modulate;
          const infraSource = sources.infra;
          const [
            billResult,
            planCostResult,
            feesResult,
            vendorBalanceResult,
            modulateResult,
            infraResult,
          ] = await Promise.allSettled([
            Promise.resolve().then(() => sources.billing()),
            planCostSource
              ? Promise.resolve().then(() => planCostSource(isoDay(now)))
              : Promise.resolve(null),
            feesSource
              ? Promise.resolve().then(() => feesSource(isoDay(now)))
              : Promise.resolve(null),
            vendorBalanceSource
              ? Promise.resolve().then(() => vendorBalanceSource(isoDay(now)))
              : Promise.resolve(null),
            modulateSource
              ? Promise.resolve().then(() => modulateSource(isoDay(now)))
              : Promise.resolve(null),
            infraSource
              ? Promise.resolve().then(() => infraSource(isoDay(now)))
              : Promise.resolve(null),
          ]);
          if (billResult.status === "rejected") throw billResult.reason;
          const bill = billResult.value;
          const planCost =
            planCostResult.status === "fulfilled" ? planCostResult.value : null;
          // Fee source unreachable (missing key scope / dark table) is a labelled
          // missing line, never a guess and never a failed cost stack.
          const feesUnavailable =
            feesResult.status === "rejected" ? FEES_UNAVAILABLE_REASON : null;
          // Same contract for the two vendor STT legs: dark tables are labelled
          // missing lines; the stack keeps its labelled fallbacks.
          const sonioxUnavailable =
            vendorBalanceResult.status === "rejected"
              ? SONIOX_UNAVAILABLE_REASON
              : null;
          const modulateUnavailable =
            modulateResult.status === "rejected"
              ? MODULATE_UNAVAILABLE_REASON
              : null;
          // The infra run-rate table is dark until the first Mercury load
          // after it ships: a labelled missing line, same contract as fees.
          const infraUnavailable =
            infraResult.status === "rejected"
              ? "Infra (non-GCP) run rate unavailable (mercury_infra_non_gcp_daily dark)"
              : null;
          const infra =
            infraResult.status === "fulfilled" ? infraResult.value : null;
          const vendorBalance =
            vendorBalanceResult.status === "fulfilled"
              ? vendorBalanceResult.value
              : null;
          // ≥2 snapshots = the derived day-rate series is live (David
          // 2026-10-22); before that the dated console constant stays. The
          // series ends at its last covered day — later days fall back to the
          // dated constant, flagged, never $0 spend or a phantom reset.
          const modulate =
            modulateResult.status === "fulfilled" ? modulateResult.value : null;
          // Source failures (not empty data): the cache keeps the last good cost.
          if (!bill || bill.summary.costSource !== "billing")
            throw new WallSourceError("Settled billing aggregate unavailable");
          const cutoff = isoDay(shiftDay(end, -2));
          // All-in: GCP net of CUD minus one-time incidents, plus OpenAI, the
          // Anthropic API leg only when it reports spend, measured STT vendor
          // lines (Soniox balance deltas + Modulate modelled volume), Mercury
          // SaaS, the Mercury non-GCP infra run rate, and measured Stripe fees.
          const vendor = {
            sttMeasured: planCost?.sttMeasured,
            sonioxBalance: sonioxBalanceInputs(vendorBalance, cutoff),
            modulateModelled: modulate ?? undefined,
            sttCash: planCost?.sttCash,
            saasMeasured: planCost?.saasMeasured,
            infraMeasured: infra?.infraMeasured,
            infraAnnualPartial: infra?.infraAnnualPartial,
            infraStripeFeesCash: infra?.infraStripeFeesCash,
            stripeFees:
              feesResult.status === "fulfilled"
                ? feesResult.value?.fees
                : undefined,
          };
          const cost = allInCost(
            bill.daily.filter((d) => d.date <= cutoff),
            bill.summary.coverage,
            vendor,
            feesUnavailable
          );
          const daily = cost.daily;
          const last = daily.find((d) => d.date === cutoff);
          if (!last)
            throw new WallSourceError(`Billing data has not reached ${cutoff}`);
          const staleEstimate = (
            { stale }: { stale: boolean },
            label: string
          ) => (stale ? `${label} STALE` : label);
          // A balance series that no longer covers the cutoff day means the
          // STT constant is back in use: stale NOW, not once it ages out.
          const sonioxBroken = sonioxSeriesBroken(vendor, last.date);
          const sttEstimate = estimateStatus(
            now,
            { STT: last.sttMeasured },
            { STT: sonioxBroken && !last.sttMeasured }
          ).find((e) => e.line === "STT")!;
          const missingLines = [...cost.missing];
          if (sonioxUnavailable) missingLines.push("Soniox measured STT");
          if (modulateUnavailable) missingLines.push("Modulate modelled STT");
          if (infraUnavailable) missingLines.push(infraUnavailable);
          // Soniox: the balance-delta day-rate while the snapshot series covers
          // the day; a covered-but-unpublished row is a disclosed gap, never a
          // reset; beyond the last covered day the dated constant returns with
          // the break stated. `baseline_reset` stays reserved for an actual
          // lower cumulative balance (the producer's null-usd row).
          const bal = vendor.sonioxBalance;
          const sonioxUsage = vendor.sttMeasured?.[last.date]?.soniox;
          const covered =
            !!bal &&
            bal.ready &&
            last.date >= bal.firstDay &&
            last.date <= bal.lastDay;
          const sonioxText =
            bal && vendorBalance
              ? covered
                ? last.sttFlag === "baseline_reset"
                  ? `Soniox balance reset on ${last.date}: day unmeasured, new baseline taken; the dated estimate covers the day, never $0`
                  : last.sttFlag === SONIOX_GAP_FLAG
                  ? `Soniox ${last.date}: no published spend row (snapshot gap) — unmeasured, the dated estimate covers the day, never $0 or a reset`
                  : `Soniox measured $${last.sttSonioxUsd.toFixed(
                      2
                    )}/day (prepaid-balance Δ, as-of ${
                      vendorBalance.asOf ?? "?"
                    })${
                      last.sttFlag === "gap_spread"
                        ? ", gap-spread estimate over a missed run"
                        : ""
                    }`
                : bal.ready
                ? staleEstimate(
                    sttEstimate,
                    `Soniox balance series does not cover ${
                      last.date
                    } (last covered day ${bal.lastDay}, as-of ${
                      vendorBalance.asOf ?? "?"
                    }): the day shows the dated console constant, not $0 spend`
                  )
                : staleEstimate(
                    sttEstimate,
                    `Soniox-console constant $${STT_MONTHLY_USD}/mo (${STT_SOURCE}); ${vendorBalance.snapshots}/2 balance snapshots`
                  )
              : !vendorBalance && sonioxUnavailable
              ? `Soniox measured line UNAVAILABLE (${sonioxUnavailable})`
              : sonioxUsage != null
              ? `Soniox measured $${sonioxUsage.toFixed(
                  2
                )}/day (usage-summary line; balance series not live yet)`
              : staleEstimate(
                  sttEstimate,
                  `Soniox-console constant $${STT_MONTHLY_USD}/mo (${STT_SOURCE}); ${
                    vendorBalance
                      ? `${vendorBalance.snapshots}/2 balance snapshots`
                      : "no balance series"
                  }`
                );
          // Deepgram combines independently: its measured usage or its own
          // Mercury cash, never hidden by a Soniox measurement.
          const deepgramText = last.sttDeepgramUsd
            ? `; Deepgram ${
                last.sttDeepgramMeasured ? "measured" : "Mercury cash"
              } $${last.sttDeepgramUsd.toFixed(2)}/day`
            : "";
          // Modulate: modelled volume × committed price when present; Mercury
          // cash is the labelled fallback and always the monthly cross-check.
          const recon = modulateReconciliation(
            modulate ?? undefined,
            planCost?.sttCash,
            cutoff
          );
          const modulateText = last.sttModulateModelled
            ? `Modulate modelled $${last.sttModulateUsd.toFixed(
                2
              )}/day (measured volume × $${modulate?.price}/h, price as-of ${
                modulate?.priceAsOf
              })`
            : `Modulate Mercury cash${
                last.sttModulateUsd
                  ? ` $${last.sttModulateUsd.toFixed(2)}/day`
                  : ""
              }${
                modulateUnavailable
                  ? " (modelled line unavailable)"
                  : modulate
                  ? " (modelled line has no row for the day)"
                  : ""
              }`;
          const reconText = recon
            ? ` Modulate 30d reconciliation: modelled $${Math.round(
                recon.modelledUsd
              ).toLocaleString("en-US")} vs Mercury cash $${Math.round(
                recon.cashUsd
              ).toLocaleString("en-US")} (${
                recon.variancePct == null
                  ? "modelled $0"
                  : `${
                      recon.variancePct >= 0 ? "+" : ""
                    }${recon.variancePct.toFixed(1)}%`
              }).`
            : "";
          const sttLine = `STT ${sonioxText}${deepgramText}; ${modulateText}${reconText}`;
          const annualPartial = planCost?.saasAnnualPartial?.[last.date];
          // The run rate stays measured while history is short, but it may not
          // be called complete: label the partial with the producer's reason.
          const saasPartialNote =
            annualPartial === "history_under_12_months"
              ? " (partial: SaaS ledger history under 12 months; one-off vendors amortized ÷12, estimated)"
              : annualPartial
              ? ` (partial: ${annualPartial})`
              : "";
          const saasLine = last.saasMeasured
            ? `measured SaaS (Mercury) $${last.saas.toFixed(
                2
              )}/day${saasPartialNote}`
            : `SaaS fixed $${SAAS_MONTHLY_USD}/mo estimate as of ${SAAS_AS_OF} (${
                planCostResult.status === "rejected"
                  ? "Mercury feed unavailable"
                  : "no complete fresh Mercury row"
              })`;
          // Infra (non-GCP): Modal/AWS/Runpod-class cash. GCP (billing
          // export), STT vendors and measured Stripe fees are their own lines
          // and never enter here. A partial run rate is a floor (annual bills
          // before the ledger start are invisible to it), so the dated
          // constant wins while it is higher — labelled, still partial — and
          // the constant's age then counts against the line again.
          const infraPartialNote =
            last.infraPartial === "history_under_12_months"
              ? " (partial: infra ledger history under 12 months; one-off vendors amortized ÷12, estimated)"
              : last.infraPartial
              ? ` (partial: ${last.infraPartial})`
              : "";
          // Mercury stripe_fees cash rejoins infra only when the measured fee
          // line has no value for the day: never on both lines, never on neither.
          const infraFeesNote = last.infraFeesCash
            ? ` + Mercury stripe_fees cash $${last.infraFeesCash.toFixed(
                2
              )}/day counted here (measured Stripe fee line unavailable for the day)`
            : "";
          const infraEstimate = estimateStatus(now, {
            Infra: last.infraMeasured && !last.infraFloored,
          }).find((e) => e.line === "Infra")!;
          const infraBaseUsd = last.infra - last.infraFeesCash;
          const infraLine = !last.infraMeasured
            ? staleEstimate(
                infraEstimate,
                `Infra (non-GCP) fixed $${INFRA_MONTHLY_USD}/mo estimate as of ${INFRA_AS_OF} (${
                  infraUnavailable
                    ? "Mercury infra run-rate table unavailable"
                    : "no complete fresh Mercury infra row"
                })`
              )
            : last.infraFloored
            ? staleEstimate(
                infraEstimate,
                `Infra (non-GCP) $${infraBaseUsd.toFixed(
                  2
                )}/day: dated $${INFRA_MONTHLY_USD}/mo fallback as of ${INFRA_AS_OF} floors the partial Mercury run rate $${(
                  last.infraMeasuredUsd ?? 0
                ).toFixed(2)}/day${infraPartialNote}${infraFeesNote}`
              )
            : `measured Infra non-GCP (Mercury) $${infraBaseUsd.toFixed(
                2
              )}/day${infraPartialNote}${infraFeesNote}`;
          // Foreign-currency fee rows sit in a non-USD balance and carry no
          // conversion data: counted here so the USD figure is labelled partial
          // instead of silently complete.
          const feesForeign =
            feesResult.status === "fulfilled" && feesResult.value
              ? Object.entries(feesResult.value.foreign)
                  .filter(
                    ([day]) => day <= cutoff && day > isoDay(shiftDay(end, -32))
                  )
                  .reduce((s, [, n]) => s + n, 0)
              : 0;
          const feesLine =
            last.fees != null
              ? `measured Stripe fees $${last.fees.toFixed(2)}/day${
                  feesForeign
                    ? ` (partial: ${feesForeign} foreign-currency fee rows in the 30d window counted, not converted)`
                    : ""
                }`
              : `Stripe fees UNAVAILABLE (finops key lacks balance-transaction read scope)${
                  last.infraFeesCash
                    ? "; Mercury stripe_fees cash counted on the infra line"
                    : ""
                }`;
          const anthropicLine =
            last.anthropic != null && last.anthropic > 0
              ? ` + Anthropic $${last.anthropic.toFixed(2)}`
              : last.anthropic != null
              ? " + Anthropic $0 API (team seats are SaaS cash)"
              : " + Anthropic API leg not configured (team seats are SaaS cash)";
          const lines = `All-in: GCP net of committed-use credits, one-time incidents excluded, + OpenAI${anthropicLine} + ${sttLine} + ${saasLine} + ${infraLine} + ${feesLine}${
            missingLines.length ? `; missing: ${missingLines.join(", ")}` : ""
          }`;
          const m = metrics["cost.net_day"];
          m.value = last.total;
          m.prev =
            daily.find((d) => d.date === isoDay(shiftDay(end, -3)))?.total ??
            null;
          m.partial = true;
          stamp(
            m,
            shiftDay(end, -2),
            shiftDay(end, -1),
            lines,
            new Date(bill.generatedAt).toISOString()
          );
          m.stale = freshness(
            m.sourceRefreshedAt,
            m.dataThrough,
            "settled",
            now
          ).stale;
          m.trend = daily
            .slice(-14)
            .map((d) => ({ date: d.date, value: d.total }));
          const window = completeWindow(30, now, 1); // ends D-1 exclusive, D-2 inclusive
          const costs = daily.filter(
            (d) => d.date >= isoDay(window.start) && d.date < isoDay(window.end)
          );
          if (new Set(costs.map((d) => d.date)).size !== 30) {
            metrics["cost.per_mau_month"].reason =
              "Billing window missing settled days";
            metrics["cost.per_customer_month"].reason =
              "Billing window missing settled days";
            return;
          }
          // Software cost per paying customer shares the cost numerator with
          // cost/MAU; the denominator comes from the FinOps book (derived block).
          const windowTotal = costs.reduce((s, d) => s + d.total, 0);
          metrics["cost.per_mau_month"].numerator = windowTotal;
          metrics["cost.per_customer_month"].numerator = windowTotal;
          windowPlans = planCost;
          const rows = await sources.query(
            activityQuery(window.end, 30, "active", 1)
          );
          const mau = rows
            .filter((r) => Number(r[0]) === 0)
            .reduce((s, r) => s + Number(r[2]), 0);
          const c = metrics["cost.per_mau_month"];
          if (!mau) {
            c.reason = "Zero same-window MAU denominator";
            return;
          }
          c.definitionVersion = MCP_ACTIVITY_VERSION;
          c.value = windowTotal / mau;
          c.numerator = windowTotal;
          c.denominator = mau;
          c.partial = true;
          stamp(
            c,
            window.start,
            window.end,
            "Same-window 30-day all-in cost / qualified MAU. " +
              lines +
              "; " +
              COVERAGE_REASON,
            new Date(bill.generatedAt).toISOString()
          );
          c.sourceRefreshedAt = rows.sourceRefreshedAt
            ? [
                new Date(bill.generatedAt).toISOString(),
                rows.sourceRefreshedAt,
              ].sort()[0]
            : null;
          c.stale = freshness(
            c.sourceRefreshedAt,
            c.dataThrough,
            "settled",
            now
          ).stale;
        }
      )
    ),
  ]);
  // Derived units recompute from reused source snapshots without querying Stripe
  // again when only MAU needs retrying (or vice versa).
  {
    const a = metrics["revenue.arpmau"];
    const m = metrics["revenue.mrr"];
    const mau = metrics["engagement.mau"];
    const sameCutoff =
      m.dataThrough === isoDay(shiftDay(end, -1)) &&
      Boolean(m.sourceRefreshedAt);
    if (mau.value && m.value != null) {
      a.fixture = m.fixture === true;
      a.value = m.value / mau.value;
      a.numerator = m.value;
      a.denominator = mau.value;
      a.partial = m.partial || mau.partial || !sameCutoff;
      a.materialGap = !sameCutoff;
      stamp(
        a,
        shiftDay(end, -30),
        end,
        `${m.fixture ? "LOCAL STRIPE FIXTURE numerator · " : ""}${
          sameCutoff
            ? "Same-cutoff Omi-plan MRR / qualified MAU. "
            : `Live MRR / completed MAU through ${isoDay(
                shiftDay(end, -1)
              )}; cutoff mismatch, not the contract same-cutoff close. `
        }${COVERAGE_REASON}`,
        mau.sourceRefreshedAt && m.sourceRefreshedAt
          ? [m.sourceRefreshedAt, mau.sourceRefreshedAt].sort()[0]
          : null
      );
      a.definitionVersion = mau.definitionVersion;
      a.stale = m.stale || mau.stale;
    } else {
      a.reason =
        mau.value == null || mau.value === 0
          ? `ARPMAU requires qualified MAU: ${mau.reason}`
          : `ARPMAU requires MRR: ${m.reason}`;
    }
    if (m.retryableFailure || mau.retryableFailure)
      a.retryableFailure = m.retryableFailure || mau.retryableFailure;
    if (a.value == null && (m.sourceFailure || mau.sourceFailure))
      a.sourceFailure = m.sourceFailure || mau.sourceFailure;
  }
  // Software cost per paying customer (David 2026-10-22): the same 30-day
  // all-in software cost as cost/MAU, over a payer count measured over the
  // SAME window as the cost — the average of daily paying customers from the
  // FinOps book, stated; the window-end snapshot count and the item-based sum
  // (pre-migration) are labelled fallbacks. The breakdown exposes per-plan
  // variable cost (FinOps `variable_total` ÷ cost-active user-days × 30.44)
  // when the window has it.
  {
    const p = metrics["cost.per_customer_month"];
    const m = metrics["revenue.mrr"];
    const perMau = metrics["cost.per_mau_month"];
    const window = completeWindow(30, now, 1);
    // Assigned inside the Billing/Stripe callbacks above (like windowPlans).
    const book = windowFinops as FinopsHistory | null;
    let paying: number | null = null;
    let basis = "";
    if (book) {
      const inWindow = Object.keys(book.payingCustomers)
        .filter((d) => d >= isoDay(window.start) && d < isoDay(window.end))
        .sort();
      if (inWindow.length) {
        paying =
          inWindow.reduce((s, d) => s + book.payingCustomers[d], 0) /
          inWindow.length;
        basis = `denominator = average of ${inWindow.length} daily paying-customer snapshots inside the window`;
      } else {
        // No snapshot inside the window: the window-end count (the book's own
        // latest day, at or before the window's exclusive end), stated.
        const snaps = Object.keys(book.payingCustomers)
          .filter((d) => d <= isoDay(window.end))
          .sort();
        const snap = snaps.at(-1);
        if (snap) {
          paying = book.payingCustomers[snap];
          basis = `denominator = window-end paying-customer snapshot ${snap}`;
        }
      }
    }
    if (paying == null && m.denominator) {
      paying = m.denominator;
      basis =
        "denominator = subscription-item sum (book predates the paying-customers column)";
    }
    if (p.numerator != null && paying) {
      p.value = p.numerator / paying;
      p.denominator = paying;
      p.partial = perMau.partial || m.partial;
      // Variable $/customer/month per plan over the same cost window.
      const planWindow = windowPlans as PlanCostHistory | null;
      if (planWindow) {
        const window = completeWindow(30, now, 1);
        const varUsd: Record<string, number> = {};
        const varUsers: Record<string, number> = {};
        for (const day of Object.keys(planWindow.plans)) {
          if (day < isoDay(window.start) || day >= isoDay(window.end)) continue;
          for (const [plan, row] of Object.entries(planWindow.plans[day])) {
            varUsd[plan] = (varUsd[plan] || 0) + row.varUsd;
            varUsers[plan] = (varUsers[plan] || 0) + row.varUsers;
          }
        }
        const plans = Object.fromEntries(
          Object.entries(varUsers)
            .filter(([, users]) => users > 0)
            .map(([plan, users]) => [plan, (varUsd[plan] / users) * 30.4375])
        );
        if (Object.keys(plans).length) p.breakdown = plans;
      }
      stamp(
        p,
        perMau.windowStart ? new Date(perMau.windowStart) : shiftDay(end, -31),
        perMau.windowEnd ? new Date(perMau.windowEnd) : end,
        `Same-window 30-day all-in software cost / paying customers (${basis}; FinOps book${
          m.dataThrough ? ` through ${String(m.dataThrough).slice(0, 10)}` : ""
        }). ${perMau.reason ?? ""}${
          p.breakdown
            ? ` Per-plan breakdown: variable cost per customer/month.`
            : ""
        }`,
        m.sourceRefreshedAt
      );
      p.stale = perMau.stale || m.stale;
    } else {
      p.reason = paying
        ? `Cost numerator unavailable: ${perMau.reason}`
        : `Paying-customer book unavailable: ${m.reason}`;
    }
    if (p.value == null && (m.sourceFailure || perMau.sourceFailure))
      p.sourceFailure = m.sourceFailure || perMau.sourceFailure;
  }
  const list = WALL_DEFINITIONS.map(([id]) => metrics[id]);
  return {
    definitionVersion: DEFINITION_VERSION,
    retryableFailures,
    ...(jobCache ? { sourceRefreshAfter: jobCache.nextRefreshAt() } : {}),
    generatedAt: new Date().toISOString(),
    metrics: list,
    partial: list.some((m) => m.status === "null" || m.partial),
  };
}
export type WallPayload = Awaited<ReturnType<typeof computeWall>> & {
  refreshing?: boolean;
  cacheStale?: boolean;
  refreshError?: string;
};
