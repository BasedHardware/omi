import { describe, expect, it } from "vitest";

import {
  calculatePeriodChange,
  formatPeriodChange,
  latestPeriodChange,
} from "@/lib/period-change";

describe("period change", () => {
  it("calculates signed changes between matching periods", () => {
    expect(calculatePeriodChange(120, 100, "vs previous week")).toEqual({
      percentage: 20,
      label: "vs previous week",
    });
    expect(calculatePeriodChange(75, 100)?.percentage).toBe(-25);
    expect(formatPeriodChange(20)).toBe("+20%");
    expect(formatPeriodChange(-3.25)).toBe("-3.3%");
  });

  it("uses the latest two matching buckets", () => {
    const change = latestPeriodChange(
      [{ total: 80 }, { total: 100 }],
      (point) => point.total,
    );

    expect(change?.percentage).toBe(25);
    expect(
      latestPeriodChange(
        [{ total: 80 }, { total: 100 }, { total: Number.NaN }],
        (point) => point.total,
      ),
    ).toBeNull();
  });

  it("does not invent a percentage without a valid baseline", () => {
    expect(calculatePeriodChange(5, 0)).toBeNull();
    expect(
      latestPeriodChange([{ total: 5 }], (point) => point.total),
    ).toBeNull();
    expect(calculatePeriodChange(0, 0)?.percentage).toBe(0);
  });
});
