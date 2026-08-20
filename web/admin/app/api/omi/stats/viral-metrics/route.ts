import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import {
  applyFirestoreActivationCompat,
  type FirestoreActivationCompat,
} from "@/lib/activation-compat";
import { activationCacheKey } from "@/app/api/omi/stats/activation/route";
import { getPayload } from "@/lib/payload-cache";
import { posthogResults } from "@/lib/posthog";
import {
  summarizeActivation,
  type DailyActivationPoint,
} from "@/lib/growth-metrics";
import { parsePlatformScope, scopeFilterAnd } from "@/lib/platform-scope";

export const dynamic = "force-dynamic";

/**
 * First desktop build that emits `Memory Created` on the normal durable-session
 * path. Before 98f1ee7c7f the event only fired for recordings that failed to
 * bind a local session, so activation was structurally unreportable.
 */
const MIN_ACTIVATION_TELEMETRY_VERSION = [0, 12, 167] as const;

let cache: { data: any; days: number; platform: string; timestamp: number } | null = null;
const CACHE_TTL = 30 * 60 * 1000;

async function hogql(apiKey: string, projectId: string, host: string, query: string) {
  return posthogResults(host, projectId, apiKey, query);
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = process.env.POSTHOG_HOST || "https://us.posthog.com";

    if (!apiKey || !projectId) {
      return NextResponse.json(
        { error: "PostHog credentials not configured" },
        { status: 500 }
      );
    }

    const searchParams = request.nextUrl.searchParams;
    const days = Math.min(parseInt(searchParams.get("days") || "60", 10), 90);
    // Default macos preserves the legacy meaning for existing callers.
    const platform = parsePlatformScope(searchParams.get("platform") ?? "macos");
    const os = scopeFilterAnd(platform);
    // Mobile never emits `Sign In Completed`, so non-macOS activation cohorts
    // anchor on the user's first-ever event instead. Acquisition series
    // (weekly/daily new, cumulative, ticker) all use first-seen so every
    // panel agrees on one "new user" definition per platform.
    const activationAnchor = platform === "macos" ? `AND event = 'Sign In Completed' ${os}` : os;
    // The Firestore activation overlay is macOS-scoped by construction
    // (conversation-within-7-days of a macOS signup) — never smear it over
    // mobile or all-platform telemetry.
    const activationOverlay = async () =>
      platform === "macos"
        ? (await getPayload<FirestoreActivationCompat>(activationCacheKey(days)))?.data ?? null
        : null;

    if (cache && cache.days === days && cache.platform === platform && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json(
        applyFirestoreActivationCompat(cache.data, await activationOverlay()),
      );
    }

    // Run all queries in parallel - each is lightweight
    const [
      weeklyNewResults,
      weeklyActiveResults,
      weeklyRetainedResults,
      dailyDauResults,
      powerUserResults,
      activationResults,
      wauResult,
      mauResult,
      allTimeResult,
      userGrowthResult,
    ] = await Promise.all([
      // 1. New users per week — first-seen on this platform, the same
      // person-deduped population as the daily userGrowth series.
      hogql(apiKey, projectId, host, `
        SELECT
          toMonday(toDate(toString(min_ts))) as week,
          count(*) as new_users
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor, min(timestamp) as min_ts
          FROM events
          WHERE 1 = 1
            ${os}
          GROUP BY actor
        )
        WHERE min_ts >= now() - interval ${days} day
        GROUP BY week
        ORDER BY week
      `),

      // 2. Total active users per week
      hogql(apiKey, projectId, host, `
        SELECT
          toMonday(toDate(timestamp)) as week,
          count(DISTINCT distinct_id) as active_users
        FROM events
        WHERE timestamp >= now() - interval ${days} day
          ${os}
        GROUP BY week
        ORDER BY week
      `),

      // 3. Retained users per week (active in both current and previous week)
      // Use a self-join approach: find users active in consecutive weeks
      hogql(apiKey, projectId, host, `
        SELECT
          curr.week as curr_week,
          count(DISTINCT curr.did) as retained
        FROM (
          SELECT distinct_id as did, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= now() - interval ${days} day
            ${os}
          GROUP BY did, week
        ) curr
        INNER JOIN (
          SELECT distinct_id as did, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= now() - interval ${days + 7} day
            ${os}
          GROUP BY did, week
        ) prev ON curr.did = prev.did AND prev.week = curr.week - interval 7 day
        GROUP BY curr_week
        ORDER BY curr_week
      `),

      // 4. Daily DAU for stickiness trend
      hogql(apiKey, projectId, host, `
        SELECT
          toDate(timestamp) as day,
          count(DISTINCT distinct_id) as dau
        FROM events
        WHERE timestamp >= now() - interval ${days} day
          ${os}
        GROUP BY day
        ORDER BY day
      `),

      // 5. Power user curve - days active per user in last 30 days
      hogql(apiKey, projectId, host, `
        SELECT
          days_active,
          count(*) as user_count
        FROM (
          SELECT
            distinct_id,
            count(DISTINCT toDate(timestamp)) as days_active
          FROM events
          WHERE timestamp >= now() - interval 30 day
            ${os}
          GROUP BY distinct_id
        )
        GROUP BY days_active
        ORDER BY days_active
      `),

      // 6. Activation: new signups who created a Memory within 7 days.
      //
      // Three things this query has to get right, each of which silently
      // understated the rate before:
      //   - The cohort is the user's FIRST-EVER sign-in, matching query 1.
      //     Filtering by timestamp *before* the min() made every returning user
      //     who re-authenticated inside the window look like a new signup.
      //   - Activation tests for ANY memory inside the window. Keying off the
      //     user's earliest memory marked a returning user unactivated because
      //     their first-ever memory predates their window.
      //   - `reports_activation` records whether the build they signed up on can
      //     emit `Memory Created` at all. Desktop only began emitting it on the
      //     normal (durable-session) path in 98f1ee7c7f, first shipped in
      //     ${MIN_ACTIVATION_TELEMETRY_VERSION.join(".")}. Users on older builds
      //     cannot activate no matter what they do, so pooling them reports a
      //     rollout gap as a product failure.
      hogql(apiKey, projectId, host, `
        SELECT
          toDate(toString(s_ts)) as day,
          count(*) as signups,
          countIf(memories_in_window > 0) as activated,
          countIf(reports_activation) as capable_signups,
          countIf(reports_activation AND memories_in_window > 0) as capable_activated
        FROM (
          SELECT
            signups.s_id as s_id,
            signups.s_ts as s_ts,
            signups.reports_activation as reports_activation,
            countIf(
              memories.m_ts >= signups.s_ts
              AND memories.m_ts <= signups.s_ts + interval 7 day
            ) as memories_in_window
          FROM (
            SELECT
              distinct_id as s_id,
              min(timestamp) as s_ts,
              arrayMap(
                part -> toIntOrZero(part),
                splitByChar('.', coalesce(argMin(properties.$app_version, timestamp), '0'))
              ) >= [${MIN_ACTIVATION_TELEMETRY_VERSION.join(", ")}] as reports_activation
            FROM events
            WHERE 1 = 1
              ${activationAnchor}
            GROUP BY distinct_id
          ) signups
          LEFT JOIN (
            SELECT distinct_id as m_id, timestamp as m_ts
            FROM events
            WHERE event = 'Memory Created'
              ${os}
              AND timestamp >= now() - interval ${days + 7} day
          ) memories ON signups.s_id = memories.m_id
          WHERE signups.s_ts >= now() - interval ${days} day
          GROUP BY s_id, s_ts, reports_activation
        )
        GROUP BY day
        ORDER BY day
      `),

      // 7. WAU (current week)
      hogql(apiKey, projectId, host, `
        SELECT count(DISTINCT distinct_id)
        FROM events
        WHERE timestamp >= now() - interval 7 day
          ${os}
      `),

      // 8. MAU (current month)
      hogql(apiKey, projectId, host, `
        SELECT count(DISTINCT distinct_id)
        FROM events
        WHERE timestamp >= now() - interval 30 day
          ${os}
      `),

      // 9. All-time users on this platform (person-deduped, counted since
      // each platform's PostHog instrumentation began)
      hogql(apiKey, projectId, host, `
        SELECT uniq(COALESCE(person_id, distinct_id))
        FROM events
        WHERE 1 = 1
          ${os}
      `),

      // 10. Daily new users by first-seen date, same person-deduped
      // population as query 9 — its running sum must end at allTimeUsers so
      // the cumulative chart and the all-time ticker agree by construction.
      hogql(apiKey, projectId, host, `
        SELECT first_day, count(*) as new_users
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor,
                 toDate(min(timestamp)) as first_day
          FROM events
          WHERE 1 = 1
            ${os}
          GROUP BY actor
        )
        GROUP BY first_day
        ORDER BY first_day
      `),
    ]);

    // ── Process Growth Accounting ──
    const weeklyNew: Record<string, number> = {};
    for (const [week, count] of weeklyNewResults as any[]) weeklyNew[week] = count;

    const weeklyActive: Record<string, number> = {};
    for (const [week, count] of weeklyActiveResults as any[]) weeklyActive[week] = count;

    const weeklyRetained: Record<string, number> = {};
    for (const [week, count] of weeklyRetainedResults as any[]) weeklyRetained[week] = count;

    const allWeeks = Array.from(new Set([
      ...Object.keys(weeklyNew),
      ...Object.keys(weeklyActive),
      ...Object.keys(weeklyRetained),
    ])).sort();

    const growthAccounting = allWeeks.map((week) => {
      const active = weeklyActive[week] ?? 0;
      const newUsers = weeklyNew[week] ?? 0;
      const retained = weeklyRetained[week] ?? 0;
      const resurrected = Math.max(0, active - newUsers - retained);
      // Churned = previous week's active - this week's retained
      const prevWeekIdx = allWeeks.indexOf(week) - 1;
      const prevActive = prevWeekIdx >= 0 ? (weeklyActive[allWeeks[prevWeekIdx]] ?? 0) : 0;
      const churned = Math.max(0, prevActive - retained);

      return {
        week,
        active,
        newUsers,
        retained,
        resurrected,
        churned: -churned, // negative for stacked chart
      };
    });

    // ── Process DAU for Stickiness ──
    const dailyDau: { date: string; dau: number }[] = [];
    for (const [day, dau] of dailyDauResults as any[]) {
      dailyDau.push({ date: day, dau });
    }
    dailyDau.sort((a, b) => a.date.localeCompare(b.date));

    // Weekly stickiness: avg DAU / WAU for each week
    const wau = (wauResult as any[])[0]?.[0] ?? 0;
    const mau = (mauResult as any[])[0]?.[0] ?? 0;
    const allTimeUsers = (allTimeResult as any[])[0]?.[0] ?? 0;

    // ── User growth (first-seen daily + cumulative) ──
    const userGrowth: { date: string; users: number; cumulative: number }[] = [];
    let cumulative = 0;
    for (const [day, users] of userGrowthResult as any[]) {
      cumulative += users;
      userGrowth.push({ date: day, users, cumulative });
    }
    const recentDau = dailyDau.slice(-7);
    const avgDau = recentDau.length > 0
      ? Math.round(recentDau.reduce((s, d) => s + d.dau, 0) / recentDau.length)
      : 0;
    const dauMau = mau > 0 ? Math.round((avgDau / mau) * 1000) / 10 : 0;
    const dauWau = wau > 0 ? Math.round((avgDau / wau) * 1000) / 10 : 0;

    // Weekly stickiness trend
    const stickinessTrend: { week: string; dauWau: number; avgDau: number; wau: number }[] = [];
    for (const week of allWeeks) {
      const weekDate = new Date(week + "T00:00:00Z");
      let weekDauSum = 0;
      let weekDauCount = 0;
      for (let d = 0; d < 7; d++) {
        const dayDate = new Date(weekDate);
        dayDate.setUTCDate(dayDate.getUTCDate() + d);
        const dayStr = dayDate.toISOString().split("T")[0];
        const found = dailyDau.find((dd) => dd.date === dayStr);
        if (found) {
          weekDauSum += found.dau;
          weekDauCount++;
        }
      }
      const weekAvgDau = weekDauCount > 0 ? Math.round(weekDauSum / weekDauCount) : 0;
      const weekWau = weeklyActive[week] ?? 0;
      stickinessTrend.push({
        week,
        avgDau: weekAvgDau,
        wau: weekWau,
        dauWau: weekWau > 0 ? Math.round((weekAvgDau / weekWau) * 1000) / 10 : 0,
      });
    }

    // ── Process Power User Curve ──
    const powerUserMap: Record<number, number> = {};
    let totalPowerUsers = 0;
    for (const [daysActive, userCount] of powerUserResults as any[]) {
      powerUserMap[daysActive] = userCount;
      totalPowerUsers += userCount;
    }
    const maxDays = Math.min(
      30,
      Math.max(...Object.keys(powerUserMap).map(Number), 1)
    );
    const powerUserCurve: { daysActive: number; users: number; pct: number }[] = [];
    for (let d = 1; d <= maxDays; d++) {
      const users = powerUserMap[d] ?? 0;
      powerUserCurve.push({
        daysActive: d,
        users,
        pct: totalPowerUsers > 0 ? Math.round((users / totalPowerUsers) * 1000) / 10 : 0,
      });
    }

    // L5+/7 metric: users active 5+ days per week (approximate from 30-day data)
    const l5Plus = powerUserCurve
      .filter((p) => p.daysActive >= 20) // ~5 days/week over 30 days
      .reduce((s, p) => s + p.users, 0);
    const l5PlusPct = totalPowerUsers > 0
      ? Math.round((l5Plus / totalPowerUsers) * 1000) / 10
      : 0;

    // ── Process Activation ──
    const activation: (DailyActivationPoint & { rate: number })[] = [];
    for (const [day, signups, activated, capableSignups, capableActivated] of
      activationResults as any[]) {
      activation.push({
        date: day,
        signups,
        activated,
        capableSignups,
        capableActivated,
        rate: signups > 0 ? Math.round((activated / signups) * 1000) / 10 : 0,
      });
    }

    // Pooling every signup, including yesterday's, counts a guaranteed-zero
    // numerator against a real denominator; only matured days are summarised.
    const activationSummary = summarizeActivation(activation);

    // ── Quick Ratio ──
    const recentGA = growthAccounting.slice(-4);
    const totalNewGA = recentGA.reduce((s, w) => s + w.newUsers, 0);
    const totalResurrectedGA = recentGA.reduce((s, w) => s + w.resurrected, 0);
    const totalChurnedGA = recentGA.reduce((s, w) => s + Math.abs(w.churned), 0);
    const quickRatio = totalChurnedGA > 0
      ? Math.round(((totalNewGA + totalResurrectedGA) / totalChurnedGA) * 100) / 100
      : null;

    const result = applyFirestoreActivationCompat(
      {
        userGrowth,
        growthAccounting,
        stickinessTrend,
        dailyDau,
        powerUserCurve,
        activation,
        summary: {
          quickRatio,
          // Capability-aware until the Firestore activation cache exists. The
          // one-release compat shim below overlays the conversation-derived
          // rate so live Infinity panels do not stay blank.
          activationRate: activationSummary.capableRate,
          activationTelemetryCoverage: activationSummary.telemetryCoverage,
          activationSignups: activationSummary.capableSignups,
          activationPooledRate: activationSummary.rate,
          dauMau,
          dauWau,
          dau: avgDau,
          wau,
          mau,
          l5PlusPct,
          totalUsers: totalPowerUsers,
          allTimeUsers,
        },
      },
      await activationOverlay(),
    );

    cache = { data: result, days, platform, timestamp: Date.now() };
    return NextResponse.json(result);
  } catch (error: any) {
    console.error("Viral metrics error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch viral metrics" },
      { status: 500 }
    );
  }
}
