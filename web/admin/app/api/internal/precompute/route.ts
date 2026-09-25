import { NextRequest, NextResponse } from "next/server";
import {
  computeProfitability,
  parseProfitabilityParams,
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
import {
  computeActivation,
  activationCacheKey,
} from "@/app/api/omi/stats/activation/route";
import { setPayload } from "@/lib/payload-cache";

// Health payload key for this cron. A future panel/alert reads it to tell
// "the cron ran and everything succeeded" apart from "the cron has not run
// since Tuesday" — neither of which the per-metric caches can express.
export const PRECOMPUTE_STATUS_KEY = "precompute-status:v1";

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
//   profitability: days=30 (no desktop_cost/mobile_cost — the honest default
//     path: cost comes from billing, not from a per-user assumption)
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
const INFRA_DAYS = 30;
const DAILY_NEW_USERS_DAYS = "all";
const NOTIFICATIONS_DAYS = 30;
const ONBOARDING_DAYS = 30;
const TRENDS_MONTHS = 12;
const K_FACTOR_DAYS = 30;
// Activation fans out one aggregation query per macOS signup in the window, so
// it belongs here behind the long timeout rather than on the request path.
const ACTIVATION_DAYS = 60;

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

  const ok: string[] = [];
  const failed: Record<string, string> = {};

  // Per-metric isolation is deliberate: one dead upstream must not cost the
  // other twelve payloads. But a swallowed error used to be indistinguishable
  // from success in the logs and in the response, so a metric could serve a
  // week-old payload with nothing anywhere saying why.
  const run = async (name: string, fn: () => Promise<void>) => {
    const t0 = Date.now();
    try {
      await fn();
      results[name] = "ok";
      ok.push(name);
    } catch (err: any) {
      const message = err?.message || "failed";
      results[name] = message;
      failed[name] = message;
      console.error(`[precompute] ${name} FAILED:`, message, err);
    }
    ms[name] = Date.now() - t0;
  };

  // Profitability. Params go through the GET handler's own parser with only
  // `days` set, so the key written here is byte-identical to the key a request
  // carrying no cost params looks up.
  await run("profitability", async () => {
    const { days, desktopCost, mobileCost } = parseProfitabilityParams(
      new URLSearchParams({ days: String(PROFIT_DAYS) }),
    );
    const payload = await computeProfitability({ days, desktopCost, mobileCost });
    await setPayload(profitabilityCacheKey(days, desktopCost, mobileCost), payload);
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

  // Activation (Firestore conversation records, not desktop telemetry)
  await run("activation", async () => {
    const payload = await computeActivation(ACTIVATION_DAYS);
    await setPayload(activationCacheKey(ACTIVATION_DAYS), payload);
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
  // query cache (Firestore) so the GET serves fast from there. All three
  // platform scopes are warmed because each Grafana board queries its own.
  await run("kFactor", async () => {
    await computeKFactor(K_FACTOR_DAYS, "macos");
    await computeKFactor(K_FACTOR_DAYS, "mobile");
    await computeKFactor(K_FACTOR_DAYS, "all");
  });

  const failedNames = Object.keys(failed);
  if (failedNames.length > 0) {
    console.error(
      `[precompute] run finished with ${failedNames.length} failed metric(s): ${failedNames.join(", ")}`,
    );
  }

  const status = { ranAt: Date.now(), ok, failed };
  await setPayload(PRECOMPUTE_STATUS_KEY, status);

  return NextResponse.json({ ok, failed, results, ms, ranAt: status.ranAt });
}
