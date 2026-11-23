import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  activityQuery,
  cohortQuery,
  deviceFunnelQuery,
  mauOffsetsQuery,
} from "../wall-posthog";
import { SAMPLE_PCT_SQL, SAMPLE_WEIGHT_SQL } from "../posthog-sampling";

// Memory Created, Device Session Ended and Recording Started are kept for a
// stable 2% of distinct IDs since 2026-11-23 (contracts/analytics/posthog.json).
const end = new Date("2026-11-23T00:00:00Z");

describe("readers of sampled product events (SCA-3665)", () => {
  it("weights capture-only actors and counts foreground or MCP actors once", () => {
    const sql = activityQuery(end, 7, "active", 1);
    expect(sql).toContain(
      `if(countIf(cap)>0,maxIf(${SAMPLE_PCT_SQL},cap),100) cap_pct`
    );
    expect(sql).toContain("0 captures,1 fgn,100 cap_pct");
    expect(sql).toContain("sum(if(fg_any>0,1,100/pct_any))");
    expect(sql).not.toMatch(/SELECT period,p,count\(\)/);
  });

  it("weights every saved actor, since saved status is itself sampled", () => {
    expect(activityQuery(end, 7, "saved", 1)).toContain("sum(100/pct_any)");
    expect(activityQuery(end, 7, "assistant", 1)).toContain(
      "SELECT period,p,count()"
    );
  });

  it("weights MAU offsets per window", () => {
    const sql = mauOffsetsQuery(end, [0, 3]);
    expect(sql).toContain(`if(fg,100,${SAMPLE_PCT_SQL}) pct`);
    expect(sql).toContain("true seen,100 pct FROM mcp_days");
    expect(sql).toContain(
      "100/arrayMax(arrayMap(s -> tupleElement(s,4),hits))"
    );
  });

  it("weights capture outcomes in cohorts and the device funnel", () => {
    expect(cohortQuery(end, 7, 1)).toContain(
      "toInt64(round(sumIf(100/capture_pct,capture>0))) captured"
    );
    const funnel = deviceFunnelQuery(end);
    expect(funnel).toContain("sumIf(100/conv1_pct,conv1)");
    expect(funnel).toContain("sumIf(100/conv7_pct,conv7)");
  });

  it("weights viral-metrics Memory Created counts", () => {
    const route = readFileSync(
      "app/api/omi/stats/viral-metrics/route.ts",
      "utf8"
    );
    expect(route).toContain("${SAMPLE_PCT_SQL} as m_pct");
    expect(route).toContain("sumIf(100 / mem_pct, memories_in_window > 0)");
    expect(route).toContain(
      "round(sum(${SAMPLE_WEIGHT_SQL}))) as saved_conversations"
    );
    expect(SAMPLE_WEIGHT_SQL).toBe(`100 / ${SAMPLE_PCT_SQL}`);
  });
});
