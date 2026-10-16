import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { computeWall, WallPayload, WallSources } from "../wall-metrics";
import {
  assembleSeries,
  BAD_MARK,
  COHORT_WEEKS,
  GOOD_MARK,
  headlineDelta,
  GROWTH_WEEKS,
  resetSeriesCache,
  Row,
  SeriesName,
  seriesPayload,
  SeriesSources,
  STORE_FAIL_LIMIT,
} from "../wall-series";
import { resetWallCache } from "../wall-cache";
import {
  LEASE_MS,
  memorySeriesStore,
  mergeLegDoc,
  SeriesStore,
} from "../wall-series-store";
import { isoDay, shiftDay, utcDay } from "../qualified-activity";

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
  if (sql.includes("spans"))
    return stamp([
      [0, 1000],
      [1, 990],
    ]);
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
    finops: vi.fn(async () => ({
      mrr: finopsMrr,
    })),
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
    expect(rows.map((r) => r.source)).toEqual([
      "Pendant · 8",
      "Phone mic · 12",
      "None · 10",
    ]);
    expect(rows.reduce((n, r) => n + Number(r.people), 0)).toBe(
      rate.denominator
    );
    expect(rows[0].activation).toBe(75);
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
    expect(f.revenue.mrr.at(-1)).toMatchObject({
      total: value(wall, "revenue.mrr").value,
      unlimited: 600,
      plus: 400,
      source: "Live Stripe book",
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
      text: `▲ 6.6 pp${GOOD_MARK}`,
    });
    expect(headlineDelta("wau", rows(4000, 3600))).toMatchObject({
      unit: "%",
      delta: -10,
      tone: "bad",
      text: `▼ 10.0%${BAD_MARK}`,
    });
    // Cost up is bad; flat is neutral; one row has no prior.
    expect(headlineDelta("netCost", rows(2000, 2500)).tone).toBe("bad");
    expect(headlineDelta("costPerMau", rows(7, 7)).text).toBe("■ 0.0%");
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
    expect(f.retention.curve[0]).toMatchObject({ week: 0 });
    expect(f.retention.curve).toHaveLength(9);
    expect(f.retention.curve[1]).toHaveProperty("week", 1);
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

  it("keeps the headline whole when only older MAU windows time out", async () => {
    const s = { ...sources(), store: memorySeriesStore() };
    let mauReads = 0;
    s.query = vi.fn(async (sql: string) => {
      if (sql.includes("spans") && mauReads++ > 0)
        throw new Error("PostHog execution time limit exceeded (HTTP 504)");
      return query(sql);
    });
    const head = await seriesPayload("headline", Promise.resolve(null), now, s);
    expect(head.gaps).not.toHaveProperty("mauRecent");
    const revenue = await seriesPayload(
      "revenue",
      Promise.resolve(null),
      now,
      s
    );
    expect(revenue.gaps).toHaveProperty("mauHistory");
    expect(revenue.gaps).not.toHaveProperty("mauRecent");
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
