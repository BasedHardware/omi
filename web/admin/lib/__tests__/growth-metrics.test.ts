import { describe, expect, it } from "vitest";

import {
  completedEstablishedRetention,
  completedWeeklyGrowthAccounting,
  completedWeeklyNewUsers,
  maturedWeeklyActivation,
  rollUpActivationCohort,
  rollingGrowthSummary,
  summarizeActivation,
} from "@/lib/growth-metrics";

describe("growth metrics", () => {
  it("keeps only complete UTC weeks and balances new, retained, and resurrected", () => {
    const result = completedWeeklyGrowthAccounting(
      [
        { week: "2026-07-27", active: 100, newUsers: 20, retained: 60 },
        { week: "2026-08-03", active: 110, newUsers: 25, retained: 65 },
        { week: "2026-08-10", active: 120, newUsers: 30, retained: 70 },
        { week: "2026-08-17", active: 999, newUsers: 999, retained: 999 },
      ],
      new Date("2026-08-19T00:00:00Z"),
      14
    );

    expect(result).toEqual([
      {
        week: "2026-08-03",
        active: 110,
        newUsers: 25,
        retained: 65,
        resurrected: 20,
        inactive: 35,
        priorActive: 100,
        inactiveRate: 35,
        inactiveLoss: -35,
        netActiveChange: 10,
      },
      {
        week: "2026-08-10",
        active: 120,
        newUsers: 30,
        retained: 70,
        resurrected: 20,
        inactive: 40,
        priorActive: 110,
        inactiveRate: 36.4,
        inactiveLoss: -40,
        netActiveChange: 10,
      },
    ]);
    expect(
      result.every(
        (point) =>
          point.newUsers + point.retained + point.resurrected === point.active
      )
    ).toBe(true);
  });

  it("does not duplicate a week or treat the current UTC week as history", () => {
    const result = completedWeeklyGrowthAccounting(
      [
        { week: "2026-08-10T00:00:00Z", active: 10, newUsers: 3, retained: 4 },
        { week: "2026-08-10", active: 11, newUsers: 3, retained: 4 },
        { week: "2026-08-17", active: 12, newUsers: 3, retained: 5 },
      ],
      new Date("2026-08-17T00:05:00Z"),
      7
    );

    expect(result).toHaveLength(1);
    expect(result[0].week).toBe("2026-08-10");
    expect(result[0].active).toBe(11);
  });

  it("keeps a trailing complete week when its active query has no rows", () => {
    const result = completedWeeklyGrowthAccounting(
      [{ week: "2026-08-10", active: 100, newUsers: 0, retained: 0 }],
      new Date("2026-08-24T12:00:00Z"),
      7
    );

    expect(result).toEqual([
      {
        week: "2026-08-17",
        active: 0,
        newUsers: 0,
        retained: 0,
        resurrected: 0,
        inactive: 100,
        priorActive: 100,
        inactiveRate: 100,
        inactiveLoss: -100,
        netActiveChange: -100,
      },
    ]);
  });

  it("reports established-user retention with a real denominator", () => {
    expect(
      completedEstablishedRetention(
        [
          { week: "2026-08-03", established: 10, retained: 7 },
          { week: "2026-08-10", established: 0, retained: 0 },
          { week: "2026-08-17", established: 5, retained: 2 },
        ],
        new Date("2026-08-24T00:00:00Z"),
        30
      )
    ).toEqual([
      { week: "2026-08-03", established: 10, retained: 7, rate: 70 },
      { week: "2026-08-10", established: 0, retained: 0, rate: null },
      { week: "2026-08-17", established: 5, retained: 2, rate: 40 },
    ]);
  });

  it("keeps rolling inactivity separate and honest when the denominator is empty", () => {
    expect(
      rollingGrowthSummary({
        active: 8,
        priorActive: 0,
        newUsers: 8,
        retained: 0,
      })
    ).toEqual({
      active: 8,
      priorActive: 0,
      newUsers: 8,
      retained: 0,
      resurrected: 0,
      inactive: 0,
      inactiveRate: null,
      netActiveChange: 8,
    });
  });

  it("aggregates completed signup weeks and excludes the partial current week", () => {
    const result = completedWeeklyNewUsers(
      [
        { date: "2026-07-27", users: 10 },
        { date: "2026-08-02", users: 5 },
        { date: "2026-08-03", users: 40 },
        { date: "2026-08-08", users: 20 },
      ],
      new Date("2026-08-08T12:00:00Z")
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
      new Date("2026-08-08T12:00:00Z")
    );

    expect(result).toEqual([
      {
        week: "2026-07-20",
        signups: 30,
        activated: 12,
        rate: 40,
        capableRate: 40,
        telemetryCoverage: 100,
      },
    ]);
  });

  it("reports a week nobody could report as unmeasurable, not as zero", () => {
    const result = maturedWeeklyActivation(
      [
        {
          date: "2026-07-20",
          signups: 30,
          activated: 0,
          capableSignups: 0,
          capableActivated: 0,
        },
      ],
      new Date("2026-08-08T12:00:00Z")
    );

    expect(result[0].rate).toBe(0);
    expect(result[0].capableRate).toBeNull();
    expect(result[0].telemetryCoverage).toBe(0);
  });
});

describe("summarizeActivation", () => {
  it("excludes signups whose 7-day activation window has not elapsed", () => {
    // The Aug 5 cohort cannot have activated yet on Aug 8. Pooling it would
    // report 10/60 = 16.7% instead of the real, measurable 10/20 = 50%.
    const result = summarizeActivation(
      [
        { date: "2026-08-01", signups: 20, activated: 10 },
        { date: "2026-08-05", signups: 40, activated: 0 },
      ],
      new Date("2026-08-08T12:00:00Z")
    );

    expect(result.signups).toBe(20);
    expect(result.activated).toBe(10);
    expect(result.rate).toBe(50);
  });

  it("counts a signup day the moment its window closes, not a day later", () => {
    const result = summarizeActivation(
      [{ date: "2026-08-01", signups: 20, activated: 10 }],
      new Date("2026-08-08T00:00:00Z")
    );

    expect(result.signups).toBe(20);
    expect(result.rate).toBe(50);
  });

  it("separates users who cannot report activation from users who did not activate", () => {
    // 100 matured signups, but only 20 run a build that can emit the event.
    // The honest read is 50% of reporting users, at 20% telemetry coverage --
    // not the 10% the pooled number would imply.
    const result = summarizeActivation(
      [
        {
          date: "2026-08-01",
          signups: 100,
          activated: 10,
          capableSignups: 20,
          capableActivated: 10,
        },
      ],
      new Date("2026-08-10T12:00:00Z")
    );

    expect(result.rate).toBe(10);
    expect(result.capableRate).toBe(50);
    expect(result.telemetryCoverage).toBe(20);
  });

  it("treats a series without capability counts as fully covered", () => {
    const result = summarizeActivation(
      [{ date: "2026-08-01", signups: 50, activated: 20 }],
      new Date("2026-08-10T12:00:00Z")
    );

    expect(result.capableRate).toBe(40);
    expect(result.telemetryCoverage).toBe(100);
  });

  it("returns null rates rather than zero when nothing has matured", () => {
    const result = summarizeActivation(
      [{ date: "2026-08-09", signups: 30, activated: 0 }],
      new Date("2026-08-10T12:00:00Z")
    );

    expect(result.signups).toBe(0);
    expect(result.rate).toBeNull();
    expect(result.telemetryCoverage).toBeNull();
  });
});

describe("rollUpActivationCohort", () => {
  it("buckets members by the Monday of their signup and pools the rate", () => {
    const result = rollUpActivationCohort([
      { signupAt: "2026-08-03T09:00:00Z", activated: true },
      { signupAt: "2026-08-05T23:59:00Z", activated: false },
      { signupAt: "2026-08-09T12:00:00Z", activated: true },
      { signupAt: "2026-08-10T00:00:00Z", activated: false },
    ]);

    expect(result.weeks).toEqual([
      { week: "2026-08-03", signups: 3, activated: 2, rate: 66.7 },
      { week: "2026-08-10", signups: 1, activated: 0, rate: 0 },
    ]);
    expect(result.signups).toBe(4);
    expect(result.activated).toBe(2);
    expect(result.rate).toBe(50);
  });

  it("returns a null rate for an empty cohort rather than zero", () => {
    const result = rollUpActivationCohort([]);

    expect(result.weeks).toEqual([]);
    expect(result.rate).toBeNull();
  });
});
