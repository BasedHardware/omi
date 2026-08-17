import { expect, test } from "bun:test";
import { resolveTemporal, type TypedTemporalExpr } from "./temporal";

const clock = { query_at: "2026-07-30T16:00:00Z", capture_at: "2026-06-15T16:00:00Z" };
const cases: readonly [string, TypedTemporalExpr, string, { start: string; end: string }][] = [
  ["last week", { kind: "relative", anchor: "query", unit: "week", offset: -1 }, "America/New_York", { start: "2026-07-20T04:00:00.000Z", end: "2026-07-27T04:00:00.000Z" }],
  ["last month", { kind: "relative", anchor: "query", unit: "month", offset: -1 }, "America/New_York", { start: "2026-06-01T04:00:00.000Z", end: "2026-07-01T04:00:00.000Z" }],
  ["DST boundary week", { kind: "relative", anchor: "query", unit: "week", offset: 0 }, "America/New_York", { start: "2026-03-02T05:00:00.000Z", end: "2026-03-09T04:00:00.000Z" }],
];
for (const [name, expr, timezone, expected] of cases) test(`G0 resolves ${name} as a timezone-aware half-open interval`, () => {
  const reference = name === "DST boundary week" ? { query_at: "2026-03-08T16:00:00Z" } : clock;
  expect(resolveTemporal(expr, reference, timezone)).toMatchObject({ kind: "calendar_interval", ...expected });
});
test("G0 preserves imprecise time as its supplied coarse bucket", () => {
  expect(resolveTemporal({ kind: "imprecise", bucket: "summer-2026", precision: "season" }, clock, "America/New_York")).toEqual({ kind: "imprecise", bucket: "summer-2026", precision: "season", timezone: "America/New_York" });
});
test("G0 distinguishes capture and query anchors without ambient time", () => {
  const query = resolveTemporal({ kind: "relative", anchor: "query", unit: "month", offset: 0 }, clock, "UTC");
  const capture = resolveTemporal({ kind: "relative", anchor: "capture", unit: "month", offset: 0 }, clock, "UTC");
  expect([query.start, capture.start]).toEqual(["2026-07-01T00:00:00.000Z", "2026-06-01T00:00:00.000Z"]);
});
test("G0 adversarial offsetless clocks have identical behavior under UTC and Los Angeles ambient TZ", () => {
  const original = process.env.TZ;
  const resolveUnder = (ambientTZ: string): string => {
    process.env.TZ = ambientTZ;
    try {
      // This falls on Dec 31 in New York when parsed as UTC, but Jan 1 when
      // ambient Los Angeles parsing is allowed; the pre-fix code diverged.
      return JSON.stringify(resolveTemporal({ kind: "relative", anchor: "query", unit: "day", offset: 0 }, { query_at: "2026-01-01T02:00:00" }, "America/New_York"));
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  };
  try {
    const utc = resolveUnder("UTC");
    const losAngeles = resolveUnder("America/Los_Angeles");
    expect(utc).toBe(losAngeles);
    expect(utc).toContain("RFC3339 timestamp with an explicit offset");
  } finally {
    if (original === undefined) delete process.env.TZ;
    else process.env.TZ = original;
  }
});
