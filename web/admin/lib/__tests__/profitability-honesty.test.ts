import { beforeEach, describe, expect, it, vi } from "vitest";

// Profitability honesty: the April-era per-user cost assumptions must never
// masquerade as measurements. In billing mode a day with no active users has
// no cost-per-user at all (null), and the summary averages skip those days
// instead of averaging them in as $0. The legacy estimated path keeps the old
// fallback, and says so via costSource:"estimated".

vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));
vi.mock("@/lib/posthog", () => ({
  withRowLimit: (q: string) =>
    `SELECT * FROM (\n${q}\n) AS _row_limit_guard\nLIMIT 50000`,
}));
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
    collectionGroup: () => ({
      select: () => ({ get: async () => ({ docs: [] }) }),
    }),
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
      `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(
        2,
        "0"
      )}-${String(d.getUTCDate()).padStart(2, "0")}`
    );
  }
  return out;
}

function billingPayload(dates: string[]) {
  return {
    daily: dates.map((date) => ({
      date,
      desktop: 60,
      mobile: 40,
      unknown: 0,
      total: 100,
    })),
    summary: {
      costSource: "billing",
      assumptions: { overheadMonthlyUsd: 57447 },
    },
  };
}

async function loadRoute() {
  vi.resetModules();
  return await import("@/app/api/omi/stats/profitability/route");
}

beforeEach(() => {
  vi.clearAllMocks();
  // No PostHog credentials: both active-user legs return null, so
  // every day in the window has zero active users on both platforms.
  delete process.env.POSTHOG_PERSONAL_API_KEY;
  delete process.env.POSTHOG_PROJECT_ID;
  delete process.env.POSTHOG_HOST;
});

describe("profitability cache key", () => {
  it("defaults to the same key precompute writes when no cost params are given", async () => {
    const { parseProfitabilityParams, profitabilityCacheKey } =
      await loadRoute();

    // What the GET handler builds for `?days=30` (or for no params at all).
    const fromRequest = parseProfitabilityParams(
      new URLSearchParams("days=30")
    );
    const fromNothing = parseProfitabilityParams(new URLSearchParams());
    // What precompute now writes.
    const fromPrecompute = parseProfitabilityParams(
      new URLSearchParams({ days: "30" })
    );

    const key = profitabilityCacheKey(
      fromRequest.days,
      fromRequest.desktopCost,
      fromRequest.mobileCost
    );
    expect(key).toBe("profitability:v1:30:0.2:0.2");
    expect(
      profitabilityCacheKey(
        fromNothing.days,
        fromNothing.desktopCost,
        fromNothing.mobileCost
      )
    ).toBe(key);
    expect(
      profitabilityCacheKey(
        fromPrecompute.days,
        fromPrecompute.desktopCost,
        fromPrecompute.mobileCost
      )
    ).toBe(key);
  });
});

describe("computeProfitability cost-per-user honesty", () => {
  it("reports null, not $0.20, for a zero-active day in billing mode", async () => {
    const dates = dayKeys(DAYS);
    mockInfra.mockResolvedValue(billingPayload(dates));
    const { computeProfitability } = await loadRoute();

    const payload = await computeProfitability({
      days: DAYS,
      desktopCost: 0.2,
      mobileCost: 0.2,
    });

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
      daily: dates.map((date) => ({
        date,
        desktop: 0,
        mobile: 0,
        unknown: 0,
        total: 0,
      })),
      summary: {
        costSource: "estimated",
        assumptions: { overheadMonthlyUsd: 57447 },
      },
    });
    const { computeProfitability } = await loadRoute();

    const payload = await computeProfitability({
      days: DAYS,
      desktopCost: 0.2,
      mobileCost: 0.2,
    });

    expect(payload.summary.assumptions.costSource).toBe("estimated");
    for (const row of payload.costPerUser) {
      expect(row.desktop).toBe(0.2);
      expect(row.mobile).toBe(0.2);
      expect(row.total).toBe(0.2);
    }
    expect(payload.summary.avgCostPerUserDesktop).toBe(0.2);
    expect(payload.summary.avgCostPerUserMobile).toBe(0.2);
  });

  it("uses PostHog mobile actives for measured billing rates", async () => {
    const dates = dayKeys(DAYS);
    mockInfra.mockResolvedValue(billingPayload(dates));
    process.env.POSTHOG_PERSONAL_API_KEY = "phk";
    process.env.POSTHOG_PROJECT_ID = "1";
    process.env.POSTHOG_HOST = "https://posthog.test";
    const fetchMock = vi.fn(async (url: any, init: any) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      const q = String(body?.query?.query ?? "");
      const mobile = q.includes("$os_name IN ('iOS','Android')");
      const rows = q.includes("count(DISTINCT distinct_id)")
        ? dates.map((d) => [d, mobile ? 20 : 10])
        : mobile
        ? [["mobile-uid"]]
        : [["desktop-uid"]];
      return {
        ok: true,
        json: async () => ({ results: rows }),
        text: async () => "",
      } as any;
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      const { computeProfitability } = await loadRoute();
      const payload = await computeProfitability({
        days: DAYS,
        desktopCost: 0.2,
        mobileCost: 0.2,
      });

      expect(fetchMock).toHaveBeenCalledTimes(4);
      const queries = fetchMock.mock.calls.map(([url, init]) => {
        expect(url).toBe("https://posthog.test/api/projects/1/query/");
        expect(init.method).toBe("POST");
        expect(init.headers.Authorization).toBe("Bearer phk");
        return JSON.parse(String(init.body)).query.query as string;
      });
      expect(
        queries.filter((q) => q.includes("$os_name IN ('iOS','Android')"))
      ).toHaveLength(2);
      expect(
        queries.filter((q) => q.includes("$os_name = 'macOS'"))
      ).toHaveLength(2);
      expect(queries.every((q) => q.includes("SELECT * FROM ("))).toBe(true);
      expect(
        queries.find(
          (q) =>
            q.includes("SELECT DISTINCT distinct_id") && q.includes("'iOS'")
        )
      ).toContain("interval 90 day");
      expect(payload.summary.sources.posthogMobile).toBe(true);
      expect(
        payload.activeUsers.every(
          (row) => row.mobile === 20 && row.desktop === 10
        )
      ).toBe(true);
      // 10 desktop actives, $60 desktop cost -> $6.00/user, measured.
      for (const row of payload.costPerUser) {
        expect(row.desktop).toBe(6);
        expect(row.mobile).toBe(2); // $40 over 20 mobile actives
        expect(row.total).toBe(3.33); // $100 over 30 total actives
      }
      expect(payload.summary.avgCostPerUserDesktop).toBe(6);
      expect(payload.summary.avgCostPerUserMobile).toBe(2);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
