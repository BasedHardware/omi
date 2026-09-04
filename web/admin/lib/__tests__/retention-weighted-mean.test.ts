import { describe, expect, it } from "vitest";
import { weightedRetentionMean } from "@/app/api/omi/stats/retention/posthog/route";

describe("weightedRetentionMean", () => {
  it("weights the 2026-09-04 W4 cohorts by users, not by days", () => {
    // Live first-in-window macOS cohorts old enough for D28 on 2026-09-04.
    // Unweighted (51.6+18.5+8)/3 = 26.03 — the TV tile. User-weighted = 40.28.
    const cohorts = [
      { date: "2026-08-05", users: 896, data: [{ day: 28, retention: 51.6 }] },
      { date: "2026-08-06", users: 222, data: [{ day: 28, retention: 18.5 }] },
      { date: "2026-08-07", users: 163, data: [{ day: 28, retention: 8.0 }] },
    ];
    expect(weightedRetentionMean(cohorts)).toEqual([
      { day: 28, retention: 40.32 },
    ]);
  });

  it("omits cohorts that have not reached the day yet", () => {
    const cohorts = [
      {
        date: "old",
        users: 100,
        data: [
          { day: 0, retention: 100 },
          { day: 1, retention: 50 },
        ],
      },
      { date: "today", users: 400, data: [{ day: 0, retention: 100 }] },
    ];
    expect(weightedRetentionMean(cohorts)).toEqual([
      { day: 0, retention: 100 },
      { day: 1, retention: 50 },
    ]);
  });

  it("skips empty cohorts", () => {
    expect(
      weightedRetentionMean([
        { date: "empty", users: 0, data: [{ day: 0, retention: 12 }] },
      ])
    ).toEqual([]);
  });
});
