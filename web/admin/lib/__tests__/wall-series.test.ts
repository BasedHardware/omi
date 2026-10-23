import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computeWall, WallPayload, WallSources } from "../wall-metrics";
import {
  assembleSeries,
  BAD_MARK,
  COHORT_WEEKS,
  CURVE_MARK,
  GOOD_MARK,
  headlineDelta,
  GROWTH_WEEKS,
  MARGIN_PLANS,
  resetSeriesCache,
  Row,
  SeriesName,
  seriesPayload,
  SeriesSources,
  STORE_FAIL_LIMIT,
  UNIT_DAYS,
} from "../wall-series";
import { resetWallCache, wallPayload } from "../wall-cache";
import {
  LEASE_MS,
  memorySeriesStore,
  mergeLegDoc,
  readThroughStore,
  SeriesStore,
} from "../wall-series-store";
import { isoDay, shiftDay, utcDay } from "../qualified-activity";
import { INFRA_AS_OF, INFRA_MONTHLY_USD } from "../wall-cost";
import { HEALTH_COST_DAYS } from "../wall-finops";

const now = new Date("2026-10-15T12:00Z");
const end = utcDay(now);
// 26 periods are read; those starting before mobile telemetry (2026-05-04) are hidden.
const VISIBLE_WEEKS = 23;
const stamp = (rows: unknown[][]) =>
  Object.assign(rows, { sourceRefreshedAt: now.toISOString() });

/** One synthetic population, answered in each query's own row shape. */
async function query(sql: string) {
  if (sql.includes("__churned"))
    return stamp([
      [0, "macos", 12, 30, 5, 3],
      [0, "ios", 20, 60, 9, 6],
      [0, "integrations", 2, 2, 1, 0],
      [0, "__churned", 7, 0, 0, 0],
      [0, "__days_1", 20, 0, 0, 0],
      [0, "__days_7", 14, 0, 0, 0],
    ]);
  if (sql.includes("spans")) {
    // Every daily offset the query asks for.
    const offsets = /ARRAY JOIN \[([\d,]+)\]/.exec(sql)![1].split(",");
    return stamp(offsets.map((o) => [Number(o), 1000 - Number(o)]));
  }
  if (sql.includes("active_weeks"))
    return stamp([
      [0, 0, 100, 60],
      [0, 1, 80, 30],
      [1, 0, 120, 70],
    ]);
  if (sql.includes("denominator,countIf"))
    return stamp(
      [0, 1].flatMap((p) => [
        [p, "macos", 10, 4, 2, 6, 1, 3, 5],
        [p, "ios", 20, 2, 1, 18, 3, 4, 6],
      ])
    );
  if (sql.includes("countIf(eligible)"))
    return stamp([0, 1].map((p) => [p, "macos", 10, 7]));
  if (sql.includes("'No capture') segment"))
    return stamp([
      ["Omi pendant", 8, 6],
      ["Phone mic only", 12, 5],
      ["No capture", 10, 1],
      ["Limitless", 0, 0],
    ]);
  if (sql.includes("marker_rows"))
    return stamp(
      [0, 1, 2, 3, 4, 5].flatMap((p) => [
        [p, "macos", 12, 9],
        [p, "ios", 20, 9],
        [p, "integrations", 2, 9],
      ])
    );
  return stamp([[0, "macos", 3]]);
}
const billingDays = Array.from({ length: 90 }, (_, i) => ({
  date: isoDay(shiftDay(end, -91 + i)),
  total: 100 + i,
  components: { gcpInfra: 60, vertexLlm: 20 + i, openai: 10, anthropic: 10 },
}));
const billing = async () => ({
  daily: billingDays,
  generatedAt: now.getTime(),
  summary: { costSource: "billing", partial: true },
});
const shopify = async () => ({
  units: 7,
  hardwareUsd: 700,
  prepayUsd: 50,
  unmappedLines: 0,
});
const finopsMrr = Object.fromEntries(
  Array.from({ length: 40 }, (_, i) => [
    isoDay(shiftDay(end, -40 + i)),
    { unlimited: 500 + i, plus: 400 },
  ])
);
const finopsHistory = {
  mrr: finopsMrr,
  paying: Object.fromEntries(Object.keys(finopsMrr).map((day) => [day, 1_500])),
  payingCustomers: Object.fromEntries(
    Object.keys(finopsMrr).map((day) => [day, 1_480])
  ),
  nonUsdPaying: Object.fromEntries(
    Object.keys(finopsMrr).map((day) => [day, 0])
  ),
  refreshed: Object.fromEntries(
    Object.keys(finopsMrr).map((day) => [day, `${day}T14:36:00Z`])
  ),
};
function sources(): SeriesSources & WallSources {
  return {
    query: vi.fn(query),
    shopify: vi.fn(shopify),
    billing: vi.fn(billing),
    stripe: async () => ({
      usd: 1000,
      byPlan: { unlimited: 600, plus: 400 },
      partial: false,
      unmappedProducts: 0,
      unsupportedItems: 0,
    }),
    finops: vi.fn(async () => finopsHistory),
    planCost: vi.fn(async () => ({
      plans: {},
      sttMeasured: {},
      saasMeasured: {},
      saasAnnualPartial: {},
      sttCash: {},
    })),
    fees: vi.fn(async () => ({ fees: {}, foreign: {} })),
  };
}
const value = (wall: WallPayload, id: string) =>
  wall.metrics.find((m) => m.id === id)!;
async function all(snapshot: WallPayload | null, s = sources()) {
  const out = {} as Record<SeriesName, Record<string, Row[]>>;
  for (const name of [
    "headline",
    "growth",
    "activation",
    "retention",
    "revenue",
    "health",
  ] as const)
    out[name] = (
      await seriesPayload(name, Promise.resolve(snapshot), now, s)
    ).frames;
  return out;
}

beforeEach(() => {
  resetSeriesCache();
  resetWallCache();
});
afterEach(() => vi.useRealTimers());

describe("v3 series agree with the v2 snapshot", () => {
  it("capture-source segments cover the activation cohort", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const rate = value(wall, "activation.rate");
    const rows = f.activation.sources;
    // Largest group first.
    expect(rows.map((r) => r.source)).toEqual([
      "Phone mic · 12",
      "No capture · 10",
      "Omi pendant · 8",
    ]);
    expect(rows.reduce((n, r) => n + Number(r.people), 0)).toBe(
      rate.denominator
    );
    expect(rows.at(-1)?.activation).toBe(75);
  });

  it("every chart's latest point is the stat above it", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const wau = value(wall, "growth.wau");
    expect(f.growth.weekly.at(-1)).toMatchObject({
      date: `${isoDay(shiftDay(end, -1))}T00:00:00Z`,
      total: wau.value,
      macos: wau.split.macos,
      mobile: wau.split.mobile,
      other: wau.split.other,
      mcp: wau.split.mcp,
    });
    expect(f.activation.activation.at(-1)?.total).toBe(
      value(wall, "activation.rate").value
    );
    expect(f.activation.capture.at(-1)?.total).toBe(
      value(wall, "activation.capture_week1_share").value
    );
    expect(f.retention.established.at(-1)?.total).toBeCloseTo(
      value(wall, "retention.established_week").value!,
      1
    );
    expect(f.retention.retained.at(-1)?.total).toBeCloseTo(
      value(wall, "retention.if_activated").value!,
      1
    );
    // The stat is the FinOps book now; the chart's last point is that book's
    // snapshot day, not a live-read point.
    expect(f.revenue.mrr.at(-1)).toMatchObject({
      total: value(wall, "revenue.mrr").value,
      unlimited: finopsMrr[isoDay(shiftDay(end, -1))].unlimited,
      plus: 400,
      source: "FinOps book",
    });
    expect(f.revenue.arpmau.at(-1)?.arpmau).toBeCloseTo(
      value(wall, "revenue.arpmau").value!,
      2
    );
    expect(f.revenue.hardware.at(-1)?.hardwareUsd).toBe(
      value(wall, "revenue.hardware_usd_week").value
    );
    expect(f.revenue.hardware.at(-1)?.units).toBe(
      value(wall, "revenue.hardware_units_week").value
    );
    expect(f.health.cost.at(-1)?.total).toBe(value(wall, "cost.net_day").value);
    expect(f.health.costPerMau.at(-1)?.costPerMau).toBeCloseTo(
      value(wall, "cost.per_mau_month").value!,
      2
    );
    for (const [key, id] of [
      ["wau", "growth.wau"],
      ["dau", "engagement.dau"],
      ["mau", "engagement.mau"],
      ["activation", "activation.rate"],
      ["retained", "retention.if_activated"],
      ["netCost", "cost.net_day"],
      ["mrr", "revenue.mrr"],
      ["costPerMau", "cost.per_mau_month"],
    ] as const)
      expect(f.headline[key].at(-1)?.value).toBeCloseTo(
        value(wall, id).value!,
        2
      );
    // Prior rows are the snapshot's own prior period.
    expect(f.headline.wau[0].value).toBe(wau.prev);
  });

  it("reports rate changes in percentage points and counts/money in relative %", () => {
    const rows = (prior: number, current: number) => [
      { date: "a", value: prior },
      { date: "b", value: current },
    ];
    expect(headlineDelta("activation", rows(30, 36.6))).toMatchObject({
      unit: "pp",
      delta: expect.closeTo(6.6, 6),
      tone: "good",
      text: `▲\u00a06.6\u00a0pp${GOOD_MARK}`, // never wraps in a narrow strip
    });
    expect(headlineDelta("wau", rows(4000, 3600))).toMatchObject({
      unit: "%",
      delta: -10,
      tone: "bad",
      text: `▼\u00a010.0%${BAD_MARK}`,
    });
    // Cost up is bad; flat is neutral; one row has no prior.
    expect(headlineDelta("netCost", rows(2000, 2500)).tone).toBe("bad");
    expect(headlineDelta("costPerMau", rows(7, 7)).text).toBe("■\u00a00.0%");
    expect(headlineDelta("mrr", [{ date: "b", value: 1 }]).text).toBe(
      "no prior"
    );
    expect(headlineDelta("arpmau", [{ date: "b", value: null }]).text).toBe(
      "—"
    );
  });

  it("keeps every stat slot when a value is missing, so strips stay aligned", async () => {
    const s = sources();
    const f = await all(null, s);
    for (const key of [
      "wau",
      "dau",
      "mau",
      "activation",
      "capture",
      "retained",
      "established",
      "mrr",
      "arpmau",
      "hardware",
      "netCost",
      "costPerMau",
    ])
      expect(f.headline[key].length, key).toBeGreaterThan(0);
    const strip = f.headline.strip_retention[0];
    expect(Object.values(strip)).toHaveLength(2);
  });

  it("serves one delta strip per column from the headline pairs", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const wau = value(wall, "growth.wau");
    const strip = f.headline.strip_growth[0];
    expect(Object.keys(strip)).toEqual(["wau", "dau", "mau"]);
    expect(strip.wau).toBe(headlineDelta("wau", f.headline.wau).text);
    expect(f.headline.deltas.find((d) => d.key === "wau")?.delta).toBeCloseTo(
      (100 * (wau.value! - wau.prev!)) / wau.prev!
    );
    expect(Object.keys(f.headline.strip_activation[0])).toEqual([
      "activation",
      "capture",
    ]);
    expect(f.headline.deltas.find((d) => d.key === "activation")?.unit).toBe(
      "pp"
    );
  });

  it("computes the same latest values from series queries alone, without the snapshot", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    resetSeriesCache();
    const f = await all(null, s);
    expect(f.growth.weekly.at(-1)?.total).toBe(value(wall, "growth.wau").value);
    expect(f.growth.weekly.at(-1)?.macos).toBe(
      value(wall, "growth.wau").split.macos
    );
  });

  it("reads 26 weekly growth periods, hides pre-telemetry weeks, conserves accounting and reuses snapshot cohorts", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const weeks = f.growth.weekly;
    expect(GROWTH_WEEKS).toBe(26);
    expect(String(weeks[0].date) >= "2026-05-10").toBe(true);
    expect(weeks).toHaveLength(VISIBLE_WEEKS);
    expect(new Set(weeks.map((w) => w.date)).size).toBe(VISIBLE_WEEKS);
    expect([...weeks].map((w) => w.date).sort()).toEqual(
      weeks.map((w) => w.date)
    );
    for (const w of weeks.slice(0, -6)) {
      expect(Number(w.new) + Number(w.resurrected) + Number(w.retained)).toBe(
        w.total
      );
      expect(w.quickRatio).toBeCloseTo(
        (Number(w.new) + Number(w.resurrected)) / 7,
        2
      );
    }
    expect(f.growth.power[0]).toMatchObject({ days: "1d", "This week": 58.8 });
    // Cohorts: periods 0–5 are the snapshot trend, 6–11 the history read.
    expect(f.activation.activation).toHaveLength(COHORT_WEEKS);
    const cohortSql = (s.query as ReturnType<typeof vi.fn>).mock.calls.filter(
      ([sql]) => String(sql).includes("denominator,countIf")
    );
    // Snapshot: 3 maturities × 3 chunks + true-new 3; series: 2 histories × 3 chunks.
    expect(cohortSql).toHaveLength(12 + 6);
    // One frame per cohort age, nine week rows each; the field name carries
    // the age as invisible marks (the board's ramp matcher).
    const newest = f.retention.cohort_0;
    expect(newest).toHaveLength(9);
    expect(newest[1]).toHaveProperty("week", 1);
    const [label] = Object.keys(newest[0]).filter((k) => k !== "week");
    expect(label).toMatch(/^[A-Z][a-z]{2} \d+$/);
    const older = Object.keys(f.retention.cohort_2[0]).find(
      (k) => k !== "week"
    );
    expect(older?.endsWith(CURVE_MARK.repeat(2))).toBe(true);
    expect(older?.slice(0, -2)).not.toContain(CURVE_MARK);
  });

  it("lists sourceless wall metrics as compact coverage gaps", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const gaps = assembleSeries("headline", {}, wall, now).gaps;
    expect(gaps.map((g) => g.metric)).toEqual([
      "Crash-free (macOS)",
      "Positive answers",
      "Payer churn",
      "Activated → paid",
      "Gross margin",
    ]);
    expect(gaps.every((g) => g.reason && !String(g.reason).includes(";"))).toBe(
      true
    );
    expect(gaps.every((g) => String(g.missing).length <= 24)).toBe(true);
  });

  it("draws unit economics daily from the first FinOps book day and compares per-user stats a week back", async () => {
    const s = sources();
    // The book starts 20 days ago, like FinOps' 2026-09-18 start.
    s.finops = vi.fn(async () => ({
      mrr: Object.fromEntries(
        Object.entries(finopsMrr).filter(
          ([day]) => day >= isoDay(shiftDay(end, -20))
        )
      ),
      paying: finopsHistory.paying,
      payingCustomers: finopsHistory.payingCustomers,
      nonUsdPaying: finopsHistory.nonUsdPaying,
      refreshed: finopsHistory.refreshed,
    }));
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const days = (rows: Row[]) => rows.map((r) => String(r.date).slice(0, 10));
    const daily = (from: number, to: number) =>
      Array.from({ length: from - to + 1 }, (_, i) =>
        isoDay(shiftDay(end, -from + i))
      );
    // Each point uses the book snapshotted that day, so the first point is
    // the book's first day; nothing is drawn (or zero) before it.
    expect(days(f.revenue.arpmau)).toEqual(daily(20, 1));
    expect(days(f.health.costPerMau)).toEqual(daily(UNIT_DAYS, 2));
    // Every daily point has its own 30-day MAU read (seven offsets per read).
    for (const r of f.revenue.arpmau) expect(r.mau).toBeGreaterThan(0);
    expect(s.query).toHaveBeenCalledWith(
      expect.stringContaining("ARRAY JOIN [0,1,2,3,4,5,6]")
    );
    // Per user and cost / user priors: the point seven days earlier.
    expect(f.headline.arpmau[0].date).toBe(
      `${isoDay(shiftDay(end, -8))}T00:00:00Z`
    );
    expect(f.headline.costPerMau).toEqual([
      {
        date: `${isoDay(shiftDay(end, -9))}T00:00:00Z`,
        value: f.health.costPerMau.at(-8)?.costPerMau,
      },
      {
        date: `${isoDay(shiftDay(end, -2))}T00:00:00Z`,
        value: f.health.costPerMau.at(-1)?.costPerMau,
      },
    ]);
  });

  it("prices each day with that day's FinOps book and gaps a day without one", async () => {
    const s = sources();
    const hole = isoDay(shiftDay(end, -6));
    s.finops = vi.fn(async () => ({
      mrr: Object.fromEntries(
        Object.entries(finopsMrr).filter(([day]) => day !== hole)
      ),
      paying: finopsHistory.paying,
      payingCustomers: finopsHistory.payingCustomers,
      nonUsdPaying: finopsHistory.nonUsdPaying,
      refreshed: finopsHistory.refreshed,
    }));
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    const at = (rows: Row[], day: string) =>
      rows.find((r) => String(r.date).slice(0, 10) === day);
    expect(at(f.revenue.arpmau, hole)).toBeUndefined();
    expect(at(f.health.cost, hole)?.revenuePerDay).toBeNull();
    const day = isoDay(shiftDay(end, -5));
    const book = finopsMrr[day].unlimited + finopsMrr[day].plus;
    expect(at(f.health.cost, day)?.revenuePerDay).toBeCloseTo(book / 30.4375);
    const point = at(f.revenue.arpmau, day)!;
    expect(point.finopsArpmau).toBeCloseTo(book / (point.mau as number), 1);
  });

  it("shades the maturing span from each cohort line's last point to now", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    const f = await all(wall, s);
    // Cohorts roll daily: week one ends 8 days back, retained 38 days back.
    expect(f.activation.maturing).toEqual([
      { date: `${isoDay(shiftDay(end, -8))}T00:00:00Z`, maturing: 1 },
      { date: now.toISOString(), maturing: 1 },
    ]);
    expect(f.activation.activation.at(-1)?.date).toBe(
      f.activation.maturing[0].date
    );
    expect(f.activation.capture.at(-1)?.date).toBe(
      f.activation.maturing[0].date
    );
    expect(f.retention.retainedMaturing[0].date).toBe(
      `${isoDay(shiftDay(end, -38))}T00:00:00Z`
    );
    expect(f.retention.retained.at(-1)?.date).toBe(
      f.retention.retainedMaturing[0].date
    );
  });

  it("never anchors to fixture money and uses same-source FinOps change for the MRR delta", async () => {
    const s = sources();
    const wall = await computeWall(s, now);
    for (const m of wall.metrics) if (m.id === "revenue.mrr") m.fixture = true;
    const frames = assembleSeries(
      "headline",
      { finops: await s.finops("") },
      wall,
      now
    );
    const latest = finopsMrr[isoDay(shiftDay(end, -1))];
    expect(frames.mrr.at(-1)?.value).toBe(latest.unlimited + latest.plus);
    const weekAgo = finopsMrr[isoDay(shiftDay(end, -8))];
    expect(frames.mrr[0].value).toBe(weekAgo.unlimited + weekAgo.plus);
  });
});

describe("margin by plan (allocated estimate)", () => {
  const day = (k: number) => isoDay(shiftDay(end, -k));
  const plans = (scale: number) => ({
    unlimited: { usd: 40 * scale, users: 4, varUsd: 0, varUsers: 0 },
    unlimited_v2: { usd: 30 * scale, users: 3, varUsd: 0, varUsers: 0 },
    operator: { usd: 10 * scale, users: 1, varUsd: 0, varUsers: 0 },
    plus: { usd: 5 * scale, users: 1, varUsd: 0, varUsers: 0 },
    architect: { usd: 2 * scale, users: 1, varUsd: 0, varUsers: 0 },
    basic: { usd: 60 * scale, users: 8, varUsd: 0, varUsers: 0 },
    unattributed: { usd: 0.5, users: 1, varUsd: 0, varUsers: 0 },
    none: { usd: 0.25, users: 1, varUsd: 0, varUsers: 0 },
  });
  const book = {
    unlimited: 3_000,
    unlimited_v2: 2_000,
    operator: 900,
    plus: 300,
    architect: 200,
  };
  const legs = async (
    sttMeasured: Record<string, Record<string, number>> = {},
    saasMeasured: Record<string, number> = {},
    saasAnnualPartial: Record<string, string> = {}
  ) => ({
    billing: await billing(),
    // FinOps cost settles ~D−3: days 6..3, with day 5 missing.
    planCost: {
      plans: { [day(6)]: plans(1), [day(4)]: plans(1.1), [day(3)]: plans(1) },
      sttMeasured,
      saasMeasured,
      saasAnnualPartial,
      sttCash: {},
    },
    // The book is missing day 4 (like 2026-09-29) and has today's snapshot.
    finops: {
      mrr: Object.fromEntries([7, 6, 5, 3, 2, 1, 0].map((k) => [day(k), book])),
      paying: {},
      payingCustomers: {},
      nonUsdPaying: {},
      refreshed: {},
    },
  });

  it("draws only days with both cost and revenue and reconciles to the all-in total", async () => {
    const f = assembleSeries("health", await legs(), null, now);
    const rows = f.marginByPlan;
    // Day 5 has no cost, day 4 no revenue: gaps, never zero; ends at day 3.
    expect(rows.map((r) => String(r.date).slice(0, 10))).toEqual([
      day(6),
      day(3),
    ]);
    const allIn = new Map(f.cost.map((r) => [String(r.date).slice(0, 10), r]));
    for (const r of rows) {
      const date = String(r.date).slice(0, 10);
      expect(r.allInTotal).toBeCloseTo(allIn.get(date)!.total as number, 1);
      const parts =
        MARGIN_PLANS.reduce((s, p) => s + (r[`${p}Cost`] as number), 0) +
        (r.unattributedCost as number);
      expect(parts).toBeCloseTo(r.allInTotal as number, 1);
      expect(r.shared).toBeCloseTo(
        (r.allInTotal as number) - (r.finopsTotal as number),
        1
      );
    }
    const r = rows.at(-1)!;
    // The shared remainder is spread by cost-active user-days (Neo: 4 of 20).
    expect(r.unlimitedCost).toBeCloseTo(
      40 + ((r.shared as number) * 4) / 20,
      1
    );
    const revenue = 3_000 / (365.25 / 12);
    expect(r.unlimitedRevenue).toBeCloseTo(revenue, 2);
    expect(r.unlimitedPct).toBeCloseTo(
      (100 * (revenue - (r.unlimitedCost as number))) / revenue,
      0
    );
    // Free: no revenue, so no margin %; its margin is −cost in $/day.
    expect(r.basicPct).toBeNull();
    expect(r.basicMargin).toBeCloseTo(-(r.basicCost as number), 2);
    expect(r.basicMargin as number).toBeLessThan(0);
    // `unattributed` and other FinOps segments stay their own row.
    expect(r.unattributedCost).toBeCloseTo(
      0.75 + ((r.shared as number) * 2) / 20,
      1
    );
    expect(f.marginStatus[0].text).toBe(
      `Margin through ${new Date(`${day(3)}T00:00:00Z`).toLocaleDateString(
        "en-US",
        { month: "short", day: "numeric", timeZone: "UTC" }
      )} · STT estimate · SaaS estimate · Infra non-GCP estimate as of Oct 16 · Stripe fees unavailable (finops key scope)`
    );
  });

  it("prefers a measured FinOps STT line and labels it measured", async () => {
    const estimate = assembleSeries("health", await legs(), null, now);
    const f = assembleSeries(
      "health",
      await legs({ [day(3)]: { soniox: 99 } }),
      null,
      now
    );
    const at = (rows: Row[]) =>
      rows.find((r) => String(r.date).startsWith(day(3)))!;
    expect(at(f.cost)).toMatchObject({ stt: 99, sttSource: "measured" });
    expect(at(estimate.cost).sttSource).toBe("estimate");
    expect(
      (at(f.cost).total as number) - (at(estimate.cost).total as number)
    ).toBeCloseTo(99 - (at(estimate.cost).stt as number), 6);
    expect(at(f.marginByPlan).allInTotal).toBeCloseTo(
      at(f.cost).total as number,
      1
    );
    expect(f.marginStatus[0].text).toMatch(
      /· STT measured · SaaS estimate · Infra non-GCP estimate as of Oct 16 · Stripe fees unavailable \(finops key scope\)$/
    );
  });

  it("uses measured Mercury SaaS, labels its source, and yields the total", async () => {
    const estimate = assembleSeries("health", await legs(), null, now);
    const f = assembleSeries(
      "health",
      await legs({}, { [day(3)]: 0 }),
      null,
      now
    );
    const at = (rows: Row[]) =>
      rows.find((r) => String(r.date).startsWith(day(3)))!;
    expect(at(f.cost)).toMatchObject({
      saas: 0,
      saasSource: "measured",
      saasMeasuredUsd: 0,
      saasEstimateUsd: null,
    });
    expect(at(estimate.cost)).toMatchObject({
      saasSource: "estimate",
      saasMeasuredUsd: null,
    });
    expect(
      (at(f.cost).total as number) - (at(estimate.cost).total as number)
    ).toBeCloseTo(-(at(estimate.cost).saas as number), 6);
    expect(f.marginStatus[0].text).toMatch(
      /· STT estimate · measured SaaS \(Mercury\) · Infra non-GCP estimate as of Oct 16 · Stripe fees unavailable \(finops key scope\)$/
    );
  });

  it("uses the measured Mercury infra run rate and owns the total once measured", async () => {
    const estimate = assembleSeries("health", await legs(), null, now);
    const base = await legs();
    const f = assembleSeries(
      "health",
      {
        ...base,
        infra: {
          infraMeasured: { [day(3)]: 32.87 },
          infraAnnualPartial: {},
          infraStripeFeesCash: {},
        },
      },
      null,
      now
    );
    const at = (rows: Row[]) =>
      rows.find((r) => String(r.date).startsWith(day(3)))!;
    expect(at(f.cost)).toMatchObject({
      infra: 32.87,
      infraSource: "measured",
      infraMeasuredUsd: 32.87,
      infraEstimateUsd: null,
      infraFeesCashUsd: null,
    });
    expect(at(estimate.cost)).toMatchObject({
      infraSource: "estimate",
      infraMeasuredUsd: null,
    });
    expect(
      (at(f.cost).total as number) - (at(estimate.cost).total as number)
    ).toBeCloseTo(32.87 - (at(estimate.cost).infra as number), 6);
    expect(f.marginStatus[0].text).toMatch(
      /· STT estimate · SaaS estimate · measured Infra non-GCP \(Mercury\) as of Oct 16 · Stripe fees unavailable \(finops key scope\)$/
    );
  });

  it("prices a floored partial infra day by the dated constant, fee cash on its own field (Luna r2 P1/P2)", async () => {
    const base = await legs();
    const f = assembleSeries(
      "health",
      {
        ...base,
        // A partial row below the constant, with excluded fee cash while the
        // fee leg is unavailable (legs() carries no fee table).
        infra: {
          infraMeasured: { [day(3)]: 3.75 },
          infraAnnualPartial: { [day(3)]: "history_under_12_months" },
          infraStripeFeesCash: { [day(3)]: 4 },
        },
      },
      null,
      now
    );
    const row = f.cost.find((r) => String(r.date).startsWith(day(3)))!;
    const constant = INFRA_MONTHLY_USD / (365.25 / 12);
    // The constant floors the base; the series says "estimate", carries the
    // constant in the estimate field and the fee cash apart — neither series
    // absorbs the other, and they sum to the line.
    expect(row).toMatchObject({
      infraSource: "estimate",
      infraMeasuredUsd: null,
      infraFeesCashUsd: 4,
    });
    expect(row.infraEstimateUsd).toBeCloseTo(constant, 6);
    expect(row.infra).toBeCloseTo(constant + 4, 6);
    // The margin line prices Infra by the constant and states the floor; the
    // constant's own as-of (Oct 23) is later than STT/SaaS's, so Oct 16 stays.
    expect(f.marginStatus[0].text).toMatch(
      /· STT estimate · SaaS estimate · Infra non-GCP estimate \(floors partial Mercury run rate\) as of Oct 16 · Stripe fees unavailable \(finops key scope\)$/
    );
    expect(f.estimates.find((e) => e.line === "Infra")).toMatchObject({
      asOf: INFRA_AS_OF,
      stale: 0,
    });
  });

  it("counts the Mercury stripe_fees cash on every rendered frame while the fee line is dark (Luna r2 P2)", async () => {
    const base = await legs();
    // Cash on every frame the wall renders — the oldest included. The frames
    // span the 60 days ending at the D−2 cutoff (days 61..2 here); a history
    // read that stops 40 days back drops the cash from the oldest 19.
    const cash = Object.fromEntries(
      Array.from({ length: HEALTH_COST_DAYS }, (_, i) => [day(i + 2), 4])
    );
    const f = assembleSeries(
      "health",
      {
        ...base,
        infra: {
          infraMeasured: {},
          infraAnnualPartial: {},
          infraStripeFeesCash: cash,
        },
      },
      null,
      now
    );
    expect(f.cost).toHaveLength(HEALTH_COST_DAYS);
    expect(String(f.cost[0].date).slice(0, 10)).toBe(day(HEALTH_COST_DAYS + 1));
    expect(String(f.cost.at(-1)!.date).slice(0, 10)).toBe(day(2));
    // Every frame, the oldest first: the dated constant base plus the cash,
    // the fee line dark — the money sits on exactly one line on every day.
    const constant = INFRA_MONTHLY_USD / (365.25 / 12);
    for (const r of f.cost) {
      expect(r.infraFeesCashUsd).toBe(4);
      expect(r.infra).toBeCloseTo(constant + 4, 6);
      expect(r.feesUnavailable).toBe(1);
    }
  });

  it("flags the cost frames once a manual estimate is older than 35 days", async () => {
    const fresh = assembleSeries("health", await legs(), null, now);
    expect(fresh.cost.every((r) => r.estimateStale === 0)).toBe(true);
    const later = new Date("2026-12-01T12:00Z"); // past every line's threshold
    const f = assembleSeries("health", {}, null, later);
    expect(f.estimates).toEqual([
      expect.objectContaining({ line: "STT", asOf: "2026-10-16", stale: 1 }),
      expect.objectContaining({ line: "SaaS", asOf: "2026-10-16", stale: 1 }),
      expect.objectContaining({
        line: "Infra",
        asOf: INFRA_AS_OF,
        stale: 1,
      }),
    ]);
    expect(f.marginStatus[0].text).toBe(
      "Margin through — · STT estimate · SaaS estimate · Infra non-GCP estimate as of Oct 16 (stale) · Stripe fees unavailable (finops key scope)"
    );
  });

  it("keeps modelled Modulate and cash out of the STT measured series (Luna P2)", async () => {
    const base = await legs({ [day(3)]: { soniox: 99, deepgram: 11 } });
    const f = assembleSeries(
      "health",
      {
        ...base,
        planCost: {
          ...base.planCost,
          sttCash: { [day(3)]: { deepgram: 5, modulate: 20 } },
        },
        modulate: {
          byDay: {
            [day(3)]: {
              usd: 20.5,
              seconds: 1_230_000,
              pricePerHour: 0.06,
              priceAsOf: "2026-10-18",
            },
          },
          price: 0.06,
          priceAsOf: "2026-10-18",
        },
      },
      null,
      now
    );
    const at = f.cost.find((r) => String(r.date).startsWith(day(3)))!;
    // Measured = Soniox usage + measured Deepgram ONLY; the modelled Modulate
    // dollars have their own series and never enter "STT measured".
    expect(at.stt).toBeCloseTo(99 + 11 + 20.5);
    expect(at.sttMeasuredUsd).toBeCloseTo(110);
    expect(at.sttModulateModelledUsd).toBeCloseTo(20.5);
    expect(at.sttEstimateUsd).toBeNull();
    expect(at.sttCashUsd).toBeNull(); // measured Deepgram wins over its cash; modelled wins over Modulate cash
    expect(
      (at.sttMeasuredUsd as number) + (at.sttModulateModelledUsd as number)
    ).toBeCloseTo(at.stt as number);
  });

  it("reads plan cost and both vendor STT legs as health legs", async () => {
    const s = sources();
    const vendorBalance = vi.fn(async () => ({
      snapshots: 0,
      latestTs: null,
      asOf: null,
      spend: {},
      flags: {},
    }));
    const modulate = vi.fn(async () => ({
      byDay: {},
      price: null,
      priceAsOf: null,
    }));
    await seriesPayload("health", Promise.resolve(null), now, {
      ...s,
      vendorBalance,
      modulate,
    });
    expect(s.planCost).toHaveBeenCalledWith(isoDay(now));
    expect(vendorBalance).toHaveBeenCalledWith(isoDay(now));
    expect(modulate).toHaveBeenCalledWith(isoDay(now));
  });

  it("reads plan cost as a health leg", async () => {
    const s = sources();
    await seriesPayload("health", Promise.resolve(null), now, s);
    expect(s.planCost).toHaveBeenCalledWith(isoDay(now));
  });
});

describe("v3 series cold-load and cache rules", () => {
  it("returns honest loading frames within five seconds while one shared refresh continues", async () => {
    vi.useFakeTimers();
    const s = sources();
    s.query = vi.fn(() => new Promise<never>(() => {}));
    const retain = vi.fn();
    const pending = Promise.all([
      seriesPayload("growth", Promise.resolve(null), now, s, retain),
      seriesPayload("growth", Promise.resolve(null), now, s, retain),
    ]);
    await vi.advanceTimersByTimeAsync(5_000);
    const [a, b] = await pending;
    expect(a).toMatchObject({ refreshing: true, partial: true });
    expect(a.frames.weekly).toEqual([]);
    expect(b.gaps.growth).toBe("Series refresh running");
    expect(retain).toHaveBeenCalledTimes(1);
    expect(s.query).toHaveBeenCalledTimes(1); // single flight, serial lane
  });

  it("memoizes series reads for the UTC day and serves last-good legs after a failed next-day refresh", async () => {
    const s = sources();
    await seriesPayload("growth", Promise.resolve(null), now, s);
    const calls = (s.query as ReturnType<typeof vi.fn>).mock.calls.length;
    await seriesPayload("growth", Promise.resolve(null), now, s);
    expect((s.query as ReturnType<typeof vi.fn>).mock.calls.length).toBe(calls);
    const tomorrow = new Date(now.getTime() + 13 * 3_600_000); // next UTC day, <24h old
    s.query = vi.fn(async () => {
      throw new Error("PostHog down");
    });
    const next = await seriesPayload(
      "growth",
      Promise.resolve(null),
      tomorrow,
      s
    );
    expect(next.frames.weekly).toHaveLength(VISIBLE_WEEKS);
    expect(next.cacheStale).toBe(true);
    expect(next.gaps.growth).toContain("PostHog");
  });

  it("serves partial history and retries only the missing periods", async () => {
    const s = sources();
    let reads = 0;
    s.query = vi.fn(async (sql: string) => {
      // Fail three non-adjacent periods (0, 2, 4) on the first sweep only.
      if (sql.includes("__churned") && [0, 2, 4].includes(reads++))
        throw new Error("504");
      return query(sql);
    });
    const first = await seriesPayload("growth", Promise.resolve(null), now, s);
    expect(first.frames.weekly).toHaveLength(VISIBLE_WEEKS - 3);
    expect(first.partial).toBe(true);
    const later = new Date(now.getTime() + 3 * 60_000);
    const before = (s.query as ReturnType<typeof vi.fn>).mock.calls.length;
    const second = await seriesPayload(
      "growth",
      Promise.resolve(null),
      later,
      s
    );
    expect(
      (s.query as ReturnType<typeof vi.fn>).mock.calls.length - before
    ).toBe(3);
    expect(second.frames.weekly).toHaveLength(VISIBLE_WEEKS);
  });

  it("stops a saturated sweep after two failures and backs off exponentially", async () => {
    const s = sources();
    s.query = vi.fn(async () => {
      throw new Error("PostHog 504");
    });
    const at = (ms: number) => new Date(now.getTime() + ms);
    await seriesPayload("growth", Promise.resolve(null), now, s);
    expect(s.query).toHaveBeenCalledTimes(2);
    await seriesPayload("growth", Promise.resolve(null), at(59_000), s);
    expect(s.query).toHaveBeenCalledTimes(2); // 60s cooldown
    await seriesPayload("growth", Promise.resolve(null), at(61_000), s);
    expect(s.query).toHaveBeenCalledTimes(4);
    await seriesPayload(
      "growth",
      Promise.resolve(null),
      at(61_000 + 119_000),
      s
    );
    expect(s.query).toHaveBeenCalledTimes(4); // doubled to 120s
    await seriesPayload(
      "growth",
      Promise.resolve(null),
      at(61_000 + 121_000),
      s
    );
    expect(s.query).toHaveBeenCalledTimes(6);
  });
});

describe("v3 series converge across Cloud Run instances", () => {
  const settle = () => new Promise((r) => setTimeout(r, 0));

  it("lets one instance refresh a leg while others serve without reading", async () => {
    const store = memorySeriesStore();
    const a = { ...sources(), store, instance: "a" };
    a.query = vi.fn(() => new Promise<never>(() => {}));
    const first = seriesPayload("growth", Promise.resolve(null), now, a);
    await settle();
    resetSeriesCache(); // instance b: cold process, same shared store
    const b = { ...sources(), store, instance: "b" };
    const served = await seriesPayload("growth", Promise.resolve(null), now, b);
    expect(b.query).not.toHaveBeenCalled();
    expect(served).toMatchObject({ refreshing: true, partial: true });
    expect(served.gaps.growth).toBe("Series refresh running");
    void first;
  });

  it("serves the shared last-good on a cold instance with zero reads", async () => {
    const store = memorySeriesStore();
    const a = { ...sources(), store, instance: "a" };
    const filled = await seriesPayload("growth", Promise.resolve(null), now, a);
    expect(filled.partial).toBe(false);
    resetSeriesCache();
    const b = { ...sources(), store, instance: "b" };
    const served = await seriesPayload("growth", Promise.resolve(null), now, b);
    expect(b.query).not.toHaveBeenCalled();
    expect(served.frames.weekly).toEqual(filled.frames.weekly);
    expect(served).toMatchObject({ refreshing: false, partial: false });
    // Reads live inside the leg doc: bounded docs, no per-read garbage.
    expect(Array.from(store.docs.keys())).toEqual([
      "wall-series:v1:leg:growth",
    ]);
  });

  it("resumes an abandoned fill from its persisted reads after the lease lapses", async () => {
    const store = memorySeriesStore();
    const a = { ...sources(), store, instance: "a" };
    let served = 0;
    a.query = vi.fn((sql: string) =>
      served++ < 3 ? query(sql) : new Promise<never>(() => {})
    );
    void seriesPayload("growth", Promise.resolve(null), now, a);
    for (let i = 0; i < 10; i++) await settle();
    expect(a.query).toHaveBeenCalledTimes(4);
    resetSeriesCache(); // instance a died mid-fill
    const later = new Date(now.getTime() + LEASE_MS + 1);
    const b = { ...sources(), store, instance: "b" };
    const resumed = await seriesPayload(
      "growth",
      Promise.resolve(null),
      later,
      b
    );
    expect(b.query).toHaveBeenCalledTimes(GROWTH_WEEKS - 3);
    expect(resumed.frames.weekly).toHaveLength(VISIBLE_WEEKS);
  });

  it("lets a dev server serve shared legs but fill only in its own memory", async () => {
    const shared = memorySeriesStore();
    await seriesPayload("growth", Promise.resolve(null), now, {
      ...sources(),
      store: shared,
    });
    const before = JSON.stringify(Array.from(shared.docs.entries()));
    const writes = vi.spyOn(shared, "write");
    const leases = vi.spyOn(shared, "acquire");
    const dev = { ...sources(), store: readThroughStore(shared) };
    const growth = await seriesPayload(
      "growth",
      Promise.resolve(null),
      now,
      dev
    );
    expect(dev.query).not.toHaveBeenCalled(); // the shared leg is served
    expect(growth.frames.weekly).toHaveLength(VISIBLE_WEEKS);
    const revenue = await seriesPayload(
      "revenue",
      Promise.resolve(null),
      now,
      dev
    ); // a leg the shared store lacks fills locally
    expect(dev.query).toHaveBeenCalled();
    expect(revenue.gaps).toEqual({});
    expect(revenue.frames.arpmau.length).toBeGreaterThan(1);
    expect(writes).not.toHaveBeenCalled();
    expect(leases).not.toHaveBeenCalled();
    expect(JSON.stringify(Array.from(shared.docs.entries()))).toBe(before);
  });

  it("keeps the headline whole when only older MAU windows time out", async () => {
    const s = { ...sources(), store: memorySeriesStore() };
    let mauReads = 0;
    s.query = vi.fn(async (sql: string) => {
      if (sql.includes("spans") && mauReads++ > 0)
        throw new Error("PostHog execution time limit exceeded (HTTP 504)");
      return query(sql);
    });
    const head = await seriesPayload("headline", Promise.resolve(null), now, s);
    expect(head.gaps).not.toHaveProperty("mauPrior");
    const revenue = await seriesPayload(
      "revenue",
      Promise.resolve(null),
      now,
      s
    );
    expect(revenue.gaps).toHaveProperty("mauDaily");
    expect(revenue.gaps).not.toHaveProperty("mauPrior");
  });

  it("logs one aggregate line per leg attempt and a data-through status", async () => {
    const lines: Record<string, unknown>[] = [];
    const spy = vi.spyOn(console, "log").mockImplementation((line: unknown) => {
      try {
        lines.push(JSON.parse(String(line)));
      } catch {
        // not ours
      }
    });
    const s = { ...sources(), store: memorySeriesStore(), instance: "rev:abc" };
    (s.query as ReturnType<typeof vi.fn>).mockImplementationOnce(async () => {
      throw new Error("boom");
    });
    await seriesPayload("growth", Promise.resolve(null), now, s);
    const head = await seriesPayload("headline", Promise.resolve(null), now, s);
    spy.mockRestore();
    const legs = lines.filter((l) => l.event === "wall_series_leg");
    expect(legs.find((l) => l.leg === "growth")).toMatchObject({
      instance: "rev:abc",
      outcome: "partial:error",
      rows: expect.any(Number),
      duration_ms: expect.any(Number),
    });
    expect(legs.find((l) => l.leg === "billing")).toMatchObject({
      outcome: "ok",
    });
    const reads = lines.filter((l) => l.event === "wall_series_read");
    expect(reads[0]).toMatchObject({
      leg: "growth",
      outcome: "error",
      rows: 0,
    });
    for (const l of lines)
      expect(JSON.stringify(l)).not.toMatch(/SELECT|actor|distinct_id/i);
    expect(head.status?.through).toBe(isoDay(shiftDay(end, -1)));
    expect(head.frames.gaps[0]).toMatchObject({ metric: "Data through" });
    // The TV's single freshness line, without the rollup diagnostics.
    expect(String(head.frames.through[0].text)).toMatch(
      /^Data through Oct 14 \(UTC\)/
    );
    expect(String(head.frames.through[0].text)).not.toContain("rollup");
    expect(String(head.frames.gaps[0].missing)).toMatch(/^Oct 14 \(UTC\)/);
  });
});

describe("v3 series lease is fenced", () => {
  const settle = async (n = 10) => {
    for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0));
  };
  const read = (at: number) => ({ rows: [[at]], refreshedAt: null, at });

  it("grants exactly one of many concurrent acquires", async () => {
    const store = memorySeriesStore();
    const results = await Promise.all(
      Array.from({ length: 10 }, (_, i) =>
        store.acquire("growth", `i${i}`, now.getTime())
      )
    );
    expect(results.filter((r) => r.status === "acquired")).toHaveLength(1);
    expect(results.filter((r) => r.status === "contended")).toHaveLength(9);
  });

  it("does not fill when the lease call times out, and hands back a late grant", async () => {
    vi.useFakeTimers();
    const store = memorySeriesStore();
    let grant: (() => void) | undefined;
    const slow: SeriesStore = {
      ...store,
      acquire: (leg, holder, at) =>
        new Promise((resolve) => {
          grant = () => resolve(store.acquire(leg, holder, at));
        }),
    };
    const s = { ...sources(), store: slow, instance: "a" };
    const pending = seriesPayload("growth", Promise.resolve(null), now, s);
    await vi.advanceTimersByTimeAsync(5_000);
    const served = await pending;
    expect(s.query).not.toHaveBeenCalled();
    expect(served.gaps.growth).toBe("Shared series store unavailable");
    grant!(); // the transaction lands after we gave up on it
    await vi.advanceTimersByTimeAsync(0);
    await vi.advanceTimersByTimeAsync(0);
    expect(store.docs.has("wall-series:v1:lease:growth")).toBe(false);
  });

  it("does not fill when the lease call errors", async () => {
    const store = memorySeriesStore();
    const s = {
      ...sources(),
      store: {
        ...store,
        acquire: async () => ({ status: "unavailable" as const }),
      },
    };
    const served = await seriesPayload("growth", Promise.resolve(null), now, s);
    expect(s.query).not.toHaveBeenCalled();
    expect(served.frames.weekly).toEqual([]);
  });

  it("rejects a stale holder's writes and stops its fill at the next read", async () => {
    const store = memorySeriesStore();
    const lines: Record<string, unknown>[] = [];
    const spy = vi.spyOn(console, "log").mockImplementation((line: unknown) => {
      try {
        lines.push(JSON.parse(String(line)));
      } catch {
        // not ours
      }
    });
    const a = { ...sources(), store, instance: "a" };
    a.query = vi.fn(async (sql: string) => {
      // Our lease lapsed and another instance took it before this read landed.
      await store.acquire("growth", "b", now.getTime() + LEASE_MS + 1);
      return query(sql);
    });
    await seriesPayload("growth", Promise.resolve(null), now, a);
    await settle();
    spy.mockRestore();
    expect(
      (a.query as ReturnType<typeof vi.fn>).mock.calls.length
    ).toBeLessThan(4);
    expect(await store.read("growth")).toBeNull(); // nothing from "a" landed
    expect(lines.find((l) => l.event === "wall_series_leg")).toMatchObject({
      leg: "growth",
      outcome: "lease_lost",
    });
    // Store level: an expired token is fenced; the live one writes.
    const late = await store.acquire("curve", "a", 0);
    const live = await store.acquire("curve", "b", LEASE_MS + 1);
    if (late.status !== "acquired" || live.status !== "acquired")
      throw new Error();
    const patch = { reads: { day: "2026-10-15", rows: { h: read(1) } } };
    expect(await store.write("curve", late.token, patch, LEASE_MS + 2)).toBe(
      "fenced"
    );
    expect(await store.write("curve", live.token, patch, LEASE_MS + 2)).toBe(
      "written"
    );
  });

  it("awaits the final write before releasing, so the next holder sees the completed doc", async () => {
    const store = memorySeriesStore();
    const order: string[] = [];
    const tracked: SeriesStore = {
      ...store,
      async write(leg, token, patch, at) {
        if (patch.entry !== undefined) {
          await new Promise((r) => setTimeout(r, 50)); // slow final commit
          order.push("final-write");
        }
        return store.write(leg, token, patch, at);
      },
      async release(leg, token) {
        order.push("release");
        return store.release(leg, token);
      },
    };
    const a = { ...sources(), store: tracked, instance: "a" };
    await seriesPayload("growth", Promise.resolve(null), now, a);
    await new Promise((r) => setTimeout(r, 100));
    expect(order).toEqual(["final-write", "release"]);
    resetSeriesCache();
    const b = { ...sources(), store, instance: "b" };
    const served = await seriesPayload("growth", Promise.resolve(null), now, b);
    expect(b.query).not.toHaveBeenCalled();
    expect(served.partial).toBe(false);
  });

  it("merges reads as a superset: a slow, older write never drops completed reads", async () => {
    const day = "2026-10-15";
    const full = {
      entry: null,
      reads: { day, rows: { h1: read(5), h2: read(6) } },
    };
    const merged = mergeLegDoc(full, { reads: { day, rows: { h1: read(1) } } });
    expect(Object.keys(merged.reads.rows).sort()).toEqual(["h1", "h2"]);
    expect(merged.reads.rows.h1.at).toBe(5); // newer kept
    expect(
      mergeLegDoc(full, { reads: { day: "2026-10-16", rows: {} } }).reads
    ).toEqual({
      day: "2026-10-16",
      rows: {},
    });
    expect(
      mergeLegDoc(full, { reads: { day: "2026-10-14", rows: { x: read(9) } } })
        .reads
    ).toBe(full.reads);
    // Through the fenced write as well.
    const store = memorySeriesStore();
    const lease = await store.acquire("growth", "a", 0);
    if (lease.status !== "acquired") throw new Error();
    await store.write("growth", lease.token, { reads: full.reads }, 1);
    await store.write(
      "growth",
      lease.token,
      { reads: { day, rows: { h1: read(1) } } },
      2
    );
    const stored = await store.read("growth");
    expect(Object.keys(stored!.reads.rows).sort()).toEqual(["h1", "h2"]);
  });

  it("fills per process, single-flight, only after the store has failed repeatedly", async () => {
    const down: SeriesStore = {
      read: async () => {
        throw new Error("unreachable");
      },
      acquire: async () => ({ status: "unavailable" }),
      renew: async () => false,
      write: async () => "unavailable",
      release: async () => {},
    };
    const s = { ...sources(), store: down };
    let t = now.getTime();
    // Each request fails twice (read + lease), so the limit is crossed on the
    // request after floor(limit / 2) failing ones.
    for (let i = 0; i < Math.floor(STORE_FAIL_LIMIT / 2); i++) {
      await seriesPayload("growth", Promise.resolve(null), new Date(t), s);
      expect(s.query).not.toHaveBeenCalled();
      t += 11_000;
    }
    await Promise.all([
      seriesPayload("growth", Promise.resolve(null), new Date(t), s),
      seriesPayload("growth", Promise.resolve(null), new Date(t), s),
    ]);
    await settle();
    expect(s.query).toHaveBeenCalledTimes(GROWTH_WEEKS); // one fill, not two
  });
});

describe("the snapshot is shared and never served cold as settled", () => {
  const today = `${isoDay(end)}T00:00:00Z`;
  const through = `${isoDay(shiftDay(end, -1))}T00:00:00Z`;
  const computeWith =
    (s: WallSources) =>
    (_sources?: WallSources, at = new Date()) =>
      computeWall(s, at);
  const series = (snapshot: Promise<WallPayload>, s: SeriesSources) =>
    Promise.all(
      (
        [
          "headline",
          "growth",
          "activation",
          "retention",
          "revenue",
          "health",
        ] as const
      ).map((name) => seriesPayload(name, snapshot, now, s))
    );
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(now);
  });

  it("serves the shared last good on a cold instance with zero PostHog reads, charts reaching the stat", async () => {
    const store = memorySeriesStore();
    const a = sources();
    const retain = vi.fn();
    await wallPayload(now, computeWith(a), retain, store);
    await Promise.all(retain.mock.calls.map(([work]) => work));
    expect(a.query).toHaveBeenCalled();
    expect(store.docs.has("wall-series:v1:leg:snapshot")).toBe(true);

    resetWallCache(); // instance b: cold process, same shared store
    resetSeriesCache();
    const b = sources();
    const compute = vi.fn(computeWith(b));
    const wall = await wallPayload(now, compute, () => {}, store);
    expect(compute).not.toHaveBeenCalled();
    expect(b.query).not.toHaveBeenCalled();
    expect(wall.refreshing).toBeFalsy();
    expect(value(wall, "growth.wau").value).not.toBeNull();

    const f = await all(wall, b);
    expect(f.activation.activation.at(-1)).toMatchObject({
      date: `${value(wall, "activation.rate").trend.at(-1)!.date}T00:00:00Z`,
      total: value(wall, "activation.rate").value,
    });
    expect(f.retention.established.at(-1)?.total).toBeCloseTo(
      value(wall, "retention.established_week").value!,
      1
    );
    expect(f.headline.activation.at(-1)?.value).toBe(
      f.activation.activation.at(-1)?.total
    );
  });

  it("serves the last good on a new instance whose first store read is slow", async () => {
    const store = memorySeriesStore();
    const retain = vi.fn();
    await wallPayload(now, computeWith(sources()), retain, store);
    await Promise.all(retain.mock.calls.map(([work]) => work));
    await all(await wallPayload(now, undefined, () => {}, store), {
      ...sources(),
      store,
    });

    resetWallCache(); // a new revision's first request: the store channel opens slowly
    resetSeriesCache();
    const slow: SeriesStore = {
      ...store,
      read: (name) =>
        new Promise((resolve) => setTimeout(resolve, 3_000)).then(() =>
          store.read(name)
        ),
    };
    const b = sources();
    const compute = vi.fn(computeWith(b));
    const pending = Promise.all([
      wallPayload(now, compute, () => {}, slow),
      seriesPayload("revenue", Promise.resolve(null), now, {
        ...b,
        store: slow,
      }),
    ]);
    await vi.advanceTimersByTimeAsync(3_000);
    const [wall, revenue] = await pending;
    expect(compute).not.toHaveBeenCalled();
    expect(wall.refreshing).toBeFalsy();
    expect(value(wall, "growth.wau").value).not.toBeNull();
    expect(b.query).not.toHaveBeenCalled();
    expect(revenue.gaps).toEqual({});
    expect(revenue.frames.mrr.length).toBeGreaterThan(0);
  });

  it("reports refreshing with no null points dated today while a cold refresh has no last good", async () => {
    const compute = vi.fn(() => new Promise<never>(() => {}));
    const snapshot = wallPayload(now, compute, () => {});
    const pending = series(snapshot, sources());
    await vi.advanceTimersByTimeAsync(5_000);
    const payloads = await pending;
    expect(compute).toHaveBeenCalledTimes(1);
    for (const p of payloads) {
      expect(p.refreshing).toBe(true);
      expect(p.gaps.snapshot).toBe("Snapshot refresh running");
      for (const rows of Object.values(p.frames))
        for (const row of rows)
          expect(row.date === today && row.value === null).toBe(false);
    }
    const head = payloads[0].frames;
    expect(head.wau).toEqual([{ date: through, value: null }]);
    expect(head.deltas.find((d) => d.key === "wau")?.text).toBe("—");
  });

  it("lets a second cold instance wait honestly on the instance holding the refresh", async () => {
    const store = memorySeriesStore();
    void wallPayload(
      now,
      vi.fn(() => new Promise<never>(() => {})),
      () => {},
      store
    );
    await vi.advanceTimersByTimeAsync(0);
    resetWallCache();
    const compute = vi.fn(computeWith(sources()));
    const wall = await wallPayload(now, compute, () => {}, store);
    expect(compute).not.toHaveBeenCalled();
    expect(wall.refreshing).toBe(true);
    expect(wall.metrics.every((m) => m.value == null)).toBe(true);
  });

  it("keeps a finished partial snapshot unsettled and marks retained headline stats stale", async () => {
    const s = { ...sources(), store: memorySeriesStore() };
    const wall = await computeWall(s, now);
    const partial: WallPayload = {
      ...wall,
      retryableFailures: 1,
      metrics: wall.metrics.map((m) =>
        m.id === "engagement.dau"
          ? { ...m, stale: true, retainedSince: now.toISOString() }
          : m
      ),
    };
    const head = await seriesPayload(
      "headline",
      Promise.resolve(partial),
      now,
      s
    );
    expect(head.refreshing).toBe(true);
    expect(String(head.frames.through[0].text)).toMatch(/ · 1 stat stale$/);
    const settled = await seriesPayload(
      "headline",
      Promise.resolve(wall),
      now,
      s
    );
    expect(settled.refreshing).toBe(false);
    expect(String(settled.frames.through[0].text)).not.toContain("stale");
  });

  it("keeps a failing source's previous metric, labelled stale, on every instance", async () => {
    const store = memorySeriesStore();
    const good = sources();
    const retain = vi.fn();
    await wallPayload(now, computeWith(good), retain, store);
    await Promise.all(retain.mock.calls.map(([work]) => work));
    const before = await wallPayload(now, computeWith(good), retain, store);

    vi.advanceTimersByTime(16 * 60_000);
    const failing = sources();
    failing.stripe = async () => {
      throw new Error("Stripe restricted read key unavailable");
    };
    failing.finops = async () => {
      throw new Error("FinOps aggregate query failed");
    };
    failing.billing = vi.fn(async () => null);
    await wallPayload(new Date(), computeWith(failing), retain, store);
    await Promise.all(retain.mock.calls.map(([work]) => work));
    resetWallCache(); // a cold instance sees the same retained metrics
    const after = await wallPayload(
      new Date(),
      computeWith(failing),
      retain,
      store
    );
    for (const id of ["revenue.mrr", "cost.net_day", "revenue.arpmau"]) {
      expect(value(after, id)).toMatchObject({
        value: value(before, id).value,
        stale: true,
        sourceFailure: expect.any(String),
      });
      expect(value(before, id).value).not.toBeNull();
    }
    expect(value(after, "growth.wau").stale).toBe(false);
  });
});
