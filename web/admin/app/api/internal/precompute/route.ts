import { NextRequest, NextResponse } from "next/server";
import {
  computeProfitability,
  profitabilityCacheKey,
} from "@/app/api/omi/stats/profitability/route";
import {
  computeInfraCosts,
  infraCostsCacheKey,
} from "@/app/api/omi/stats/infra-costs/route";
import { setPayload } from "@/lib/payload-cache";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Cron-only precompute endpoint. Computes the heavy profitability + infra-costs
// payloads off the request path (long timeout) and writes them to the Firestore
// payload cache, so the dashboard GET routes become fast cache reads.
//
// Auth: requires `x-cron-secret` header to equal `process.env.CRON_SECRET`.
// No admin auth — this is invoked by the scheduler, not a browser.
//
// Params MUST match the dashboard's default/initial query so the GET handlers
// hit the cache. From app/(protected)/dashboard/page.tsx:
//   profitDays initial = 30; desktopCostInput "1.20" → 1.2; mobileCostInput "0.30" → 0.3
//   → profitability: days=30&desktop_cost=1.2&mobile_cost=0.3
//   → infra-costs:   days=30 (overhead_monthly omitted → default 57447)
const PROFIT_DAYS = 30;
const PROFIT_DESKTOP_COST = 1.2;
const PROFIT_MOBILE_COST = 0.3;
const INFRA_DAYS = 30;

function defaultOverheadMonthly(): number {
  const envOverhead = parseFloat(process.env.ADMIN_INFRA_OVERHEAD_MONTHLY || "");
  return Number.isFinite(envOverhead) && envOverhead >= 0 ? envOverhead : 57447;
}

export async function POST(request: NextRequest) {
  const secret = process.env.CRON_SECRET;
  const provided = request.headers.get("x-cron-secret");
  if (!secret || provided !== secret) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const results: { profitability: string; infraCosts: string } = {
    profitability: "ok",
    infraCosts: "ok",
  };
  const ms: { profitability: number; infraCosts: number } = {
    profitability: 0,
    infraCosts: 0,
  };

  // Profitability
  {
    const t0 = Date.now();
    try {
      const payload = await computeProfitability({
        days: PROFIT_DAYS,
        desktopCost: PROFIT_DESKTOP_COST,
        mobileCost: PROFIT_MOBILE_COST,
      });
      await setPayload(
        profitabilityCacheKey(PROFIT_DAYS, PROFIT_DESKTOP_COST, PROFIT_MOBILE_COST),
        payload,
      );
    } catch (err: any) {
      results.profitability = err?.message || "failed";
    }
    ms.profitability = Date.now() - t0;
  }

  // Infra costs
  {
    const t0 = Date.now();
    try {
      const overheadMonthly = defaultOverheadMonthly();
      const payload = await computeInfraCosts({ days: INFRA_DAYS, overheadMonthly });
      await setPayload(infraCostsCacheKey(INFRA_DAYS, overheadMonthly), payload);
    } catch (err: any) {
      results.infraCosts = err?.message || "failed";
    }
    ms.infraCosts = Date.now() - t0;
  }

  return NextResponse.json({ ok: true, results, ms });
}
