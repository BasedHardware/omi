import { afterEach, describe, expect, it, vi } from "vitest";

const posthogResults = vi.fn();
vi.mock("@/lib/posthog", () => ({ posthogResults }));

// Firestore referral ledger: two granted claims, one inside the last 24h.
const RECENT_CLAIM_MS = Date.now() - 3_600_000;
const OLD_CLAIM_MS = Date.now() - 10 * 86_400_000;
const referralDocs = [
  { get: (f: string) => (f === "referral.claimed_at" ? RECENT_CLAIM_MS / 1000 : null) },
  { get: (f: string) => (f === "referral.claimed_at" ? OLD_CLAIM_MS / 1000 : null) },
];
// Pages served in order — pagination tests enqueue a full page plus a tail.
let firestorePages: Array<Array<{ get: (f: string) => unknown }>> = [referralDocs];
const firestoreGet = vi.fn(async () => ({
  docs: firestorePages.shift() ?? [],
}));
vi.mock("@/lib/firebase/admin", () => ({
  getDb: () => ({
    collection: () => ({
      where: (field: string, op: string, value: string) => {
        expect(field).toBe("referral.program");
        expect(value).toBe("desktop_operator_month_v1");
        const query = {
          limit: () => query,
          startAfter: () => query,
          get: firestoreGet,
        };
        return query;
      },
    }),
  }),
}));

const ENV_KEYS = [
  "POSTHOG_PERSONAL_API_KEY",
  "POSTHOG_PROJECT_ID",
  "POSTHOG_HOST",
] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]]),
);

function configurePosthog() {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "1";
  process.env.POSTHOG_HOST = "https://posthog.test";
}

function nycDate(msAgo = 0): string {
  return new Date(Date.now() - msAgo).toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });
}

afterEach(() => {
  vi.resetModules();
  posthogResults.mockReset();
  firestoreGet.mockClear();
  firestorePages = [referralDocs];
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

async function compute(platform?: "all" | "macos" | "mobile") {
  const { computeKFactor } = await import(
    "@/app/api/omi/stats/k-factor/posthog/route"
  );
  return computeKFactor(30, platform);
}

function capturedQueries(): string[] {
  return posthogResults.mock.calls.map(([, , , query]) => query as string);
}

describe("computeKFactor viral signals", () => {
  it("is unavailable when PostHog credentials are missing", async () => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
    await expect(compute()).resolves.toMatchObject({
      available: false,
      kFactor: null,
      reason: "PostHog credentials not configured.",
    });
    expect(posthogResults).not.toHaveBeenCalled();
  });

  it("keeps the legacy referral funnel fields for the classic dashboard tile", async () => {
    configurePosthog();
    posthogResults.mockResolvedValue([]);
    await expect(compute("macos")).resolves.toMatchObject({
      available: true,
      funnel: { issued: 0, captured: 0, granted: 0 },
    });
    const funnelQueries = capturedQueries().filter((q) =>
      q.includes("desktop_operator_month_v1"),
    );
    expect(funnelQueries).toHaveLength(3);
    expect(funnelQueries.join("\n")).toContain("properties.claimed = true");
    for (const q of funnelQueries) expect(q).not.toContain("$os_name");
  });

  it("scopes the macOS board to macOS client events with NYC day buckets", async () => {
    configurePosthog();
    posthogResults.mockResolvedValue([]);
    await compute("macos");
    const queries = capturedQueries();
    const friendQuery = queries.find((q) =>
      q.includes("Onboarding How Did You Hear"),
    )!;
    expect(friendQuery).toContain("properties.source = 'Friend'");
    expect(friendQuery).toContain("properties.$os_name = 'macOS'");
    const sharesQuery = queries.find((q) => q.includes("Share Action"))!;
    expect(sharesQuery).toContain("properties.category = 'conversation'");
    // Delivered share emails are recorded server-side without an OS — the
    // event name itself is the platform scope.
    expect(sharesQuery).toContain("Conversation Summary Shared");
    for (const q of queries.filter((q) => q.includes("toDate"))) {
      expect(q).toContain("America/New_York");
    }
  });

  it("scopes the mobile board to mobile shares and zero desktop-only signals", async () => {
    configurePosthog();
    posthogResults.mockResolvedValue([]);
    const payload = await compute("mobile");
    const queries = capturedQueries();
    const sharesQuery = queries.find((q) => q.includes("Conversation Shared"))!;
    expect(sharesQuery).toContain("'iOS', 'Android', 'iPadOS'");
    expect(sharesQuery).not.toContain("Conversation Summary Shared");
    // The referral program grants a desktop trial — the mobile board must not
    // read the Firestore ledger at all.
    expect(firestoreGet).not.toHaveBeenCalled();
    expect((payload as any).summary.referral).toBe(0);
  });

  it("computes k-factor as viral events per new user and exposes daily and weekly trackers", async () => {
    configurePosthog();
    const today = nycDate();
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Onboarding How Did You Hear")) {
        return query.includes("INTERVAL 7 DAY") ? [[1, 3]] : [[today, 2]].map((r) => r);
      }
      if (query.includes("Share Action") || query.includes("Conversation Shared")) {
        return query.includes("INTERVAL 7 DAY") ? [[2, 6]] : [[today, 4]];
      }
      if (query.includes("min_ts")) {
        return query.includes("INTERVAL 7 DAY") ? [[10, 40]] : [[today, 10]];
      }
      return [[0]]; // funnel queries
    });
    const payload: any = await compute("macos");

    const lastDaily = payload.daily[payload.daily.length - 1];
    expect(lastDaily.date).toBe(today);
    // Rolling last-24h replaces the partial calendar day, and the Firestore
    // claim from the last hour is counted as a referral.
    expect(lastDaily.friend).toBe(2);
    expect(lastDaily.shares).toBe(4);
    expect(lastDaily.referral).toBe(1);
    expect(lastDaily.viralEvents).toBe(7);
    expect(lastDaily.newUsers).toBe(10);
    expect(lastDaily.kFactor).toBeCloseTo(0.7);

    // Weekly tracker exists and its last bucket is the rolling trailing 7d.
    const lastWeekly = payload.weekly[payload.weekly.length - 1];
    expect(lastWeekly.friend).toBe(3);
    expect(lastWeekly.shares).toBe(6);
    // Only the claim from the last hour is inside the trailing 7 days; the
    // 10-day-old claim still counts toward the 30d summary below.
    expect(lastWeekly.referral).toBe(1);
    expect(lastWeekly.newUsers).toBe(40);
    expect(lastWeekly.kFactor).toBeCloseTo(10 / 40);
    expect(payload.summary.referral).toBe(2);

    // Window k-factor = total viral events / total new users.
    expect(payload.summary.kFactor).toBe(payload.kFactor);
    expect(payload.kFactor).toBeGreaterThan(0);
  });

  it("reads the whole referral ledger past the first Firestore page", async () => {
    configurePosthog();
    posthogResults.mockResolvedValue([]);
    const { REFERRAL_LEDGER_PAGE_SIZE } = await import(
      "@/app/api/omi/stats/k-factor/posthog/route"
    );
    const claim = { get: (f: string) => (f === "referral.claimed_at" ? RECENT_CLAIM_MS / 1000 : null) };
    // A full first page must NOT terminate the read: the claim on page two
    // has to reach the summary.
    firestorePages = [Array(REFERRAL_LEDGER_PAGE_SIZE).fill(claim), [claim]];
    const payload: any = await compute("macos");
    expect(firestoreGet).toHaveBeenCalledTimes(2);
    expect(payload.summary.referral).toBe(REFERRAL_LEDGER_PAGE_SIZE + 1);
  });

  it("never double-counts the hours a rolling 24h window shares with yesterday", async () => {
    configurePosthog();
    const today = nycDate();
    const yesterday = nycDate(86_400_000);
    posthogResults.mockImplementation(async (_h, _p, _k, query: string) => {
      if (query.includes("Onboarding How Did You Hear")) {
        // 5 signups yesterday + 1 today; the trailing 24h window sees 4 of
        // them (3 of yesterday's late-evening ones plus today's).
        return query.includes("INTERVAL 7 DAY") ? [[4, 6]] : [[yesterday, 5], [today, 1]];
      }
      if (query.includes("Share Action")) {
        return query.includes("INTERVAL 7 DAY") ? [[0, 0]] : [];
      }
      if (query.includes("min_ts")) {
        return query.includes("INTERVAL 7 DAY") ? [[10, 20]] : [[yesterday, 10], [today, 10]];
      }
      return [[0]];
    });
    const payload: any = await compute("macos");

    // Chart: the newest bar is the full rolling window…
    const lastDaily = payload.daily[payload.daily.length - 1];
    expect(lastDaily.friend).toBe(4);
    // …but the 30d summary stays the sum of calendar days (5 + 1), NOT the
    // calendar days with today swapped for the overlapping 24h window (5 + 4).
    expect(payload.summary.friend).toBe(6);
    // Weekly calendar buckets are aggregated pre-override too: everything but
    // the last (rolling trailing 7d) bucket sums calendar values.
    const weeklySum = payload.weekly.reduce(
      (acc: number, w: any) => acc + w.friend,
      0,
    );
    const lastWeekly = payload.weekly[payload.weekly.length - 1];
    expect(lastWeekly.friend).toBe(6); // trailing-7d query value, a replacement
    if (payload.weekly.length > 1) {
      expect(weeklySum - lastWeekly.friend).toBeLessThanOrEqual(6);
    }
  });
});
