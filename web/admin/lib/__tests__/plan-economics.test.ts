import { beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import {
  buildPlanEconomics,
  type EconomicsSnapshot,
} from "@/lib/services/plan-economics";

const query = vi.hoisted(() => vi.fn());
const verifyAdmin = vi.hoisted(() => vi.fn());
vi.mock("@/lib/services/gcp-billing", () => ({
  getGcpBillingClient: () => ({ query }),
}));
vi.mock("@/lib/auth", () => ({ verifyAdmin }));

function fixture(): EconomicsSnapshot {
  const snapshot: EconomicsSnapshot = {
    costs: [],
    revenue: [],
    reconciliation: [],
  };
  for (let n = 10; n <= 16; n++) {
    const day = `2026-09-${n}`;
    for (const [segment, users, factor] of [
      ["operator", 2, 1],
      ["basic", 1, 0.5],
      ["all", 3, 1.5],
    ] as const) {
      for (const [component, usd] of Object.entries({
        variable_total: 8,
        vertex_pt_fixed: 2,
        fully_loaded: 10,
        stt_vendor_low: 1,
        stt_vendor_high: 1.8,
      })) {
        snapshot.costs.push({
          day,
          segment_type: segment === "all" ? "total" : "plan",
          segment,
          component:
            component as EconomicsSnapshot["costs"][number]["component"],
          usd: usd * factor,
          users,
          run_id: day,
          inputs_settled: true,
        });
      }
    }
    for (const pool of [
      "shared_gcp",
      "audio_pipeline_gcp",
      "vertex_paygo",
      "desktop_pools",
      "vertex_pt_fixed",
      "llm_openai",
      "llm_anthropic",
      "stt_vendor_low",
      "gcp_total_export",
      "one_time",
    ]) {
      snapshot.reconciliation.push({
        day,
        pool,
        delta_pct: 0,
        run_id: day,
        inputs_settled: true,
      });
    }
  }
  snapshot.revenue.push({
    day: "2026-09-16",
    plan: "operator",
    paying_subs: 10,
    mrr_usd: 500,
    snapshot_date: "2026-09-18",
    run_id: "2026-09-16",
  });
  return snapshot;
}

describe("plan economics snapshot", () => {
  it("normalizes costs once, keeps free costs, and uses the correct two denominators", () => {
    const result = buildPlanEconomics(fixture(), "2026-09-18");
    expect(result.partial).toBe(false);
    expect(result.rows[0]).toMatchObject({
      plan: "operator",
      mrr: 500,
      subscribers: 10,
      variableMonthly: 240,
      fixedMonthly: 60,
      allocatedMonthly: 300,
      estimatedSttMonthly: 30,
      estimatedCostMonthly: 330,
      estimatedMarginPct: 34,
      highSttMarginPct: 29.2,
      revenuePerSubscriber: 50,
      costPerSubscriber: 33,
      contributionPerSubscriber: 17,
      activeUsersPerDay: 2,
      costPerActiveDay: 5.5,
      unitBasis: "Subscriber units use paid subscriptions",
    });
    expect(result.rows[1]).toMatchObject({
      plan: "basic",
      mrr: 0,
      subscribers: 0,
      estimatedCostMonthly: 165,
      costPerSubscriber: null,
      revenuePerSubscriber: null,
      estimatedMarginPct: null,
      costPerActiveDay: 5.5,
      unitBasis: "Free: no paid subscribers",
    });
    expect(result.status[0]).toMatchObject({
      window: "2026-09-10 to 2026-09-16 (UTC)",
      revenueAsOf: "2026-09-18",
    });
  });

  it("suppresses every monetary figure when the feed has stopped", () => {
    const result = buildPlanEconomics(fixture(), "2026-09-25");
    expect(result.partial).toBe(true);
    expect(result.status[0].status).toContain("stale");
    expect(
      result.rows.every(
        (r) =>
          r.estimatedCostMonthly === null &&
          r.mrr === null &&
          r.costPerSubscriber === null
      )
    ).toBe(true);
  });

  it.each([
    "missing day",
    "missing component",
    "duplicate",
    "mixed run",
    "unsettled",
    "failed reconciliation",
    "missing reconciliation",
    "lost plan",
    "wrong user count",
  ])("does not publish misleading cost for %s", (defect) => {
    const s = fixture();
    if (defect === "missing day")
      s.costs = s.costs.filter((r) => r.day !== "2026-09-12");
    if (defect === "missing component") s.costs.splice(0, 1);
    if (defect === "duplicate") s.costs.push({ ...s.costs[0] });
    if (defect === "mixed run") s.costs[0].run_id = "new-load";
    if (defect === "unsettled") s.costs[0].inputs_settled = false;
    if (defect === "failed reconciliation") s.reconciliation[0].delta_pct = 2;
    if (defect === "missing reconciliation") s.reconciliation.splice(0, 1);
    if (defect === "wrong user count")
      s.costs
        .filter((r) => r.segment === "operator")
        .forEach((r) => {
          r.users += 1;
        });
    if (defect === "lost plan")
      s.costs = s.costs.filter((r) => r.segment !== "basic");
    const result = buildPlanEconomics(s, "2026-09-18");
    expect(result.partial).toBe(true);
    expect(result.rows.every((r) => r.estimatedCostMonthly === null)).toBe(
      true
    );
  });

  it("retains valid cost but never fabricates revenue or margin from a missing/stale revenue book", () => {
    for (const revenue of [
      [],
      [{ ...fixture().revenue[0], snapshot_date: "2026-09-01" }],
      [{ ...fixture().revenue[0], run_id: "different-load" }],
    ]) {
      const result = buildPlanEconomics(
        { ...fixture(), revenue },
        "2026-09-18"
      );
      expect(result.partial).toBe(true);
      expect(result.rows.find((r) => r.plan === "operator")).toMatchObject({
        mrr: null,
        estimatedCostMonthly: 330,
        estimatedMarginPct: null,
        costPerSubscriber: null,
      });
    }
  });

  it("does not invent a zero cost for a revenue-only plan and keeps unmapped cost visible", () => {
    const s = fixture();
    s.revenue[0].plan = "unlimited";
    const result = buildPlanEconomics(s, "2026-09-18");
    expect(result.rows.find((r) => r.plan === "unlimited")).toMatchObject({
      planName: "Omi Unlimited + Neo",
      mrr: 500,
      estimatedCostMonthly: null,
      estimatedMarginPct: null,
    });
    s.costs
      .filter((r) => r.segment === "basic")
      .forEach((r) => {
        r.segment = "legacy";
      });
    expect(
      buildPlanEconomics(s, "2026-09-18").rows.find((r) => r.plan === "legacy")
    ).toMatchObject({
      planName: "Unmapped (legacy)",
      estimatedCostMonthly: 165,
      mrr: null,
      costPerActiveDay: 5.5,
      unitBasis: "Revenue/subscriber mapping unavailable",
    });
  });

  it("uses calendar days for run rate and summed user-days for intermittent activity", () => {
    const s = fixture();
    s.costs = s.costs.filter(
      (r) => !(r.segment === "basic" && r.day === "2026-09-10")
    );
    s.costs
      .filter((r) => r.segment_type === "total" && r.day === "2026-09-10")
      .forEach((r) => {
        r.usd /= 1.5;
        r.users = 2;
      });
    expect(
      buildPlanEconomics(s, "2026-09-18").rows.find((r) => r.plan === "basic")
    ).toMatchObject({
      estimatedCostMonthly: 141.43,
      costPerActiveDay: 5.5,
      activeUsersPerDay: 0.86,
    });
  });
});

describe("plan economics route", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.clearAllMocks();
    verifyAdmin.mockResolvedValue({ uid: "admin" });
  });
  it("authenticates before reading billing data and rejects platform mislabelling", async () => {
    const { GET } = await import("@/app/api/omi/stats/plan-economics/route");
    verifyAdmin.mockResolvedValueOnce(
      NextResponse.json({ error: "Unauthorized" }, { status: 401 })
    );
    expect(
      (await GET(new NextRequest("http://local/api/omi/stats/plan-economics")))
        .status
    ).toBe(401);
    expect(
      (
        await GET(
          new NextRequest(
            "http://local/api/omi/stats/plan-economics?platform=macos"
          )
        )
      ).status
    ).toBe(400);
    expect(query).not.toHaveBeenCalled();
  });
  it("returns an error with no stale rows when BigQuery fails", async () => {
    query.mockRejectedValue(new Error("permission denied"));
    const { GET } = await import("@/app/api/omi/stats/plan-economics/route");
    const response = await GET(
      new NextRequest("http://local/api/omi/stats/plan-economics")
    );
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ rows: [], partial: true });
  });
  it("coalesces panel reads but retries after TTL, without serving last-good data on failure", async () => {
    query.mockResolvedValue([[{ snapshot: JSON.stringify(fixture()) }]]);
    const { fetchPlanEconomics } = await import(
      "@/lib/services/plan-economics"
    );
    const now = new Date("2026-09-18T12:00:00Z");
    const results = await Promise.all([
      fetchPlanEconomics(now),
      fetchPlanEconomics(now),
    ]);
    expect(results[0].rows[0].estimatedCostMonthly).toBe(330);
    expect(query).toHaveBeenCalledTimes(1);
    query.mockRejectedValue(new Error("query failed"));
    await expect(
      fetchPlanEconomics(new Date("2026-09-18T12:31:00Z"))
    ).rejects.toThrow("query failed");
    expect(query).toHaveBeenCalledTimes(2);
  });
});
