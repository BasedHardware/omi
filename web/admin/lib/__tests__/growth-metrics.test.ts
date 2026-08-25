import { describe, expect, it } from "vitest";

import {
  completedWeeklyNewUsers,
  maturedWeeklyActivation,
} from "@/lib/growth-metrics";

describe("growth metrics", () => {
  it("aggregates completed signup weeks and excludes the partial current week", () => {
    const result = completedWeeklyNewUsers(
      [
        { date: "2026-07-27", users: 10 },
        { date: "2026-08-02", users: 5 },
        { date: "2026-08-03", users: 40 },
        { date: "2026-08-08", users: 20 },
      ],
      new Date("2026-08-08T12:00:00Z"),
    );

    expect(result).toEqual([{ week: "2026-07-27", users: 15 }]);
  });

  it("waits for every signup in a week to finish its activation window", () => {
    const result = maturedWeeklyActivation(
      [
        { date: "2026-07-20", signups: 20, activated: 8 },
        { date: "2026-07-26", signups: 10, activated: 4 },
        { date: "2026-07-27", signups: 50, activated: 15 },
      ],
      new Date("2026-08-08T12:00:00Z"),
    );

    expect(result).toEqual([
      {
        week: "2026-07-20",
        signups: 30,
        activated: 12,
        rate: 40,
      },
    ]);
  });
});
