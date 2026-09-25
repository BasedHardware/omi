import { beforeEach, describe, expect, it, vi } from "vitest";

// Profitability honesty: the April-era per-user cost assumptions must never
// masquerade as measurements. In billing mode a day with no active users has
// no cost-per-user at all (null), and the summary averages skip those days
// instead of averaging them in as $0. The legacy estimated path keeps the old
// fallback, and says so via costSource:"estimated".

vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));
vi.mock("@/lib/posthog", () => ({ withRowLimit: (q: string) => q }));
vi.mock("@/lib/stripe", () => ({ getOptionalStripe: () => null }));
vi.mock("@/lib/stripe-subscriptions", () => ({
  MRR_STATUSES: ["active"],
  fetchOmiSubscriptions: vi.fn(async () => ({ subscriptions: [] })),
  monthlyAmount: () => 0,
}));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(async () => null),
  setPayload: vi.fn(async () => {}),
}));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({
    collectionGroup: () => ({ select: () => ({ get: async () => ({ docs: [] }) }) }),
  }),
  getAdminAuth: () => ({
    listUsers: async () => ({ users: [], pageToken: undefined }),
  }),
}));

const mockInfra = vi.fn();
vi.mock("@/app/api/omi/stats/infra-costs/route", () => ({
  computeInfraCosts: (...args: unknown[]) => mockInfra(...args),
}));

const DAYS = 3;

function dayKeys(days: number): string[] {
  const out: string[] = [];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(
      `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`,
    );
  }
  return out;
}

function billingPayload(dates: string[]) {
  return {
    daily: dates.map((date) => ({ date, desktop: 60, mobile: 40, unknown: 0, total: 100 })),
    summary: { costSource: "billing", assumptions: { overheadMonthlyUsd: 57447 } },
  };
}

async function loadRoute() {
  vi.resetModules();
  return await import("@/app/api/omi/stats/profitability/route");
}

beforeEach(() => {
  vi.clearAllMocks();
  // No PostHog / Mixpanel credentials: both active-user legs return null, so
  // every day in the window has zero active users on both platforms.
  delete process.env.POSTHOG_PERSONAL_API_KEY;
  delete process.env.POSTHOG_PROJECT_ID;
  delete process.env.MIXPANEL_SECRET;
});

describe("profitability cache key", () => {
  it("defaults to the same key precompute writes when no cost params are given", async () => {
    const { parseProfitabilityParams, profitabilityCacheKey } = await loadRoute();

    // What the GET handler builds for `?days=30` (or for no params at all).
    const fromRequest = parseProfitabilityParams(new URLSearchParams("days=30"));
    const fromNothing = parseProfitabilityParams(new URLSearchParams());
    // What precompute now writes.
    const fromPrecompute = parseProfitabilityParams(new URLSearchParams({ days: "30" }));

    const key = profitabilityCacheKey(
      fromRequest.days,
      fromRequest.desktopCost,
      fromRequest.mobileCost,
    );
    expect(key).toBe("profitability:v1:30:0.2:0.2");
    expect(
      profitabilityCacheKey(fromNothing.days, fromNothing.desktopCost, fromNothing.mobileCost),
    ).toBe(key);
    expect(
      profitabilityCacheKey(
        fromPrecompute.days,
        fromPrecompute.desktopCost,
        fromPrecompute.mobileCost,
      ),
    ).toBe(key);
  });
});

describe("computeProfitability cost-per-user honesty", () => {
  it("reports null, not $0.20, for a zero-active day in billing mode", async () => {
    const dates = dayKeys(DAYS);
    mockInfra.mockResolvedValue(billingPayload(dates));
    const { computeProfitability } = await loadRoute();

    const payload = await computeProfitability({ days: DAYS, desktopCost: 0.2, mobileCost: 0.2 });

    expect(payload.summary.assumptions.costSource).toBe("real");
    expect(payload.costPerUser).toHaveLength(DAYS);
    for (const row of payload.costPerUser) {
      expect(row.desktop).toBeNull();
      expect(row.mobile).toBeNull();
      expect(row.total).toBeNull();
    }
    // The cost series itself is still the measured billing spend.
    expect(payload.cost.every((c) => c.total === 100)).toBe(true);
    // Averages skip the null days rather than averaging them in as 0.
    expect(payload.summary.avgCostPerUserDesktop).toBeNull();
    expect(payload.summary.avgCostPerUserMobile).toBeNull();
  });

  it("keeps the labeled per-user assumption on the legacy estimated path", async () => {
    const dates = dayKeys(DAYS);
    mockInfra.mockResolvedValue({
      daily: dates.map((date) => ({ date, desktop: 0, mobile: 0, unknown: 0, total: 0 })),
      summary: { costSource: "estimated", assumptions: { overheadMonthlyUsd: 57447 } },
    });
    const { computeProfitability } = await loadRoute();

    const payload = await computeProfitability({ days: DAYS, desktopCost: 0.2, mobileCost: 0.2 });

    expect(payload.summary.assumptions.costSource).toBe("estimated");
    for (const row of payload.costPerUser) {
      expect(row.desktop).toBe(0.2);
      expect(row.mobile).toBe(0.2);
      expect(row.total).toBe(0.2);
    }
    expect(payload.summary.avgCostPerUserDesktop).toBe(0.2);
    expect(payload.summary.avgCostPerUserMobile).toBe(0.2);
  });

  it("computes a real rate when the platform has active users", async () => {
    const dates = dayKeys(DAYS);
    mockInfra.mockResolvedValue(billingPayload(dates));
    process.env.POSTHOG_PERSONAL_API_KEY = "phk";
    process.env.POSTHOG_PROJECT_ID = "1";
    const fetchMock = vi.fn(async (url: any, init: any) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const q = String(body?.query?.query ?? "");
      // The per-day active-users query; the uid query returns nothing.
      const rows = q.includes("count(DISTINCT distinct_id)")
        ? dates.map((d) => [d, 10])
        : [];
      return { ok: true, json: async () => ({ results: rows }), text: async () => "" } as any;
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      const { computeProfitability } = await loadRoute();
      const payload = await computeProfitability({ days: DAYS, desktopCost: 0.2, mobileCost: 0.2 });

      // 10 desktop actives, $60 desktop cost -> $6.00/user, measured.
      for (const row of payload.costPerUser) {
        expect(row.desktop).toBe(6);
        expect(row.mobile).toBeNull(); // no mobile actives, no invented rate
        expect(row.total).toBe(10); // $100 over 10 total actives
      }
      expect(payload.summary.avgCostPerUserDesktop).toBe(6);
      expect(payload.summary.avgCostPerUserMobile).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
