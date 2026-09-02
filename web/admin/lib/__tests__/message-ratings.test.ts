import { afterEach, describe, expect, it, vi } from "vitest";

const posthogResults = vi.hoisted(() => vi.fn());
vi.mock("@/lib/posthog", () => ({ posthogResults }));
vi.mock("@/lib/auth", () => ({ verifyAdmin: vi.fn() }));

import { computeMessageRatings } from "@/app/api/omi/stats/message-ratings/route";

const ENV_KEYS = ["POSTHOG_PERSONAL_API_KEY", "POSTHOG_PROJECT_ID"] as const;
const originalEnv = Object.fromEntries(
  ENV_KEYS.map((k) => [k, process.env[k]]),
);

afterEach(() => {
  posthogResults.mockReset();
  for (const key of ENV_KEYS) {
    if (originalEnv[key] == null) delete process.env[key];
    else process.env[key] = originalEnv[key];
  }
});

describe("computeMessageRatings (macOS thumbs positive share)", () => {
  it("splits text/voice, folds legacy into All only, and rolls NYC weeks", async () => {
    process.env.POSTHOG_PERSONAL_API_KEY = "phx";
    process.env.POSTHOG_PROJECT_ID = "1";
    // Monday 2026-08-24: text 3↑1↓, voice 1↑1↓; Tuesday: legacy 2↑0↓.
    posthogResults.mockResolvedValue([
      ["2026-08-24", "text", 3, 1],
      ["2026-08-24", "voice", 1, 1],
      ["2026-08-25", "legacy", 2, 0],
    ]);
    const payload = await computeMessageRatings(30);

    const query = posthogResults.mock.calls[0][3] as string;
    expect(query).toContain("properties.$os_name = 'macOS'");
    expect(query).toContain("America/New_York");

    const monday = payload.daily.find((p) => p.date === "2026-08-24")!;
    expect(monday.text).toBe(75); // one number %: up / rated
    expect(monday.voice).toBe(50);
    expect(monday.all).toBeCloseTo(66.7);
    const tuesday = payload.daily.find((p) => p.date === "2026-08-25")!;
    expect(tuesday.text).toBeNull(); // legacy events never fake a split series
    expect(tuesday.voice).toBeNull();
    expect(tuesday.all).toBe(100);

    // Weekly: both days share the 2026-08-24 NYC Monday bucket.
    expect(payload.weekly).toHaveLength(1);
    expect(payload.weekly[0].week).toBe("2026-08-24");
    expect(payload.weekly[0].all).toBe(75); // (3+1+2)↑ / 8 rated
    expect(payload.weekly[0].text).toBe(75);
    expect(payload.weekly[0].voice).toBe(50);

    // Legacy shape stays for the volumes panel and /dashboard/classic.
    expect(payload.data[0]).toEqual({
      date: "2026-08-24",
      thumbs_up: 4,
      thumbs_down: 2,
      ratio: expect.closeTo(66.7, 1),
    });
  });
});
