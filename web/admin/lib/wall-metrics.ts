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
} from "./wall-posthog";
import { fetchShopifyWeek } from "./wall-shopify";

export const WALL_DEFINITIONS = [
  ["growth.wau", "WAU", "people", "Growth"],
  ["growth.true_new_7d", "Interim true-new", "people", "Growth"],
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
  ["cost.net_day", "Settled net cost", "USD/day", "Health"],
  ["cost.per_mau_month", "Cost / MAU", "USD/person/30d", "Health"],
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
}
export interface Metric {
  id: MetricId;
  label: string;
  column: string;
  value: number | null;
  prev: number | null;
  unit: string;
  split: Split;
  numerator: number | null;
  denominator: number | null;
  splitCounts: Record<
    keyof Split,
    { numerator: number; denominator: number }
  > | null;
  fixture?: boolean;
  materialGap?: boolean;
  status: "exact" | "proxy" | "null";
  reason: string | null;
  dataThrough: string | null;
  sourceRefreshedAt: string | null;
  definitionVersion: string;
  stale: boolean;
  partial: boolean;
  windowStart: string | null;
  windowEnd: string | null;
  trend: { date: string; value: number | null }[];
}
const emptySplit = (): Split => ({ macos: null, mobile: null, other: null });
const bucket = (p: unknown): keyof Split =>
  p === "macos" ? "macos" : p === "ios" || p === "android" ? "mobile" : "other";
export interface WallSources {
  query: Query;
  shopify: typeof fetchShopifyWeek;
  stripe: () => Promise<{
    usd: number;
    partial: boolean;
    unmappedProducts: number;
    unsupportedItems: number;
    fixture?: boolean;
    dataThrough?: string;
    sourceRefreshedAt?: string;
  }>;
  billing: () => Promise<{
    daily: { date: string; total: number }[];
    generatedAt: number;
    summary: { costSource?: string; partial: boolean; windowEnd?: string };
  } | null>;
}
export const defaultWallSources: WallSources = {
  query: queryPosthog,
  shopify: fetchShopifyWeek,
  stripe: async () => {
    const { getOptionalStripe } = await import("./stripe");
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
    const stripe = getOptionalStripe();
    if (!stripe) throw new Error("Stripe restricted read key unavailable");
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
  "revenue.activated_paid_30d":
    "Signup/person/billing identity join unavailable",
  "revenue.payer_churn":
    "Complete-month distinct-payer snapshots and effective lapse history unavailable",
  "cost.gross_margin_pct":
    "Recognized subscription revenue, variable cost, STT and fee coverage unavailable; 60% is a goal",
  "health.crash_free":
    "Crash reporting coverage unverified; zero crash events cannot prove 100% crash-free",
  "health.thumbs_positive":
    "Message creation/vote aggregate source unavailable",
};
export async function computeWall(
  sources: WallSources = defaultWallSources,
  now = new Date()
) {
  const metrics = Object.fromEntries(
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
        reason: NULL_REASONS[id] || "Source unavailable",
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
    for (let period = 5; period >= 0; period--) {
      const subset = rows.filter((r) => Number(r[0]) === period);
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
      m.trend.push({ date: isoDay(shiftDay(stop, -days * period - 1)), value });
      if (period === 1) m.prev = value;
      if (period !== 0) continue;
      m.value = value;
      m.numerator = num;
      m.denominator = den;
      const counts = {
        macos: { numerator: 0, denominator: 0 },
        mobile: { numerator: 0, denominator: 0 },
        other: { numerator: 0, denominator: 0 },
      };
      for (const r of subset) {
        const b = counts[bucket(r[1])];
        b.numerator += Number(r[numeratorIndex]);
        b.denominator +=
          denominatorIndex == null ? 0 : Number(r[denominatorIndex]);
      }
      m.splitCounts = counts;
      for (const key of ["macos", "mobile", "other"] as const)
        m.split[key] =
          den == null
            ? counts[key].numerator
            : counts[key].denominator
            ? (100 * counts[key].numerator) / counts[key].denominator
            : null;
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
    if (m.value == null)
      m.reason = "Zero cohort denominator; " + COVERAGE_REASON;
  }
  const jobs: (() => Promise<void>)[] = [];
  for (const [id, days, kind] of [
    ["growth.wau", 7, "active"],
    ["engagement.dau", 1, "active"],
    ["engagement.mau", 30, "active"],
    ["engagement.saved_creators", 1, "saved"],
    ["engagement.assistant_success", 1, "assistant"],
  ] as const)
    jobs.push(async () =>
      fromCounts(
        id,
        await sources.query(
          activityQuery(end, days, kind, days === 30 ? 2 : 6)
        ),
        end,
        days
      )
    );
  for (const maturity of [2, 7, 37] as const)
    jobs.push(async () => {
      const rows = await sources.query(cohortQuery(end, maturity));
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
    });
  jobs.push(async () => {
    const rows = await sources.query(cohortQuery(end, 0)); // latest complete 7d; no future query bounds
    fromCounts("growth.true_new_7d", rows, end, 7, 2);
    metrics["growth.true_new_7d"].reason =
      "Interim first-seen proxy, bounded 180-day history; " + COVERAGE_REASON;
  });
  jobs.push(async () => {
    const stop = completeWeek(now).end;
    fromCounts(
      "retention.established_week",
      await sources.query(establishedQuery(stop)),
      stop,
      7,
      3,
      2
    );
  });
  // Bound PostHog concurrency to avoid flooding the query service.
  for (let i = 0; i < jobs.length; i += 2)
    await Promise.allSettled(jobs.slice(i, i + 2).map((job) => job()));
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
  const week = completeWeek(now);
  await Promise.allSettled([
    (async () => {
      const snapshots = await Promise.allSettled(
        [0, 1].map(async (i) =>
          sources.shopify(
            isoDay(shiftDay(week.start, -7 * i)),
            isoDay(shiftDay(week.end, -7 * i))
          )
        )
      );
      for (const [id, key] of [
        ["revenue.hardware_units_week", "units"],
        ["revenue.hardware_usd_week", "hardwareUsd"],
        ["revenue.plan_prepay_usd_week", "prepayUsd"],
      ] as const) {
        const current = snapshots[0],
          previous = snapshots[1];
        const m = metrics[id];
        if (current.status !== "fulfilled") {
          m.reason =
            "Shopify orders unavailable; read_orders and complete pagination required";
          continue;
        }
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
    })(),
    (async () => {
      const book = await sources.stripe();
      const m = metrics["revenue.mrr"];
      m.fixture = book.fixture === true;
      m.value =
        book.usd === 0 &&
        (book.partial || book.unmappedProducts > 0 || book.unsupportedItems > 0)
          ? null
          : book.usd;
      m.partial =
        book.partial || book.unmappedProducts > 0 || book.unsupportedItems > 0;
      // Live Stripe is today's book. Never pretend it is a historical complete-day close.
      m.status = m.value == null ? "null" : "proxy";
      m.sourceRefreshedAt = new Date().toISOString();
      m.dataThrough = now.toISOString();
      m.stale = false;
      m.reason = `Live renewal run-rate, not a complete-period snapshot; prior/trend unavailable. ${book.unmappedProducts} unmapped product items, ${book.unsupportedItems} tiered/non-USD items excluded; JPY stays yen, no implicit FX. Shopify cash excluded.`;
      const a = metrics["revenue.arpmau"];
      a.reason =
        "MRR snapshot at the qualified-MAU cutoff unavailable; live Stripe book is not a same-cutoff numerator";
      if (
        book.dataThrough === isoDay(shiftDay(end, -1)) &&
        book.sourceRefreshedAt
      ) {
        stamp(
          m,
          shiftDay(end, -1),
          end,
          `${
            book.fixture ? "LOCAL STRIPE FIXTURE · " : ""
          }Omi-plan renewal run-rate snapshot; Shopify cash excluded; USD/approved FX only`,
          book.sourceRefreshedAt
        );
        const mau = metrics["engagement.mau"];
        if (mau.value && m.value != null && !m.partial) {
          a.fixture = book.fixture === true;
          a.value = book.usd / mau.value;
          a.denominator = mau.value;
          stamp(
            a,
            shiftDay(end, -30),
            end,
            `${
              book.fixture ? "LOCAL STRIPE FIXTURE numerator · " : ""
            }Same-cutoff Omi-plan MRR / qualified MAU. ${COVERAGE_REASON}`,
            book.sourceRefreshedAt
          );
          a.sourceRefreshedAt = mau.sourceRefreshedAt
            ? [book.sourceRefreshedAt, mau.sourceRefreshedAt].sort()[0]
            : null;
          a.stale = m.stale || mau.stale;
        }
      }
    })(),
    (async () => {
      const bill = await sources.billing();
      if (!bill || bill.summary.costSource !== "billing") return;
      const cutoff = isoDay(shiftDay(end, -2));
      const daily = bill.daily
        .filter((d) => d.date <= cutoff)
        .sort((a, b) => a.date.localeCompare(b.date));
      const last = daily.find((d) => d.date === cutoff);
      if (!last) return;
      const m = metrics["cost.net_day"];
      m.value = last.total;
      m.prev =
        daily.find((d) => d.date === isoDay(shiftDay(end, -3)))?.total ?? null;
      m.partial = true;
      stamp(
        m,
        shiftDay(end, -2),
        shiftDay(end, -1),
        "Billing mode net credits; provider/STT coverage partial; allocation unavailable",
        new Date(bill.generatedAt).toISOString()
      );
      m.stale = freshness(
        m.sourceRefreshedAt,
        m.dataThrough,
        "settled",
        now
      ).stale;
      m.trend = daily.slice(-14).map((d) => ({ date: d.date, value: d.total }));
      const window = completeWindow(30, now, 1); // ends D-1 exclusive, D-2 inclusive
      const costs = daily.filter(
        (d) => d.date >= isoDay(window.start) && d.date < isoDay(window.end)
      );
      if (new Set(costs.map((d) => d.date)).size !== 30) return;
      const rows = await sources.query(
        activityQuery(window.end, 30, "active", 2)
      );
      const mau = rows
        .filter((r) => Number(r[0]) === 0)
        .reduce((s, r) => s + Number(r[2]), 0);
      const c = metrics["cost.per_mau_month"];
      if (!mau) {
        c.reason = "Zero same-window MAU denominator";
        return;
      }
      c.value = costs.reduce((s, d) => s + d.total, 0) / mau;
      c.denominator = mau;
      c.partial = true;
      stamp(
        c,
        window.start,
        window.end,
        "Same-window settled 30d billed cost / qualified MAU; provider/STT coverage partial; " +
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
    })(),
  ]);
  const list = WALL_DEFINITIONS.map(([id]) => metrics[id]);
  return {
    definitionVersion: DEFINITION_VERSION,
    generatedAt: new Date().toISOString(),
    metrics: list,
    partial: list.some((m) => m.status === "null" || m.partial),
  };
}
export type WallPayload = Awaited<ReturnType<typeof computeWall>>;
