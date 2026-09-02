import { afterEach, describe, expect, it, vi } from "vitest";

const posthogResults = vi.hoisted(() => vi.fn());
vi.mock("@/lib/posthog", () => ({ posthogResults }));
vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));
vi.mock("@/lib/payload-cache", () => ({
  getPayload: vi.fn(),
  setPayload: vi.fn(),
  withFreshness: (data: object, freshAt: number) => ({ ...data, freshAt }),
}));

import {
  ACTIVATION_QUESTIONS,
  ACTIVATION_WINDOW_HOURS,
  computeActivation,
  rollUpDaily,
} from "@/app/api/omi/stats/activation/route";

const ENV_KEYS = ["POSTHOG_PERSONAL_API_KEY", "POSTHOG_PROJECT_ID"] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]]),
);

afterEach(() => {
  posthogResults.mockReset();
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

function configure() {
  process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
  process.env.POSTHOG_PROJECT_ID = "1";
}

// PostHog returns "YYYY-MM-DD HH:MM:SS" strings (UTC) for toString(ts).
function ph(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 86_400_000)
    .toISOString()
    .slice(0, 19)
    .replace("T", " ");
}

describe("computeActivation (2+ questions within 48h)", () => {
  it("activation = questions >= threshold; rate over the matured cohort", async () => {
    configure();
    // 4 matured signups: 2 activated (>=2 questions in window), 2 not.
    posthogResults.mockResolvedValue([
      [ph(10), 5],
      [ph(9), 2],
      [ph(8), 1],
      [ph(7), 0],
    ]);
    const series = await computeActivation(60);

    expect(series.signups).toBe(4);
    expect(series.activated).toBe(2);
    expect(series.rate).toBeCloseTo(50);
    expect(series.erroredUsers).toBe(0);
    // Weekly rollup preserved for the existing signup→activated chart.
    expect(series.weeks.length).toBeGreaterThan(0);
    // Daily series for the new daily-rate chart.
    expect(series.daily.reduce((a, d) => a + d.signups, 0)).toBe(4);
    expect(series.daily.every((d) => d.rate >= 0 && d.rate <= 100)).toBe(true);
  });

  it("sends the definition to PostHog: macOS cohort, maturity, Chat Message Sent window", async () => {
    configure();
    posthogResults.mockResolvedValue([]);
    await computeActivation(30);
    const query = posthogResults.mock.calls[0][3] as string;
    expect(query).toContain("properties.$os_name = 'macOS'");
    expect(query).toContain(
      `first_ts <= now() - INTERVAL ${ACTIVATION_WINDOW_HOURS} HOUR`,
    );
    // Questions = typed chat AND floating-bar/PTT queries — counting only
    // one of them undercounts activation by ~a third (user-reported).
    expect(query).toContain("'Chat Message Sent', 'floating_bar_query_sent'");
    // Only post-onboarding questions count; a user who never completed
    // onboarding cannot activate (onboarding-chat questions are not product
    // usage).
    expect(query).toContain("Onboarding Completed");
    expect(query).toContain("e.timestamp >= o.onb_ts");
    expect(query).toContain("o.onb_ts > toDateTime(0)");
    expect(query).toContain(
      `f.first_ts + INTERVAL ${ACTIVATION_WINDOW_HOURS} HOUR`,
    );
    expect(ACTIVATION_QUESTIONS).toBe(2);
  });

  it("throws without PostHog credentials so the caller returns an honest 500", async () => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
    await expect(computeActivation(60)).rejects.toThrow(
      "PostHog credentials not configured",
    );
  });
});

describe("rollUpDaily", () => {
  it("groups by NYC day and rounds rate to one decimal", () => {
    const day = "2026-08-20T15:00:00.000Z";
    const daily = rollUpDaily([
      { signupAt: day, activated: true },
      { signupAt: day, activated: true },
      { signupAt: day, activated: false },
    ]);
    expect(daily).toEqual([
      { date: "2026-08-20", signups: 3, activated: 2, rate: 66.7 },
    ]);
  });
});
