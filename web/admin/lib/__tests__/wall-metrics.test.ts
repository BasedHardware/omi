import { beforeEach, describe, expect, it, vi } from "vitest";
import { computeWall, WALL_DEFINITIONS, WallSources } from "../wall-metrics";
import { resetWallCache, wallPayload } from "../wall-cache";
import { aggregateOrders, ShopOrder } from "../wall-shopify";
import { wallSubscriptionBook } from "../stripe-subscriptions";
import type Stripe from "stripe";
const now = new Date("2026-10-15T12:00Z");
const fail = async () => {
  throw new Error("unavailable");
};
const sources = (): WallSources => ({
  query: fail,
  shopify: fail,
  stripe: fail,
  billing: fail,
  planCost: fail,
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
  });
  const wall = await computeWall(s, now);
  const metric = wall.metrics.find((m) => m.id === "cost.net_day")!;
  expect(metric.value).toBeCloseTo(100 + 5_300 / (365.25 / 12));
  expect(metric.reason).toContain("measured SaaS (Mercury): $0.00/day");
});
