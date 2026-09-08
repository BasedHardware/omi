import { describe, expect, it } from "vitest";

import {
  JOURNAL_PUMP_BASE_INTERVAL_MS,
  JOURNAL_PUMP_MAX_INTERVAL_MS,
  nextJournalPumpDelayMs,
} from "../src/runtime/journal-pump-backoff.js";

describe("nextJournalPumpDelayMs", () => {
  it("runs at base cadence while healthy (streak 0)", () => {
    expect(nextJournalPumpDelayMs(0)).toBe(JOURNAL_PUMP_BASE_INTERVAL_MS);
  });

  it("doubles the delay on each consecutive failure", () => {
    expect(nextJournalPumpDelayMs(1)).toBe(1_000);
    expect(nextJournalPumpDelayMs(2)).toBe(2_000);
    expect(nextJournalPumpDelayMs(3)).toBe(4_000);
    expect(nextJournalPumpDelayMs(4)).toBe(8_000);
  });

  it("saturates at the cap so a durable poison throttles to ~1/min, not 60/min", () => {
    expect(nextJournalPumpDelayMs(7)).toBe(JOURNAL_PUMP_MAX_INTERVAL_MS);
    expect(nextJournalPumpDelayMs(100)).toBe(JOURNAL_PUMP_MAX_INTERVAL_MS);
    expect(nextJournalPumpDelayMs(Number.POSITIVE_INFINITY)).toBe(JOURNAL_PUMP_BASE_INTERVAL_MS);
  });

  it("treats a reset/negative/non-integer streak as healthy base cadence", () => {
    expect(nextJournalPumpDelayMs(-3)).toBe(JOURNAL_PUMP_BASE_INTERVAL_MS);
    expect(nextJournalPumpDelayMs(Number.NaN)).toBe(JOURNAL_PUMP_BASE_INTERVAL_MS);
    // A fractional streak floors to the lower step rather than over-delaying.
    expect(nextJournalPumpDelayMs(2.9)).toBe(2_000);
  });
});
