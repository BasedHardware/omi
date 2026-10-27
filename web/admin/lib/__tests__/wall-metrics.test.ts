import { beforeEach, describe, expect, it, vi } from "vitest";
import { computeWall, WALL_DEFINITIONS, WallSources } from "../wall-metrics";
import type { PlanCostHistory } from "../wall-finops";
import { INFRA_AS_OF, INFRA_MONTHLY_USD } from "../wall-cost";
import { resetWallCache, wallPayload } from "../wall-cache";
import { aggregateOrders, ShopOrder } from "../wall-shopify";
import { wallSubscriptionBook } from "../stripe-subscriptions";
import type Stripe from "stripe";
const now = new Date("2026-10-15T12:00Z");
/** The dated infra fallback the all-in stack books on days without a complete
 * fresh Mercury infra row. */
const infraDay = INFRA_MONTHLY_USD / (365.25 / 12);
const fail = async () => {
  throw new Error("unavailable");
};
const sources = (): WallSources => ({
  query: fail,
  shopify: fail,
  stripe: fail,
  billing: fail,
  planCost: fail,
  finops: fail,
  fees: fail,
});

describe("wall source and payload contracts", () => {
  beforeEach(() => {
    resetWallCache();
    vi.useRealTimers();
  });
  it("returns every contract ID with null/reason for missing sources, never fabricated zero", async () => {
    const wall = await computeWall(sources(), now);
    expect(wall.metrics).toHaveLength(WALL_DEFINITIONS.length);
    expect(
      wall.metrics.every(
        (m) => m.value === null && m.status === "null" && m.reason
      )
    ).toBe(true);
  });
  it("conserves counts and computes rates from denominators including unqualified entry users", async () => {
    const s = sources();
    s.query = async (sql) =>
      sql.includes("denominator,countIf")
        ? [
            [0, "macos", 10, 4, 2, 6, 1, 3, 5],
            [0, "ios", 20, 2, 1, 18, 3, 4, 6],
            [0, "unknown", 30, 0, 0, 30, 1, 0, 0],
            [1, "macos", 10, 2, 1, 8, 1, 1, 2],
          ]
        : sql.includes("countIf(eligible)")
        ? [
            [0, "macos", 10, 7],
            [0, "ios", 20, 10],
          ]
        : [
            [0, "macos", 3],
            [0, "ios", 4],
            [0, "android", 2],
            [1, "macos", 2],
          ];
    const wall = await computeWall(s, now);
    const get = (id: string) => wall.metrics.find((m) => m.id === id)!;
    expect(get("growth.wau").value).toBe(9);
    expect(get("growth.wau").split).toEqual({
      macos: 3,
      mobile: 6,
      other: 0,
      mcp: null,
    });
    expect(get("activation.rate").value).toBe(10);
    expect(get("activation.rate").denominator).toBe(60);
    expect(get("activation.rate").split.other).toBe(0);
    expect(get("retention.if_activated").value).toBe(50);
    expect(get("retention.established_week").value).toBeCloseTo(
      (100 * 17) / 30
    );
    expect(get("growth.wau").trend.at(-1)?.date).toBe("2026-10-14");
  });
  it("empty telemetry and zero denominators stay null", async () => {
    const s = sources();
    s.query = async () => [];
    expect(
      (await computeWall(s, now)).metrics.every((m) => m.value === null)
    ).toBe(true);
  });
  it("coalesces payload reads and invalidates at UTC midnight without restamping sources", async () => {
    const payload = await computeWall(sources(), now);
    payload.metrics[0].value = 1;
    const compute = vi.fn(async () => payload);
    const [a, b] = await Promise.all([
      wallPayload(now, compute),
      wallPayload(now, compute),
    ]);
    expect(a).toBe(b);
    expect(compute).toHaveBeenCalledTimes(1);
    expect(await wallPayload(new Date("2026-10-15T12:01Z"), compute)).toBe(a);
    await wallPayload(new Date("2026-10-16T00:00Z"), compute);
    await new Promise((resolve) => setTimeout(resolve, 0)); // lease, then compute
    expect(compute).toHaveBeenCalledTimes(2);
  });
  it("labels current Stripe / completed MAU as a dimmed proxy, not a same-cutoff close", async () => {
    const s = sources();
    s.query = async () => [[0, "macos", 10]];
    s.stripe = async () => ({
      usd: 1400,
      partial: false,
      unmappedProducts: 0,
      unsupportedItems: 1,
    });
    const wall = await computeWall(s, now);
    expect(wall.metrics.find((m) => m.id === "revenue.mrr")?.value).toBe(1400);
    expect(wall.metrics.find((m) => m.id === "revenue.mrr")?.partial).toBe(
      true
    );
    expect(wall.metrics.find((m) => m.id === "revenue.arpmau")).toMatchObject({
      value: 140,
      partial: true,
      materialGap: true,
    });
    expect(
      wall.metrics.find((m) => m.id === "revenue.arpmau")?.reason
    ).toContain("cutoff mismatch");
  });
});

describe("Shopify net weekly sales", () => {
  const money = (amount: string) => ({
    shopMoney: { amount, currencyCode: "USD" },
  });
  const order: ShopOrder = {
    test: false,
    cancelledAt: null,
    displayFinancialStatus: "PAID",
    lineItems: {
      pageInfo: { hasNextPage: false },
      nodes: [
        {
          id: "device",
          title: "Omi",
          sku: null,
          quantity: 2,
          discountedTotalSet: money("300"),
        },
        {
          id: "plan",
          title: "Omi Unlimited: 1st Year",
          sku: null,
          quantity: 1,
          discountedTotalSet: money("200"),
        },
      ],
    },
    refunds: [
      {
        refundLineItems: {
          pageInfo: { hasNextPage: false },
          nodes: [
            {
              lineItem: { id: "device" },
              quantity: 1,
              subtotalSet: money("150"),
            },
          ],
        },
      },
    ],
  };
  it("restates sale week for refunds and separates plan cash", () => {
    expect(aggregateOrders([order])).toEqual({
      units: 1,
      hardwareUsd: 150,
      prepayUsd: 200,
      unmappedLines: 0,
    });
    expect(aggregateOrders([{ ...order, test: true }]).units).toBe(0);
    expect(
      aggregateOrders([{ ...order, displayFinancialStatus: "PARTIALLY_PAID" }])
        .units
    ).toBe(0);
  });
  it("rejects truncated line/refund data and missing currency conversion", () => {
    expect(() =>
      aggregateOrders([
        {
          ...order,
          lineItems: { ...order.lineItems, pageInfo: { hasNextPage: true } },
        },
      ])
    ).toThrow("pagination");
    const copy = structuredClone(order);
    copy.lineItems.nodes[0].discountedTotalSet.shopMoney.currencyCode = "JPY";
    expect(() => aggregateOrders([copy])).toThrow("FX");
  });
});

describe("Stripe wall book", () => {
  const sub = (
    currency: string,
    amount: number,
    product = "prod_Uu6nrHIKWnnTWL"
  ) =>
    ({
      status: "active",
      metadata: {},
      items: {
        data: [
          {
            quantity: 1,
            price: {
              unit_amount: amount,
              currency,
              product,
              recurring: { interval: "month", interval_count: 1 },
            },
          },
        ],
      },
    } as Stripe.Subscription);
  it("includes unmapped prices within allowed products and keeps JPY in major yen", () => {
    const book = wallSubscriptionBook([
      sub("usd", 140000),
      sub("jpy", 4800),
      sub("usd", 100, "test"),
    ]);
    expect(book.usd).toBe(1400);
    expect(book.monthlyByCurrency.jpy).toBe(4800);
    expect(book.unsupportedItems).toBe(1);
    expect(book.unmappedProducts).toBe(1);
    expect(
      wallSubscriptionBook([sub("jpy", 4800)], { jpy: 0.0067 }).usd
    ).toBeCloseTo(32.16);
  });
  it("counts additional approved enterprise products and excludes marketplace", () => {
    vi.stubEnv("OMI_TV_PLAN_PRODUCT_IDS", "enterprise");
    const app = { ...sub("usd", 1000), metadata: { app_id: "app" } };
    expect(
      wallSubscriptionBook([sub("usd", 140000, "enterprise"), app]).usd
    ).toBe(1400);
    vi.unstubAllEnvs();
  });
});

it("does not turn unsupported or failed Stripe coverage into a zero MRR", async () => {
  const s = sources();
  s.stripe = async () => ({
    usd: 0,
    partial: false,
    unmappedProducts: 0,
    unsupportedItems: 2,
  });
  const wall = await computeWall(s, now);
  expect(wall.metrics.find((m) => m.id === "revenue.mrr")?.value).toBeNull();
});

it("uses a measured Mercury zero in the all-in stat and names the source", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true, anthropic: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(metric.reason).toContain("measured SaaS (Mercury) $0.00/day");
});

it("adds Modulate Mercury cash to the STT line and keeps Soniox cash out", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: { "2026-10-13": { soniox: 140 } },
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: { "2026-10-13": { modulate: 20, soniox: 500, deepgram: 5 } },
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // Measured Soniox + Modulate cash + Deepgram's own cash (a Soniox
  // measurement never hides another provider); the Soniox prepaid recharge
  // never stacks on its measured line.
  expect(metric.value).toBeCloseTo(100 + 140 + 20 + 5 + infraDay);
  expect(metric.reason).toContain(
    "Soniox measured $140.00/day (usage-summary line; balance series not live yet)"
  );
  expect(metric.reason).toContain("Deepgram Mercury cash $5.00/day");
  expect(metric.reason).toContain("Modulate Mercury cash $20.00/day");
});

it("uses the Soniox balance-delta day-rate once two snapshots exist", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.vendorBalance = async () => ({
    snapshots: 3,
    latestTs: "2026-10-13T14:30:00Z",
    asOf: "2026-10-13",
    spend: { "2026-10-12": 175.5, "2026-10-13": 140.25 },
    flags: {},
  });
  s.modulate = async () => ({
    byDay: {
      "2026-10-13": {
        usd: 20.5,
        seconds: 1_230_000,
        pricePerHour: 0.06,
        priceAsOf: "2026-10-18",
      },
    },
    price: 0.06,
    priceAsOf: "2026-10-18",
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(100 + 140.25 + 20.5 + infraDay);
  expect(metric.reason).toContain(
    "Soniox measured $140.25/day (prepaid-balance Δ, as-of 2026-10-13)"
  );
  expect(metric.reason).toContain(
    "Modulate modelled $20.50/day (measured volume × $0.06/h, price as-of 2026-10-18)"
  );
  // no Mercury modulate cash in the window: the reconciliation shows -100%
  expect(metric.reason).toContain("Modulate 30d reconciliation");
  expect(metric.reason).toContain("-100.0%");
});

it("flags a baseline-reset day and keeps the constant only below two snapshots", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.vendorBalance = async () => ({
    snapshots: 3,
    latestTs: "2026-10-13T14:30:00Z",
    asOf: "2026-10-13",
    spend: { "2026-10-13": null },
    flags: { "2026-10-13": "baseline_reset" },
  });
  const wall = await computeWall(s, now);
  const reset = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // The reset day keeps Soniox spend in the total via the dated estimate —
  // never a $0 leg that silently drops all-in cost (Luna r2 P1).
  expect(reset.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(reset.reason).toContain(
    "Soniox balance reset on 2026-10-13: day unmeasured, new baseline taken; the dated estimate covers the day, never $0"
  );

  s.vendorBalance = async () => ({
    snapshots: 1,
    latestTs: "2026-10-13T14:30:00Z",
    asOf: "2026-10-13",
    spend: {},
    flags: {},
  });
  const wall2 = await computeWall(s, now);
  const constant = wall2.metrics.find((m) => m.id === "cost.net_day")!;
  expect(constant.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(constant.reason).toContain("1/2 balance snapshots");
});

it("reports both vendor STT legs unavailable when their tables are dark", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.vendorBalance = fail;
  s.modulate = fail;
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.reason).toContain("Soniox measured line UNAVAILABLE");
  expect(metric.reason).toContain("Modulate Mercury cash");
  expect(metric.reason).toContain("modelled line unavailable");
  expect(metric.reason).toContain(
    "missing: Stripe processing fees, Soniox measured STT, Modulate modelled STT"
  );
});

it("shows Stripe fees as unavailable with the missing scope, never a guess", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: { costSource: "billing", partial: false, coverage: {} },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
    saasAnnualPartial: {},
    sttCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.reason).toContain("Stripe fees UNAVAILABLE");
  expect(metric.reason).toContain("missing: Stripe processing fees");
  expect(metric.value).toBeCloseTo(
    100 + 5_300 / (365.25 / 12) + 4_800 / (365.25 / 12) + infraDay
  );
});

it("counts the Anthropic invoice only when the admin API reports spend", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0, anthropic: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { anthropic: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
    saasAnnualPartial: {},
    sttCash: {},
  });
  const wall = await computeWall(s, now);
  const zero = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(zero.reason).toContain("Anthropic $0 API (team seats are SaaS cash)");
  expect(zero.value).toBeCloseTo(
    100 + 5_300 / (365.25 / 12) + 4_800 / (365.25 / 12) + infraDay
  );
});

it("uses the FinOps book snapshot for MRR and cross-checks the live read", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 10]];
  s.finops = async () => ({
    mrr: {
      "2026-10-13": { unlimited_v2: 60_000, plus: 15_610 },
      "2026-10-14": { unlimited_v2: 61_000, plus: 15_000 },
    },
    paying: { "2026-10-13": 3_100, "2026-10-14": 3_209 },
    payingCustomers: { "2026-10-13": 3_050, "2026-10-14": 3_160 },
    nonUsdPaying: { "2026-10-13": 0, "2026-10-14": 0 },
    refreshed: {
      "2026-10-13": "2026-10-13T14:36:00Z",
      "2026-10-14": "2026-10-14T14:36:00Z",
    },
  });
  s.stripe = async () => ({
    usd: 80_000,
    partial: false,
    unmappedProducts: 0,
    unsupportedItems: 0,
  });
  const wall = await computeWall(s, now);
  const mrr = wall.metrics.find((m) => m.id === "revenue.mrr")!;
  // The latest complete-day book (D-1 = 10-14), not today's half-written one.
  // The denominator is distinct paying customers (3,160), not the item sum
  // (3,209) — the two JPY-carrying multi-item payers must not double-count.
  expect(mrr.value).toBe(76_000);
  expect(mrr.denominator).toBe(3_160);
  expect(String(mrr.dataThrough).slice(0, 10)).toBe("2026-10-14");
  expect(mrr.reason).toContain("FinOps Stripe book snapshot 2026-10-14");
  expect(mrr.reason).toContain("coupons applied");
  expect(mrr.reason).toContain("+5.3%");
  expect(mrr.stale).toBe(false);
});

it("falls back to the live book with its gaps named when FinOps is down", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 10]];
  s.stripe = async () => ({
    usd: 1_400,
    partial: false,
    unmappedProducts: 0,
    unsupportedItems: 1,
  });
  const wall = await computeWall(s, now);
  const mrr = wall.metrics.find((m) => m.id === "revenue.mrr")!;
  expect(mrr.value).toBe(1_400);
  expect(mrr.reason).toContain("FinOps book unavailable");
});

const billingWindow = (now: Date) => {
  const day = (offset: number) =>
    new Date(now.getTime() - offset * 86_400_000).toISOString().slice(0, 10);
  return Array.from({ length: 33 }, (_, k) => ({
    date: day(k + 1),
    total: 100,
    components: { gcpInfra: 100, vertexLlm: 0 },
  }));
};

it("derives software cost per paying customer with a per-plan variable breakdown", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 1_000]]; // MAU for cost/MAU
  s.billing = async () => ({
    daily: billingWindow(now),
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => {
    const plans: PlanCostHistory["plans"] = {};
    for (const d of billingWindow(now)) {
      plans[d.date] = {
        unlimited_v2: { usd: 1, users: 2, varUsd: 300, varUsers: 100 },
        basic: { usd: 1, users: 2, varUsd: 100, varUsers: 100 },
      };
    }
    return {
      plans,
      sttMeasured: {},
      saasMeasured: {},
      saasAnnualPartial: {},
      sttCash: {},
    };
  };
  s.finops = async () => ({
    mrr: { "2026-10-14": { unlimited_v2: 76_000 } },
    paying: { "2026-10-14": 3_209 },
    payingCustomers: { "2026-10-14": 3_160 },
    nonUsdPaying: { "2026-10-14": 0 },
    refreshed: { "2026-10-14": "2026-10-14T14:36:00Z" },
  });
  const wall = await computeWall(s, now);
  const perCustomer = wall.metrics.find(
    (m) => m.id === "cost.per_customer_month"
  )!;
  // 30 settled days × $100 GCP + STT/SaaS constants ÷ the SAME-WINDOW payer
  // measure. The only book snapshot sits at the window's exclusive end
  // (2026-10-14), so the window-end count applies, stated in the reason.
  const windowTotal =
    30 * 100 +
    30 * (5_300 / (365.25 / 12)) +
    30 * (4_800 / (365.25 / 12)) +
    30 * infraDay;
  expect(perCustomer.numerator).toBeCloseTo(windowTotal);
  expect(perCustomer.value).toBeCloseTo(windowTotal / 3_160);
  expect(perCustomer.denominator).toBe(3_160);
  expect(perCustomer.reason).toContain(
    "denominator = window-end paying-customer snapshot 2026-10-14"
  );
  expect(perCustomer.breakdown).toMatchObject({
    unlimited_v2: (300 / 100) * 30.4375,
    basic: (100 / 100) * 30.4375,
  });
  expect(
    wall.metrics.find((m) => m.id === "cost.per_mau_month")!.value
  ).toBeCloseTo(windowTotal / 1_000);
});

it("never reads a stale Soniox series as $0 spend or a reset (Luna P1)", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  // The pull stopped on 10-10: the series is live (3 snapshots) but covers
  // nothing past 10-10, while the wall's settled cutoff is 10-13.
  s.vendorBalance = async () => ({
    snapshots: 3,
    latestTs: "2026-10-10T14:30:00Z",
    asOf: "2026-10-10",
    spend: { "2026-10-09": 175.5, "2026-10-10": 140.25 },
    flags: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // The uncovered day shows the dated console constant — never $0, never a reset.
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(metric.reason).toContain(
    "Soniox balance series does not cover 2026-10-13"
  );
  expect(metric.reason).toContain("not $0 spend");
  expect(metric.reason).not.toContain("balance reset on 2026-10-13");
  expect(metric.reason).toContain("STALE");
});

it("labels measured Stripe fees partial while foreign-currency rows exist (Luna P2)", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.fees = async () => ({
    fees: { "2026-10-13": 12.5 },
    foreign: { "2026-10-12": 3, "2026-10-13": 2 },
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(
    100 + 5_300 / (365.25 / 12) + 12.5 + infraDay
  );
  expect(metric.reason).toContain("measured Stripe fees $12.50/day");
  expect(metric.reason).toContain(
    "partial: 5 foreign-currency fee rows in the 30d window counted, not converted"
  );
});

it("labels a measured Mercury SaaS day partial while history is under 12 months (Luna P2)", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    // The amortized Mercury value stays the run rate; it is just labelled
    // partial until the ledger covers a full year.
    saasMeasured: { "2026-10-13": 12.5 },
    saasAnnualPartial: { "2026-10-13": "history_under_12_months" },
    sttCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // Measured SaaS replaces the dated constant; STT keeps its own estimate.
  expect(metric.value).toBeCloseTo(
    100 + 5_300 / (365.25 / 12) + 12.5 + infraDay
  );
  expect(metric.reason).toContain("measured SaaS (Mercury) $12.50/day");
  expect(metric.reason).toContain(
    "partial: SaaS ledger history under 12 months"
  );
  expect(metric.reason).toContain("one-off vendors amortized ÷12, estimated");
});

it("counts the measured Mercury infra run rate in the all-in stat", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: { "2026-10-13": { modulate: 20 } },
  });
  s.infra = async () => ({
    infraMeasured: { "2026-10-13": 32.87 },
    infraAnnualPartial: {},
    infraStripeFeesCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // The infra line adds on top of GCP and the STT legs exactly once; STT cash
  // and the infra run rate are separate lines and never collapse.
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + 20 + 32.87);
  expect(metric.reason).toContain(
    "measured Infra non-GCP (Mercury) $32.87/day"
  );
  expect(metric.reason).toContain("Modulate Mercury cash $20.00/day");
});

it("floors a partial infra run rate at the dated fallback, still labelled partial (Luna r2 P1)", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  // Before the 400-day backfill the ledger cannot see the 2026-01-08 Modal
  // wire: the row shows the ≈$114/mo Cloudflare + Hetzner slice only.
  s.infra = async () => ({
    infraMeasured: { "2026-10-13": 3.75 },
    infraAnnualPartial: { "2026-10-13": "history_under_12_months" },
    infraStripeFeesCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // The $1,114/mo constant (which carries the known wire) floors the partial
  // slice — never the ≈$1,000/mo undercount — and the line says so, still
  // labelled partial with the producer's reason.
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(metric.reason).toContain(
    `Infra (non-GCP) $${infraDay.toFixed(
      2
    )}/day: dated $${INFRA_MONTHLY_USD}/mo fallback as of ${INFRA_AS_OF} floors the partial Mercury run rate $3.75/day`
  );
  expect(metric.reason).toContain(
    "partial: infra ledger history under 12 months"
  );
  expect(metric.reason).toContain("one-off vendors amortized ÷12, estimated");
  expect(metric.reason).not.toContain("measured Infra non-GCP");
  expect(metric.reason).not.toContain("STALE");
});

it("uses a partial infra run rate that rises above the dated fallback, still labelled partial", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.infra = async () => ({
    infraMeasured: { "2026-10-13": 50 },
    infraAnnualPartial: { "2026-10-13": "history_under_12_months" },
    infraStripeFeesCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  // The measured run rate is not hidden behind the constant once it exceeds
  // it; the partial label stays until the producer calls history complete.
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + 50);
  expect(metric.reason).toContain(
    "measured Infra non-GCP (Mercury) $50.00/day (partial: infra ledger history under 12 months"
  );
  expect(metric.reason).not.toContain("floors the partial");
});

it("counts Mercury stripe_fees cash on the infra line only while the measured fee line is dark (Luna r2 P2)", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.infra = async () => ({
    infraMeasured: { "2026-10-13": 32.87 },
    infraAnnualPartial: {},
    infraStripeFeesCash: { "2026-10-13": 4 },
  });
  // Fee table dark (default `fail`): the fee cash rejoins infra, labelled on
  // both lines so neither reads as if the money vanished.
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + 32.87 + 4);
  expect(metric.reason).toContain(
    "measured Infra non-GCP (Mercury) $32.87/day + Mercury stripe_fees cash $4.00/day counted here (measured Stripe fee line unavailable for the day)"
  );
  expect(metric.reason).toContain(
    "Stripe fees UNAVAILABLE (finops key lacks balance-transaction read scope); Mercury stripe_fees cash counted on the infra line"
  );
  // Measured fee line present: it owns the money; infra drops the cash.
  s.fees = async () => ({ fees: { "2026-10-13": 12.5 }, foreign: {} });
  const wall2 = await computeWall(s, now);
  const metric2 = wall2.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric2.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + 32.87 + 12.5);
  expect(metric2.reason).toContain(
    "measured Infra non-GCP (Mercury) $32.87/day"
  );
  expect(metric2.reason).toContain("measured Stripe fees $12.50/day");
  expect(metric2.reason).not.toContain("stripe_fees cash");
});

it("falls back to the dated infra constant and names a dark table a missing line, never $0", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 0 },
    saasAnnualPartial: {},
    sttCash: {},
  });
  // The table is dark until the first Mercury load after it ships.
  s.infra = fail;
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(metric.reason).toContain(
    `Infra (non-GCP) fixed $${INFRA_MONTHLY_USD}/mo estimate as of ${INFRA_AS_OF}`
  );
  expect(metric.reason).toContain("Mercury infra run-rate table unavailable");
  expect(metric.reason).toContain(
    "Infra (non-GCP) run rate unavailable (mercury_infra_non_gcp_daily dark)"
  );
  // A day with no complete fresh row (source healthy) keeps the same dated
  // constant without a missing line: labelled, never silent $0.
  s.infra = async () => ({
    infraMeasured: {},
    infraAnnualPartial: {},
    infraStripeFeesCash: {},
  });
  const wall2 = await computeWall(s, now);
  const metric2 = wall2.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric2.value).toBeCloseTo(100 + 5_300 / (365.25 / 12) + infraDay);
  expect(metric2.reason).toContain("no complete fresh Mercury infra row");
  expect(metric2.reason).not.toContain("missing: Infra");
});

it("includes the infra run rate in the software cost per paying customer", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 1_000]];
  s.billing = async () => ({
    daily: billingWindow(now),
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
    saasAnnualPartial: {},
    sttCash: {},
  });
  s.infra = async () => ({
    infraMeasured: Object.fromEntries(
      billingWindow(now).map((d) => [d.date, 32.87])
    ),
    infraAnnualPartial: {},
    infraStripeFeesCash: {},
  });
  s.finops = async () => ({
    mrr: { "2026-10-14": { unlimited_v2: 76_000 } },
    paying: { "2026-10-14": 3_209 },
    payingCustomers: { "2026-10-14": 3_160 },
    nonUsdPaying: { "2026-10-14": 0 },
    refreshed: { "2026-10-14": "2026-10-14T14:36:00Z" },
  });
  const wall = await computeWall(s, now);
  const perCustomer = wall.metrics.find(
    (m) => m.id === "cost.per_customer_month"
  )!;
  const windowTotal =
    30 * 100 +
    30 * (5_300 / (365.25 / 12)) +
    30 * (4_800 / (365.25 / 12)) +
    30 * 32.87;
  expect(perCustomer.numerator).toBeCloseTo(windowTotal);
  expect(perCustomer.value).toBeCloseTo(windowTotal / 3_160);
});

it("labels the measured SaaS line with the producer's other partial reason verbatim", async () => {
  const s = sources();
  s.query = async () => [];
  s.billing = async () => ({
    daily: [
      {
        date: "2026-10-13",
        total: 100,
        components: { gcpInfra: 100, vertexLlm: 0 },
      },
    ],
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: { "2026-10-13": 12.5 },
    saasAnnualPartial: { "2026-10-13": "uncategorized_above_threshold" },
    sttCash: {},
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.reason).toContain("(partial: uncategorized_above_threshold)");
});

it("marks MRR partial when the book carries non-USD payers (Luna P1: no yen-as-dollars)", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 10]];
  s.finops = async () => ({
    mrr: { "2026-10-14": { unlimited_v2: 76_000 } },
    paying: { "2026-10-14": 3_209 },
    payingCustomers: { "2026-10-14": 3_160 },
    nonUsdPaying: { "2026-10-14": 2 },
    refreshed: { "2026-10-14": "2026-10-14T14:36:00Z" },
  });
  const wall = await computeWall(s, now);
  const mrr = wall.metrics.find((m) => m.id === "revenue.mrr")!;
  expect(mrr.value).toBe(76_000);
  expect(mrr.partial).toBe(true);
  expect(mrr.reason).toContain(
    "2 non-USD paying subscriptions counted but excluded from MRR (native currency, no implicit FX)"
  );
});

it("uses the average of daily paying customers over the cost window (Luna P1)", async () => {
  const s = sources();
  s.query = async () => [[0, "macos", 1_000]];
  s.billing = async () => ({
    daily: billingWindow(now),
    generatedAt: now.getTime(),
    summary: {
      costSource: "billing",
      partial: false,
      coverage: { openai: true },
    },
  });
  s.planCost = async () => ({
    plans: {},
    sttMeasured: {},
    saasMeasured: {},
    saasAnnualPartial: {},
    sttCash: {},
  });
  // Three book snapshots inside the window (it ends 2026-10-14 exclusive):
  // the average of the daily counts, never the latest snapshot alone.
  s.finops = async () => ({
    mrr: {
      "2026-10-11": { unlimited_v2: 76_000 },
      "2026-10-12": { unlimited_v2: 76_000 },
      "2026-10-13": { unlimited_v2: 76_000 },
    },
    paying: { "2026-10-13": 3_209 },
    payingCustomers: {
      "2026-10-11": 3_000,
      "2026-10-12": 3_200,
      "2026-10-13": 3_400,
    },
    nonUsdPaying: { "2026-10-13": 0 },
    refreshed: { "2026-10-13": "2026-10-13T14:36:00Z" },
  });
  const wall = await computeWall(s, now);
  const perCustomer = wall.metrics.find(
    (m) => m.id === "cost.per_customer_month"
  )!;
  const windowTotal =
    30 * 100 +
    30 * (5_300 / (365.25 / 12)) +
    30 * (4_800 / (365.25 / 12)) +
    30 * infraDay;
  expect(perCustomer.value).toBeCloseTo(windowTotal / 3_200);
  expect(perCustomer.denominator).toBe(3_200);
  expect(perCustomer.reason).toContain(
    "denominator = average of 3 daily paying-customer snapshots inside the window"
  );
});
