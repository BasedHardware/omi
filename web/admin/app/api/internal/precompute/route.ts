import { NextRequest, NextResponse } from "next/server";
import {
  computeProfitability,
  profitabilityCacheKey,
} from "@/app/api/omi/stats/profitability/route";
import {
  computeInfraCosts,
  infraCostsCacheKey,
} from "@/app/api/omi/stats/infra-costs/route";
import {
  computeDailyNewUsers,
  dailyNewUsersCacheKey,
} from "@/app/api/omi/stats/daily-new-users/route";
import {
  computeMacosVersions,
  macosVersionsCacheKey,
} from "@/app/api/omi/stats/macos-versions/route";
import {
  computeNotifications,
  notificationsCacheKey,
} from "@/app/api/omi/stats/notifications/route";
import {
  computeOnboarding,
  onboardingCacheKey,
} from "@/app/api/omi/stats/onboarding/posthog/route";
import {
  computeRevenue,
  revenueCacheKey,
} from "@/app/api/omi/stats/revenue/route";
import {
  computeMrrTrends,
  mrrTrendsCacheKey,
} from "@/app/api/omi/stats/mrr-trends/route";
import {
  computeSubscriptionTrends,
  subscriptionTrendsCacheKey,
} from "@/app/api/omi/stats/subscription-trends/route";
import {
  computeSubscriptions,
  subscriptionsCacheKey,
} from "@/app/api/omi/stats/subscriptions/route";
import {
  computeAppSubscriptions,
  appSubscriptionsCacheKey,
} from "@/app/api/omi/stats/app-subscriptions/route";
import { computeKFactor } from "@/app/api/omi/stats/k-factor/posthog/route";
import { setPayload } from "@/lib/payload-cache";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Cron-only precompute endpoint. Computes the heavy graph payloads off the
// request path (long timeout) and writes them to the Firestore payload cache,
// so the dashboard GET routes become fast cache reads.
//
// Auth: requires `x-cron-secret` header to equal `process.env.CRON_SECRET`.
// No admin auth — this is invoked by the scheduler, not a browser.
//
// Params MUST match the dashboard's default/initial query so the GET handlers
// hit the cache. From app/(protected)/dashboard/page.tsx:
//   profitability: days=30&desktop_cost=1.2&mobile_cost=0.3
//   infra-costs:   days=30 (overhead_monthly omitted → default 57447)
//   daily-new-users: days=all
//   macos-versions: (no params)
//   notifications: days=30
//   onboarding/posthog: days=30
//   revenue / subscriptions / app-subscriptions: (no params)
//   mrr-trends / subscription-trends: months=12
//   k-factor/posthog: days=30 (no payload cache — posthogResults caches the query)
//
// Sequential on purpose: PostHog is aggressively rate-limited, so we must NOT
// fire these concurrently.
const PROFIT_DAYS = 30;
const PROFIT_DESKTOP_COST = 1.2;
const PROFIT_MOBILE_COST = 0.3;
const INFRA_DAYS = 30;
const DAILY_NEW_USERS_DAYS = "all";
const NOTIFICATIONS_DAYS = 30;
const ONBOARDING_DAYS = 30;
const TRENDS_MONTHS = 12;
const K_FACTOR_DAYS = 30;

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

  const results: Record<string, string> = {};
  const ms: Record<string, number> = {};

  const run = async (name: string, fn: () => Promise<void>) => {
    const t0 = Date.now();
    try {
      await fn();
      results[name] = "ok";
    } catch (err: any) {
      results[name] = err?.message || "failed";
    }
    ms[name] = Date.now() - t0;
  };

  // Profitability
  await run("profitability", async () => {
    const payload = await computeProfitability({
      days: PROFIT_DAYS,
      desktopCost: PROFIT_DESKTOP_COST,
      mobileCost: PROFIT_MOBILE_COST,
    });
    await setPayload(
      profitabilityCacheKey(PROFIT_DAYS, PROFIT_DESKTOP_COST, PROFIT_MOBILE_COST),
      payload,
    );
  });

  // Infra costs
  await run("infraCosts", async () => {
    const overheadMonthly = defaultOverheadMonthly();
    const payload = await computeInfraCosts({ days: INFRA_DAYS, overheadMonthly });
    await setPayload(infraCostsCacheKey(INFRA_DAYS, overheadMonthly), payload);
  });

  // Daily new users
  await run("dailyNewUsers", async () => {
    const payload = await computeDailyNewUsers(DAILY_NEW_USERS_DAYS);
    await setPayload(dailyNewUsersCacheKey(DAILY_NEW_USERS_DAYS), payload);
  });

  // macOS versions
  await run("macosVersions", async () => {
    const payload = await computeMacosVersions();
    await setPayload(macosVersionsCacheKey(), payload);
  });

  // Notifications
  await run("notifications", async () => {
    const payload = await computeNotifications(NOTIFICATIONS_DAYS);
    await setPayload(notificationsCacheKey(NOTIFICATIONS_DAYS), payload);
  });

  // Onboarding funnel
  await run("onboarding", async () => {
    const payload = await computeOnboarding(ONBOARDING_DAYS);
    await setPayload(onboardingCacheKey(ONBOARDING_DAYS), payload);
  });

  // Revenue
  await run("revenue", async () => {
    const payload = await computeRevenue();
    await setPayload(revenueCacheKey(), payload);
  });

  // MRR trends
  await run("mrrTrends", async () => {
    const payload = await computeMrrTrends(TRENDS_MONTHS);
    await setPayload(mrrTrendsCacheKey(TRENDS_MONTHS), payload);
  });

  // Subscription trends
  await run("subscriptionTrends", async () => {
    const payload = await computeSubscriptionTrends(TRENDS_MONTHS);
    await setPayload(subscriptionTrendsCacheKey(TRENDS_MONTHS), payload);
  });

  // Subscriptions
  await run("subscriptions", async () => {
    const payload = await computeSubscriptions();
    await setPayload(subscriptionsCacheKey(), payload);
  });

  // App subscriptions
  await run("appSubscriptions", async () => {
    const payload = await computeAppSubscriptions();
    await setPayload(appSubscriptionsCacheKey(), payload);
  });

  // k-factor: no payload cache — calling compute warms its posthogResults
  // query cache (Firestore) so the GET serves fast from there.
  await run("kFactor", async () => {
    await computeKFactor(K_FACTOR_DAYS);
  });

  return NextResponse.json({ ok: true, results, ms });
}
