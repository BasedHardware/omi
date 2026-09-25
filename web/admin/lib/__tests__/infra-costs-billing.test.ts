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
const mockLedger = vi.fn();
vi.mock("@/lib/services/gcp-billing", () => ({
  fetchGcpBilling: (...args: unknown[]) => mockGcp(...args),
}));
vi.mock("@/lib/services/provider-costs", () => ({
  fetchAnthropicDailyCosts: (...args: unknown[]) => mockAnthropic(...args),
  fetchOpenAiDailyCosts: (...args: unknown[]) => mockOpenAi(...args),
}));
vi.mock("@/lib/services/gateway-ledger", () => ({
  fetchGatewayLedgerDays: (...args: unknown[]) => mockLedger(...args),
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

// Gateway ledger: measured per-attempt spend for the same two days.
// Day 1 mixes all four classes; day 2 is desktop + shared extraction only, so
// the two days must produce different measured desktop shares.
const LEDGER_DAYS = [
  {
    date: "2026-08-20",
    totalUsd: 100,
    byProvider: { openai: 20, anthropic: 60, gemini: 20, openrouter: 0, perplexity: 0 },
    byClass: { desktop: 30, mobile: 0, sharedExtraction: 40, sharedChat: 20, unknown: 10 },
    attemptCount: 500,
    byokIncluded: false,
  },
  {
    date: "2026-08-21",
    totalUsd: 200,
    byProvider: { openai: 10, anthropic: 30, gemini: 160, openrouter: 0, perplexity: 0 },
    byClass: { desktop: 100, mobile: 0, sharedExtraction: 100, sharedChat: 0, unknown: 0 },
    attemptCount: 800,
    byokIncluded: false,
  },
];

// The measured desktop share of a day's LLM spend, as the route derives it.
function measuredDesktopShare(day: (typeof LEDGER_DAYS)[number]): number {
  return (
    (day.byClass.desktop +
      day.byClass.sharedExtraction * 0.2273 +
      day.byClass.sharedChat * 0.5464 +
      day.byClass.unknown * 0.4673) /
    day.totalUsd
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  delete process.env.ADMIN_PLATFORM_COST_SHARES_JSON;
  mockLedger.mockResolvedValue(null);
});

describe("computeInfraCosts billing mode", () => {
  it("splits billed pools by the measured ledger share and labels the source", async () => {
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue([{ date: "2026-08-20", usd: 100 }]);
    mockOpenAi.mockResolvedValue([{ date: "2026-08-21", usd: 50 }]);
    mockLedger.mockResolvedValue(LEDGER_DAYS);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.costSource).toBe("billing");
    expect(payload.summary.windowEnd).toBe("2026-08-21");
    expect(payload.summary.coverage).toEqual({
      gcpBilling: true,
      anthropic: true,
      openai: true,
      trackedLlm: false,
      gatewayLedger: true,
    });
    // trackedLlm leg failed -> partial, but the dollars are still real.
    expect(payload.summary.partial).toBe(true);

    // The ledger leg is scoped to the GCP window, not to a guessed date range.
    expect(mockLedger).toHaveBeenCalledWith(["2026-08-20", "2026-08-21"]);

    // Day 1: extraction pool = 400 (gcp llm); chat = 100 (anthropic); other = 600.
    // The extraction pool now splits by the day's MEASURED desktop share
    // (0.5469 here) rather than the static 0.2273.
    const share0 = measuredDesktopShare(LEDGER_DAYS[0]);
    expect(share0).toBeCloseTo(0.54693, 5);
    const d0 = payload.daily[0];
    expect(d0.date).toBe("2026-08-20");
    expect(d0.desktop).toBeCloseTo(400 * share0 + 100 * 0.5464 + 600 * 0.4673, 2);
    expect(d0.mobile).toBeCloseTo(400 * (1 - share0) + 100 * 0.4536 + 600 * 0.5327, 2);
    expect(d0.total).toBeCloseTo(d0.desktop + d0.mobile, 2);
    // Day 2: extraction pool = 500 + 50 (openai); no chat; other = 1500. A
    // different ledger mix -> a different measured share on the same window.
    const share1 = measuredDesktopShare(LEDGER_DAYS[1]);
    expect(share1).not.toBeCloseTo(share0, 3);
    const d1 = payload.daily[1];
    expect(d1.desktop).toBeCloseTo(550 * share1 + 1500 * 0.4673, 2);

    // Window ledger rollup.
    expect(payload.summary.gatewayLedger).toEqual({
      windowUsd: 300,
      byProvider: { openai: 30, anthropic: 90, gemini: 180, openrouter: 0, perplexity: 0 },
      byClass: { desktop: 130, mobile: 0, sharedExtraction: 140, sharedChat: 20, unknown: 10 },
      byokIncluded: false,
    });

    // Direct-path leak = invoiced - ledger, per provider, clamped at zero.
    // Anthropic: 100 invoiced - 90 in the ledger. OpenAI: 50 - 30.
    expect(payload.summary.directPath).toEqual({ anthropicUsd: 10, openaiUsd: 20 });

    const services = payload.breakdown.map((r) => r.service);
    expect(services).toContain("Anthropic (billed)");
    expect(services).toContain("OpenAI (billed)");
    expect(services).toContain("Compute Engine");
  });

  it("falls back to the static shares and omits directPath when the ledger is unavailable", async () => {
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue([{ date: "2026-08-20", usd: 100 }]);
    mockOpenAi.mockResolvedValue([{ date: "2026-08-21", usd: 50 }]);
    mockLedger.mockResolvedValue(null);
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.coverage?.gatewayLedger).toBe(false);
    expect(payload.summary.partial).toBe(true);
    // No ledger, no leak claim: a missing leg must never read as a $0 leak.
    expect(payload.summary.directPath).toBeUndefined();
    expect(payload.summary.gatewayLedger).toBeUndefined();

    const d0 = payload.daily[0];
    expect(d0.desktop).toBeCloseTo(400 * 0.2273 + 100 * 0.5464 + 600 * 0.4673, 2);
    expect(d0.mobile).toBeCloseTo(400 * 0.7727 + 100 * 0.4536 + 600 * 0.5327, 2);
  });

  it("keeps static shares on days the ledger does not cover", async () => {
    mockGcp.mockResolvedValue(GCP_SNAPSHOT);
    mockAnthropic.mockResolvedValue([{ date: "2026-08-20", usd: 100 }]);
    mockOpenAi.mockResolvedValue([{ date: "2026-08-21", usd: 50 }]);
    mockLedger.mockResolvedValue([LEDGER_DAYS[0]]); // day 2 missing
    const { computeInfraCosts } = await loadRoute();

    const payload = await computeInfraCosts({ days: 30, overheadMonthly: 57447 });

    expect(payload.summary.coverage?.gatewayLedger).toBe(true);
    expect(payload.daily[0].desktop).toBeCloseTo(
      400 * measuredDesktopShare(LEDGER_DAYS[0]) + 100 * 0.5464 + 600 * 0.4673,
      2,
    );
    expect(payload.daily[1].desktop).toBeCloseTo(550 * 0.2273 + 1500 * 0.4673, 2);
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
