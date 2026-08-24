import { beforeEach, describe, expect, it, vi } from "vitest";

// Billing-mode infra costs: every dollar from a billing system, split by the
// usage-weighted shares, honest D-2 window, labeled fallback to the legacy
// estimated path when BigQuery is unavailable.

vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(async () => null),
  setPayload: vi.fn(async () => {}),
}));
// Firestore llm_usage scan: unavailable in these tests (coverage.trackedLlm=false).
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => {
    throw new Error("no firestore in test");
  },
  getAdminAuth: vi.fn(),
}));

const mockGcp = vi.fn();
const mockAnthropic = vi.fn();
const mockOpenAi = vi.fn();
vi.mock("@/lib/services/gcp-billing", () => ({
  fetchGcpBilling: (...args: unknown[]) => mockGcp(...args),
}));
vi.mock("@/lib/services/provider-costs", () => ({
  fetchAnthropicDailyCosts: (...args: unknown[]) => mockAnthropic(...args),
  fetchOpenAiDailyCosts: (...args: unknown[]) => mockOpenAi(...args),
}));

async function loadRoute() {
  vi.resetModules();
  return await import("@/app/api/omi/stats/infra-costs/route");
}

const GCP_SNAPSHOT = {
  daily: [
    { date: "2026-08-20", netUsd: 1000, grossUsd: 1200, llmNetUsd: 400 },
    { date: "2026-08-21", netUsd: 2000, grossUsd: 2300, llmNetUsd: 500 },
  ],
  services: [
    { service: "Vertex AI", netUsd: 900, isLlm: true },
    { service: "Compute Engine", netUsd: 2100, isLlm: false },
  ],
  windowStart: "2026-08-20",
  windowEnd: "2026-08-21",
};

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.ADMIN_PLATFORM_COST_SHARES_JSON;
});

describe("computeInfraCosts billing mode", () => {
  it("splits billed pools by the usage-weighted shares and labels the source", async () => {
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue([{ date: "2026-08-20", usd: 100 }]);
    mockOpenAi.mockResolvedValue([{ date: "2026-08-21", usd: 50 }]);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.costSource).toBe("billing");
    expect(payload.summary.windowEnd).toBe("2026-08-21");
    expect(payload.summary.coverage).toEqual({
      gcpBilling: true,
      anthropic: true,
      openai: true,
      trackedLlm: false,
    });
    // trackedLlm leg failed -> partial, but the dollars are still real.
    expect(payload.summary.partial).toBe(true);

    // Day 1: extraction pool = 400 (gcp llm); chat = 100 (anthropic); other = 600.
    const d0 = payload.daily[0];
    expect(d0.date).toBe("2026-08-20");
    expect(d0.desktop).toBeCloseTo(400 * 0.2273 + 100 * 0.5464 + 600 * 0.4673, 2);
    expect(d0.mobile).toBeCloseTo(400 * 0.7727 + 100 * 0.4536 + 600 * 0.5327, 2);
    expect(d0.total).toBeCloseTo(d0.desktop + d0.mobile, 2);
    // Day 2: extraction pool = 500 + 50 (openai); no chat; other = 1500.
    const d1 = payload.daily[1];
    expect(d1.desktop).toBeCloseTo(550 * 0.2273 + 1500 * 0.4673, 2);

    const services = payload.breakdown.map((r) => r.service);
    expect(services).toContain("Anthropic (billed)");
    expect(services).toContain("OpenAI (billed)");
    expect(services).toContain("Compute Engine");
  });

  it("treats a missing provider leg as partial coverage, never as $0-and-fine", async () => {
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue(null);
    mockOpenAi.mockResolvedValue(null);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.costSource).toBe("billing");
    expect(payload.summary.partial).toBe(true);
    expect(payload.summary.coverage?.anthropic).toBe(false);
    expect(payload.breakdown.map((r) => r.service)).not.toContain("Anthropic (billed)");
  });

  it("falls back to the legacy estimated path when BigQuery is unavailable", async () => {
    mockGcp.mockResolvedValue(null);
    mockAnthropic.mockResolvedValue(null);
    mockOpenAi.mockResolvedValue(null);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.costSource).toBe("estimated");
    expect(payload.summary.coverage?.gcpBilling).toBe(false);
    expect(payload.daily.length).toBe(30);
    // Legacy path still adds the flat per-service overhead every day.
    expect(payload.daily[0].total).toBeGreaterThan(0);
  });

  it("honors ADMIN_PLATFORM_COST_SHARES_JSON overrides", async () => {
    process.env.ADMIN_PLATFORM_COST_SHARES_JSON = JSON.stringify({
      llm: { desktop: 0.5, mobile: 0.5 },
      chat: { desktop: 0.5, mobile: 0.5 },
      core: { desktop: 0.5, mobile: 0.5 },
      asOf: "2026-09-01",
      method: "test",
    });
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue([]);
    mockOpenAi.mockResolvedValue([]);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.shares?.asOf).toBe("2026-09-01");
    const d0 = payload.daily[0];
    expect(d0.desktop).toBeCloseTo(d0.mobile, 2); // 50/50 on both pools
  });
});
