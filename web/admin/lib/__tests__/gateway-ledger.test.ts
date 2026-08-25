import { beforeEach, describe, expect, it, vi } from "vitest";

// Gateway ledger aggregation: never scans documents, never invents a class for
// spend it can't attribute, and degrades to the BYOK-inclusive superset rather
// than dropping a day when the payer filter can't be served.

vi.mock("firebase-admin/firestore", () => ({
  AggregateField: {
    sum: (field: string) => ({ sum: field }),
    count: () => ({ count: true }),
  },
}));

const mockGetPayload: any = vi.fn(async (_key: string) => null as any);
const mockSetPayload = vi.fn(async () => {});
vi.mock("@/lib/payload-cache", () => ({
  getPayload: (...args: unknown[]) => mockGetPayload(...(args as [])),
  setPayload: (...args: unknown[]) => mockSetPayload(...(args as [])),
}));

type Filters = Record<string, string>;

const queries: Filters[] = [];
let rejectPayerFilter = false;
let failEverything = false;
// micro-USD keyed by the discriminating filter value ("" = the day total).
const SUMS: Record<string, { micro: number; count: number }> = {
  "": { micro: 100_000_000, count: 400 }, // $100 total
  "provider:anthropic": { micro: 60_000_000, count: 200 },
  "provider:openai": { micro: 20_000_000, count: 100 },
  "feature:desktop_proactive_extraction": { micro: 30_000_000, count: 90 },
  "feature:chat_agent": { micro: 20_000_000, count: 60 },
  "feature:memories": { micro: 40_000_000, count: 150 },
};

function makeQuery(filters: Filters): any {
  return {
    where(field: string, _op: string, value: string) {
      return makeQuery({ ...filters, [field]: value });
    },
    aggregate() {
      return {
        async get() {
          if (failEverything) throw new Error("UNAVAILABLE");
          if (rejectPayerFilter && filters.payer) {
            throw new Error("FAILED_PRECONDITION: The query requires an index.");
          }
          queries.push(filters);
          const key = filters.provider
            ? `provider:${filters.provider}`
            : filters.feature
              ? `feature:${filters.feature}`
              : "";
          const hit = SUMS[key] ?? { micro: 0, count: 0 };
          return { data: () => hit };
        },
      };
    },
  };
}

vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({ collection: () => makeQuery({}) }),
  getAdminAuth: vi.fn(),
}));

// Old enough that the volatile-window rule doesn't force a recompute.
const DAY = "2026-08-01";

async function load() {
  vi.resetModules();
  return await import("@/lib/services/gateway-ledger");
}

beforeEach(() => {
  vi.clearAllMocks();
  queries.length = 0;
  rejectPayerFilter = false;
  failEverything = false;
  mockGetPayload.mockResolvedValue(null);
});

describe("fetchGatewayLedgerDays", () => {
  it("aggregates a day by class and provider without reading documents", async () => {
    const { fetchGatewayLedgerDays } = await load();

    const days = await fetchGatewayLedgerDays([DAY]);

    expect(days).not.toBeNull();
    const day = days![0];
    expect(day.date).toBe(DAY);
    expect(day.totalUsd).toBe(100);
    expect(day.attemptCount).toBe(400);
    expect(day.byokIncluded).toBe(false);
    expect(day.byProvider.anthropic).toBe(60);
    expect(day.byProvider.openai).toBe(20);
    expect(day.byProvider.gemini).toBe(0);
    expect(day.byClass.desktop).toBe(30);
    expect(day.byClass.sharedChat).toBe(20);
    expect(day.byClass.sharedExtraction).toBe(40);
    // $90 of the $100 day total lands on classified features; the remainder is
    // spend from features we don't classify, kept separate as `unknown`.
    expect(day.byClass.unknown).toBe(10);

    // Every query is an equality-filtered aggregation scoped to the day and
    // the Omi payer; nothing fetches documents.
    expect(queries.length).toBeGreaterThan(5);
    for (const q of queries) {
      expect(q.date).toBe(DAY);
      expect(q.payer).toBe("omi");
    }
    expect(mockSetPayload).toHaveBeenCalledWith(`gateway-ledger:v1:${DAY}`, day);
  });

  it("credits unclassified spend to unknown rather than to a class", async () => {
    SUMS[""] = { micro: 150_000_000, count: 500 };
    try {
      const { fetchGatewayLedgerDays } = await load();
      const days = await fetchGatewayLedgerDays([DAY]);
      expect(days![0].byClass.unknown).toBe(60); // 150 total - 90 classified
    } finally {
      SUMS[""] = { micro: 100_000_000, count: 400 };
    }
  });

  it("retries without the payer filter and flags byokIncluded when it is rejected", async () => {
    rejectPayerFilter = true;
    const { fetchGatewayLedgerDays } = await load();

    const days = await fetchGatewayLedgerDays([DAY]);

    expect(days![0].byokIncluded).toBe(true);
    expect(days![0].totalUsd).toBe(100);
    for (const q of queries) expect(q.payer).toBeUndefined();
  });

  it("serves a cached day as-is and only computes the missing ones", async () => {
    const cached = {
      date: DAY,
      totalUsd: 7,
      byProvider: {},
      byClass: { desktop: 7, mobile: 0, sharedExtraction: 0, sharedChat: 0, unknown: 0 },
      attemptCount: 1,
      byokIncluded: false,
    };
    mockGetPayload.mockImplementation(async (key: unknown) =>
      key === `gateway-ledger:v1:${DAY}` ? ({ data: cached, freshAt: 1 } as any) : null,
    );
    const { fetchGatewayLedgerDays } = await load();

    const days = await fetchGatewayLedgerDays([DAY, "2026-08-02"]);

    expect(days).toHaveLength(2);
    expect(days![0]).toEqual(cached);
    expect(queries.every((q) => q.date === "2026-08-02")).toBe(true);
  });

  it("classifies the gateway features that used to fall into unknown", async () => {
    const { FEATURE_CLASS } = await load();

    // Desktop-only surfaces.
    expect(FEATURE_CLASS.workstream_association).toBe("desktop");
    expect(FEATURE_CLASS.chat_structured).toBe("desktop");
    // Coarse usage-context names that override the model_config feature on the
    // wire (backend/utils/llm/gateway_client.py `_gateway_usage_headers`).
    expect(FEATURE_CLASS.chat).toBe("sharedChat");
    expect(FEATURE_CLASS.persona).toBe("sharedChat");
    expect(FEATURE_CLASS.conversation_processing).toBe("sharedExtraction");
    expect(FEATURE_CLASS.conv_apps).toBe("sharedExtraction");
    expect(FEATURE_CLASS.realtime_integrations).toBe("sharedExtraction");
    expect(FEATURE_CLASS.subscription_notification).toBe("sharedExtraction");
    // Gateway-side fallback labels and shadow runs.
    expect(FEATURE_CLASS.image_generation).toBe("sharedExtraction");
    expect(FEATURE_CLASS.public_shared_conversation_chat).toBe("sharedChat");
    expect(FEATURE_CLASS["conversation_structure.extract.shadow"]).toBe("sharedExtraction");
    expect(FEATURE_CLASS["conversation_action_items.extract.shadow"]).toBe("sharedExtraction");
  });

  it("aggregates every classified feature, including the newly added ones", async () => {
    const { fetchGatewayLedgerDays, FEATURE_CLASS } = await load();

    await fetchGatewayLedgerDays([DAY]);

    const queried = new Set(queries.map((q) => q.feature).filter(Boolean));
    for (const feature of Object.keys(FEATURE_CLASS)) {
      expect(queried.has(feature)).toBe(true);
    }
  });

  it("returns null only when every day fails", async () => {
    failEverything = true;
    const { fetchGatewayLedgerDays } = await load();
    expect(await fetchGatewayLedgerDays([DAY, "2026-08-02"])).toBeNull();
    expect(await fetchGatewayLedgerDays([])).toBeNull();
  });
});
