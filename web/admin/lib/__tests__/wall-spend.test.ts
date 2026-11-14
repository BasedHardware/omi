import { describe, expect, it } from "vitest";
import {
  isCalendarDate,
  PARITY_ALL_IN_USD,
  PARITY_DAY,
  parityDelta,
  listenUsdPerAudioHour,
  spendDailyQuery,
  spendDays,
  variableCostPerPayingUserMonth,
  SPEND_TABLE,
} from "../wall-spend";

describe("spendDailyQuery", () => {
  it("reads the settled table with latest-run dedupe and the window bounds", () => {
    const sql = spendDailyQuery("2026-11-04", 7);
    expect(sql).toContain(`\`${SPEND_TABLE}\``);
    expect(sql).toContain("inputs_settled");
    expect(sql).toContain("QUALIFY ROW_NUMBER()");
    expect(sql).toContain("ORDER BY computed_at DESC");
    expect(sql).toContain("DATE '2026-11-04'");
    expect(sql).toContain("INTERVAL 7 DAY");
  });

  it("dedupes to the latest run before it drops unsettled rows", () => {
    const sql = spendDailyQuery("2026-11-04", 7);
    const latestBlock = sql.slice(
      sql.indexOf("latest AS ("),
      sql.indexOf("QUALIFY")
    );
    expect(latestBlock).not.toContain("inputs_settled");
    expect(sql.indexOf("QUALIFY")).toBeLessThan(
      sql.indexOf("WHERE inputs_settled")
    );
  });

  it("counts one alternative per exclusive pair, gated on the margin basis", () => {
    const sql = spendDailyQuery("2026-11-04", 7);
    // The producer writes Modulate cash + modelled, and Stripe actual fees +
    // the subscription estimate, as separate variable rows on the same day.
    // Only in_margin_basis says which one counts; summing basis_class alone
    // double counts both pairs.
    expect(sql).toContain(
      "SUM(IF(basis_class = 'variable' AND in_margin_basis, usd, NULL)) AS variable_usd"
    );
    expect(sql).toContain(
      "SUM(IF(basis_class = 'variable' AND in_margin_basis AND STARTS_WITH(line, 'stt_'), usd, NULL)) AS listen_usd"
    );
    // The all-in total keeps its own flag.
    expect(sql).toContain("SUM(IF(in_all_in, usd, NULL)) AS all_in_usd");
  });

  it("drops provisional rows like the producer's parity gate", () => {
    expect(spendDailyQuery("2026-11-04", 7)).toContain(
      "WHERE inputs_settled AND status != 'provisional'"
    );
  });

  it("rejects dates that are not real calendar days", () => {
    expect(isCalendarDate("2026-02-31")).toBe(false);
    expect(isCalendarDate("2026-02-29")).toBe(false);
    expect(isCalendarDate("2026-13-01")).toBe(false);
    expect(isCalendarDate("2024-02-29")).toBe(true);
    expect(isCalendarDate("2026-11-04")).toBe(true);
    expect(() => spendDailyQuery("2026-02-31", 7)).toThrow();
  });

  it("rejects inputs that are not a date or a bounded window", () => {
    expect(() => spendDailyQuery("2026-11-04; DROP", 7)).toThrow();
    expect(() => spendDailyQuery("2026-11-04", 0)).toThrow();
    expect(() => spendDailyQuery("2026-11-04", 1.5)).toThrow();
    expect(() => spendDailyQuery("2026-11-04", 401)).toThrow();
  });
});

describe("spendDays", () => {
  it("keeps missing sums as null, not zero, and sorts by day", () => {
    const days = spendDays([
      {
        day: "2026-11-05",
        variable_usd: "10.5",
        listen_usd: null,
        all_in_usd: "100",
        rows: "4",
      },
      {
        day: "2026-11-04",
        variable_usd: null,
        listen_usd: "2",
        all_in_usd: "3549.21",
        rows: 6,
      },
    ]);
    expect(days.map((d) => d.day)).toEqual(["2026-11-04", "2026-11-05"]);
    expect(days[0].variableUsd).toBeNull();
    expect(days[0].listenUsd).toBe(2);
    expect(days[1].listenUsd).toBeNull();
    expect(days[1].variableUsd).toBe(10.5);
  });
});

describe("parityDelta", () => {
  const day = (allInUsd: number | null) => [
    { day: PARITY_DAY, variableUsd: null, listenUsd: null, allInUsd, rows: 1 },
  ];

  it("passes at the contract value to the cent", () => {
    expect(parityDelta(day(PARITY_ALL_IN_USD))).toBe(0);
  });

  it("reports the difference when the total drifts", () => {
    expect(parityDelta(day(3549.5))).toBe(0.29);
  });

  it("is a gap, not a pass, when the anchor day is absent", () => {
    expect(parityDelta([])).toBeNull();
    expect(parityDelta(day(null))).toBeNull();
  });
});

describe("listenUsdPerAudioHour", () => {
  it("divides STT variable cost by wire audio hours", () => {
    expect(listenUsdPerAudioHour(120, 40)).toBe(3);
  });

  it("is null when either side is missing or hours are not positive", () => {
    expect(listenUsdPerAudioHour(null, 40)).toBeNull();
    expect(listenUsdPerAudioHour(120, null)).toBeNull();
    expect(listenUsdPerAudioHour(120, 0)).toBeNull();
  });
});

describe("variableCostPerPayingUserMonth", () => {
  const day = (variableUsd: number | null) => ({
    day: "2026-11-01",
    variableUsd,
    listenUsd: null,
    allInUsd: null,
    rows: 1,
  });

  it("scales the mean daily variable cost by 30.44 days, per paying user", () => {
    const days = [day(10), day(20)];
    expect(variableCostPerPayingUserMonth(days, 100)).toBeCloseTo(
      (15 * 30.44) / 100,
      10
    );
  });

  it("averages only covered days, so a gap does not drag the mean to zero", () => {
    const days = [day(10), day(null), day(20)];
    expect(variableCostPerPayingUserMonth(days, 100)).toBeCloseTo(
      (15 * 30.44) / 100,
      10
    );
  });

  it("is null without paying users or without any covered day", () => {
    expect(variableCostPerPayingUserMonth([day(10)], null)).toBeNull();
    expect(variableCostPerPayingUserMonth([day(10)], 0)).toBeNull();
    expect(variableCostPerPayingUserMonth([day(null)], 100)).toBeNull();
    expect(variableCostPerPayingUserMonth([], 100)).toBeNull();
  });
});
