import { afterEach, describe, expect, it, vi } from "vitest";

const posthogResults = vi.fn();
vi.mock("@/lib/posthog", () => ({ posthogResults }));

const ENV_KEYS = [
  "POSTHOG_PERSONAL_API_KEY",
  "POSTHOG_PROJECT_ID",
  "POSTHOG_HOST",
] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((key) => [key, process.env[key]]),
);

afterEach(() => {
  vi.resetModules();
  posthogResults.mockReset();
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

describe("computeDesktopRatings", () => {
  it("buckets by NYC day and reports a count-weighted average", async () => {
    process.env.POSTHOG_PERSONAL_API_KEY = "phx_test";
    process.env.POSTHOG_PROJECT_ID = "1";
    posthogResults.mockResolvedValue([
      ["2026-08-24", 5, 1],
      ["2026-08-25", 3, 3],
    ]);
    const { computeDesktopRatings } = await import(
      "@/app/api/omi/stats/desktop-ratings/route"
    );
    const payload = await computeDesktopRatings(60);

    expect(posthogResults.mock.calls[0][3]).toContain(
      "toTimeZone(timestamp, 'America/New_York')",
    );
    expect(posthogResults.mock.calls[0][3]).toContain("Desktop Rating Submitted");
    // HogQL rejects ClickHouse's toFloat64OrZero with a validation_error
    // ("Unsupported function call ... Perhaps you meant 'toFloatOrZero'") —
    // observed live on prod PostHog 2026-08-25.
    expect(posthogResults.mock.calls[0][3]).toContain("toFloatOrZero(");
    expect(posthogResults.mock.calls[0][3]).not.toContain("toFloat64OrZero");
    expect(payload.daily).toEqual([
      { date: "2026-08-24", avgRating: 5, count: 1 },
      { date: "2026-08-25", avgRating: 3, count: 3 },
    ]);
    // (5*1 + 3*3) / 4 = 3.5 — weighted by ratings, not by days.
    expect(payload.summary).toEqual({ avgRating: 3.5, count: 4 });
  });

  it("degrades to unavailable without PostHog credentials", async () => {
    delete process.env.POSTHOG_PERSONAL_API_KEY;
    delete process.env.POSTHOG_PROJECT_ID;
    const { computeDesktopRatings } = await import(
      "@/app/api/omi/stats/desktop-ratings/route"
    );
    await expect(computeDesktopRatings(60)).resolves.toMatchObject({
      available: false,
      daily: [],
    });
    expect(posthogResults).not.toHaveBeenCalled();
  });
});
