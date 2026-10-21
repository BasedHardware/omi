import { beforeEach, describe, expect, it, vi } from "vitest";

// Route-level fall-through for the staleness bound: when the payload cache
// holds no doc within the freshness bound (missing OR older than
// MAX_PRECOMPUTED_AGE_MS — both surface as a null from getPayload), the GET
// handlers must recompute inline and refresh the cache, never fail and never
// serve the stale doc. Fresh-hit behavior: the cached doc is served verbatim
// without touching the compute path.

type CacheHit = { data: unknown; freshAt: number };

const getPayloadMock = vi.hoisted(() =>
  vi.fn(
    async (
      _key: string,
      _opts?: { maxAgeMs?: number }
    ): Promise<CacheHit | null> => null
  )
);
const setPayloadMock = vi.hoisted(() =>
  vi.fn(async (_key: string, _data: unknown): Promise<void> => {})
);

import type * as PayloadCacheNs from "@/lib/payload-cache";
type PayloadCacheModule = typeof PayloadCacheNs;
vi.mock("@/lib/payload-cache", async (importOriginal) => {
  const actual = await importOriginal<PayloadCacheModule>();
  return {
    ...actual,
    getPayload: getPayloadMock,
    setPayload: setPayloadMock,
  };
});
vi.mock("@/lib/auth", () => ({
  verifyAdmin: vi.fn(async () => ({ uid: "t" })),
}));
vi.mock("@/lib/posthog", () => ({ withRowLimit: (q: string) => q }));
vi.mock("@/lib/stripe", () => ({ getOptionalStripe: () => null }));
vi.mock("@/lib/stripe-subscriptions", () => ({
  MRR_STATUSES: ["active"],
  fetchOmiSubscriptions: vi.fn(async () => ({ subscriptions: [] })),
  monthlyAmount: () => 0,
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
const mockGcp = vi.hoisted(() => vi.fn());
vi.mock("@/lib/services/gcp-billing", () => ({
  fetchGcpBilling: (...args: unknown[]) => mockGcp(...args),
}));
vi.mock("@/lib/services/provider-costs", () => ({
  fetchAnthropicDailyCosts: vi.fn(async () => []),
  fetchOpenAiDailyCosts: vi.fn(async () => []),
}));
vi.mock("@/lib/services/gateway-ledger", () => ({
  fetchGatewayLedgerDays: vi.fn(async () => []),
}));

import { MAX_PRECOMPUTED_AGE_MS } from "@/lib/payload-cache";
import { GET as profitabilityGET } from "@/app/api/omi/stats/profitability/route";
import { GET as infraCostsGET } from "@/app/api/omi/stats/infra-costs/route";

const GCP_SNAPSHOT = {
  daily: [{ date: "2026-08-20", netUsd: 1000, grossUsd: 1200, llmNetUsd: 400 }],
  services: [{ service: "Vertex AI", netUsd: 900, isLlm: true }],
  windowStart: "2026-08-20",
  windowEnd: "2026-08-20",
};

function request(path: string) {
  return { url: `https://admin.test${path}` } as never;
}

beforeEach(() => {
  vi.clearAllMocks();
  getPayloadMock.mockResolvedValue(null);
  delete process.env.ADMIN_INFRA_OVERHEAD_MONTHLY;
  delete process.env.ADMIN_PLATFORM_COST_SHARES_JSON;
  delete process.env.ADMIN_SERVICE_COSTS_JSON;
  delete process.env.POSTHOG_PERSONAL_API_KEY;
  delete process.env.POSTHOG_PROJECT_ID;
  delete process.env.MIXPAL_SECRET;
  mockGcp.mockResolvedValue(GCP_SNAPSHOT);
});

describe("profitability GET staleness bound", () => {
  const KEY = "profitability:v1:30:0.2:0.2";

  it("reads the cache with the freshness bound", async () => {
    await profitabilityGET(request("/api/omi/stats/profitability?days=30"));

    expect(getPayloadMock).toHaveBeenCalledWith(KEY, {
      maxAgeMs: MAX_PRECOMPUTED_AGE_MS,
    });
  });

  it("serves a doc within the bound verbatim, without recomputing", async () => {
    const freshAt = Date.now() - 60 * 60 * 1000;
    getPayloadMock.mockResolvedValue({
      data: { days: 30, marker: "precomputed" },
      freshAt,
    });

    const res = await profitabilityGET(
      request("/api/omi/stats/profitability?days=30")
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual({ days: 30, marker: "precomputed", freshAt });
    expect(setPayloadMock).not.toHaveBeenCalled();
  });

  it("recomputes inline and refreshes the cache when the doc is stale or missing", async () => {
    // getPayload → null is also what a doc older than the bound returns, so
    // this is the frozen-legacy-key path (stale doc) as much as the cold path.
    const res = await profitabilityGET(
      request("/api/omi/stats/profitability?days=30")
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.marker).toBeUndefined();
    expect(body.days).toBe(30);
    expect(setPayloadMock).toHaveBeenCalledTimes(1);
    expect(setPayloadMock.mock.calls[0][0]).toBe(KEY);
  });
});

describe("infra-costs GET staleness bound", () => {
  const KEY = "infra-costs:v1:30:57447";

  it("reads the cache with the freshness bound", async () => {
    await infraCostsGET(request("/api/omi/stats/infra-costs?days=30"));

    expect(getPayloadMock).toHaveBeenCalledWith(KEY, {
      maxAgeMs: MAX_PRECOMPUTED_AGE_MS,
    });
  });

  it("serves a doc within the bound verbatim, without recomputing", async () => {
    const freshAt = Date.now() - 60 * 60 * 1000;
    getPayloadMock.mockResolvedValue({
      data: { days: 30, marker: "precomputed" },
      freshAt,
    });

    const res = await infraCostsGET(
      request("/api/omi/stats/infra-costs?days=30")
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toEqual({ days: 30, marker: "precomputed", freshAt });
    expect(setPayloadMock).not.toHaveBeenCalled();
  });

  it("recomputes inline and refreshes the cache when the doc is stale or missing", async () => {
    const res = await infraCostsGET(
      request("/api/omi/stats/infra-costs?days=30")
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.marker).toBeUndefined();
    expect(body.summary.costSource).toBe("billing");
    expect(setPayloadMock).toHaveBeenCalledTimes(1);
    expect(setPayloadMock.mock.calls[0][0]).toBe(KEY);
  });
});
