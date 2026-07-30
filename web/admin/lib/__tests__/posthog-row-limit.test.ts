import { describe, expect, it } from "vitest";

import { POSTHOG_SERVED_MAX_ROWS, withRowLimit } from "../posthog";

// #10190: PostHog silently fills LIMIT 100 into any HogQL (sub)query without
// one. withRowLimit binds one explicit outer LIMIT so the default cap can never
// truncate, and wraps in a subquery so a UNION's total (not just its last arm)
// is bounded.
describe("withRowLimit", () => {
  it("binds an explicit outer LIMIT at the served max by default", () => {
    const out = withRowLimit(
      "SELECT version, count() FROM events GROUP BY version",
    );
    expect(out).toContain(`LIMIT ${POSTHOG_SERVED_MAX_ROWS}`);
    // The served max is 50k, verified live (LIMIT 100000 returns 50000).
    expect(POSTHOG_SERVED_MAX_ROWS).toBe(50_000);
  });

  it("wraps in a subquery so the LIMIT binds the whole UNION, not the last arm", () => {
    const union = "SELECT 1 AS a UNION ALL SELECT 2 AS a";
    const out = withRowLimit(union);
    // The union must sit inside a subquery; the LIMIT must come after the close
    // paren, not inline with the last arm (which would bind that arm only).
    expect(out).toMatch(
      /SELECT \* FROM \(\s*[\s\S]*UNION ALL[\s\S]*\)\s*AS _row_limit_guard\s*LIMIT/,
    );
    const limitPos = out.lastIndexOf("LIMIT");
    const closeParenPos = out.lastIndexOf(")");
    expect(limitPos).toBeGreaterThan(closeParenPos);
  });

  it("is ceiling-only: a caller's tighter inner LIMIT is preserved inside the wrap", () => {
    const out = withRowLimit("SELECT * FROM events LIMIT 10");
    // The inner LIMIT 10 survives (inside the subquery); the outer is just a cap.
    expect(out).toContain("LIMIT 10");
    expect(out).toContain(`LIMIT ${POSTHOG_SERVED_MAX_ROWS}`);
    // Inner limit appears before the guard's outer limit.
    expect(out.indexOf("LIMIT 10")).toBeLessThan(
      out.lastIndexOf(`LIMIT ${POSTHOG_SERVED_MAX_ROWS}`),
    );
  });

  it("honors a custom max", () => {
    expect(withRowLimit("SELECT 1", 500)).toContain("LIMIT 500");
  });
});
