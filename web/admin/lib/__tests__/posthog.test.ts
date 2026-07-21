import { describe, expect, it } from "vitest";

import { POSTHOG_MAX_ROWS, withPosthogRowLimit } from "../posthog";

describe("withPosthogRowLimit", () => {
  it("wraps a LIMIT-less grouped query with an explicit outer limit", () => {
    const query = `
      SELECT version, event, count() AS cnt
      FROM events
      WHERE event IN ('App Crash Detected', 'App Launched')
      GROUP BY version, event
    `;
    const guarded = withPosthogRowLimit(query);
    expect(guarded).toContain(`LIMIT ${POSTHOG_MAX_ROWS}`);
    // The original query must survive intact inside the subquery so grouping,
    // aliases, and column order are unchanged.
    expect(guarded).toContain("GROUP BY version, event");
    expect(guarded).toMatch(/SELECT \* FROM \(/);
  });

  it("caps a UNION whose trailing LIMIT would otherwise bind to the last arm only", () => {
    // A trailing LIMIT on a UNION binds to the final arm, so a naive append
    // would not bound the whole result. Wrapping puts the limit outside both.
    const query = "SELECT 1 UNION ALL SELECT 2";
    const guarded = withPosthogRowLimit(query, 5);
    expect(guarded).toBe(
      "SELECT * FROM (\nSELECT 1 UNION ALL SELECT 2\n) LIMIT 5",
    );
  });

  it("keeps a caller-pinned inner limit authoritative (outer cap is a no-op)", () => {
    const guarded = withPosthogRowLimit("SELECT day FROM events LIMIT 10");
    // Inner LIMIT 10 binds first; the outer high cap never reduces below it.
    expect(guarded).toContain("LIMIT 10");
    expect(guarded).toContain(`LIMIT ${POSTHOG_MAX_ROWS}`);
  });

  it("strips a trailing semicolon so the subquery wrap stays valid", () => {
    const guarded = withPosthogRowLimit("SELECT day FROM events;");
    expect(guarded).not.toContain(";");
    expect(guarded).toBe(
      `SELECT * FROM (\nSELECT day FROM events\n) LIMIT ${POSTHOG_MAX_ROWS}`,
    );
  });

  it("defaults to PostHog's served maximum row count", () => {
    expect(POSTHOG_MAX_ROWS).toBe(50_000);
  });
});
