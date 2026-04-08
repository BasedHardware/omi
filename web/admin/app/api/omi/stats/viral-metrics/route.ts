import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

let cache: { data: any; days: number; timestamp: number } | null = null;
const CACHE_TTL = 30 * 60 * 1000;

async function hogql(apiKey: string, projectId: string, host: string, query: string) {
  const resp = await fetch(`${host}/api/projects/${projectId}/query/`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`PostHog query error ${resp.status}: ${text.slice(0, 200)}`);
  }
  const raw = await resp.json();
  return raw.results || [];
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

    if (cache && cache.days === days && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json(cache.data);
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
    ] = await Promise.all([
      // 1. New users per week (first-ever Sign In Completed)
      hogql(apiKey, projectId, host, `
        SELECT
          toMonday(toDate(toString(min_ts))) as week,
          count(*) as new_users
        FROM (
          SELECT distinct_id, min(timestamp) as min_ts
          FROM events
          WHERE event = 'Sign In Completed'
            AND properties.$os_name = 'macOS'
          GROUP BY distinct_id
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
        WHERE event = 'App Became Active'
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval ${days} day
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
          WHERE event = 'App Became Active'
            AND properties.$os_name = 'macOS'
            AND timestamp >= now() - interval ${days} day
          GROUP BY did, week
        ) curr
        INNER JOIN (
          SELECT distinct_id as did, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE event = 'App Became Active'
            AND properties.$os_name = 'macOS'
            AND timestamp >= now() - interval ${days + 7} day
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
        WHERE event = 'App Became Active'
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval ${days} day
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
          WHERE event = 'App Became Active'
            AND properties.$os_name = 'macOS'
            AND timestamp >= now() - interval 30 day
          GROUP BY distinct_id
        )
        GROUP BY days_active
        ORDER BY days_active
      `),

      // 6. Activation: signups who created a Memory within 7 days
      hogql(apiKey, projectId, host, `
        SELECT
          toDate(toString(signup_ts)) as day,
          count(*) as signups,
          countIf(has_memory = 1) as activated
        FROM (
          SELECT
            s_id,
            s_ts as signup_ts,
            if(m_count > 0, 1, 0) as has_memory
          FROM (
            SELECT
              distinct_id as s_id,
              min(timestamp) as s_ts
            FROM events
            WHERE event = 'Sign In Completed'
              AND properties.$os_name = 'macOS'
              AND timestamp >= now() - interval ${days} day
            GROUP BY distinct_id
          ) signups
          LEFT JOIN (
            SELECT
              distinct_id as m_id,
              min(timestamp) as m_ts,
              count(*) as m_count
            FROM events
            WHERE event = 'Memory Created'
              AND properties.$os_name = 'macOS'
              AND timestamp >= now() - interval ${days + 7} day
            GROUP BY distinct_id
          ) memories ON signups.s_id = memories.m_id
            AND memories.m_ts >= signups.s_ts
            AND memories.m_ts <= signups.s_ts + interval 7 day
        )
        GROUP BY day
        ORDER BY day
      `),

      // 7. WAU (current week)
      hogql(apiKey, projectId, host, `
        SELECT count(DISTINCT distinct_id)
        FROM events
        WHERE event = 'App Became Active'
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval 7 day
      `),

      // 8. MAU (current month)
      hogql(apiKey, projectId, host, `
        SELECT count(DISTINCT distinct_id)
        FROM events
        WHERE event = 'App Became Active'
          AND properties.$os_name = 'macOS'
          AND timestamp >= now() - interval 30 day
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
    const activation: { date: string; signups: number; activated: number; rate: number }[] = [];
    for (const [day, signups, activated] of activationResults as any[]) {
      activation.push({
        date: day,
        signups,
        activated,
        rate: signups > 0 ? Math.round((activated / signups) * 1000) / 10 : 0,
      });
    }

    const totalSignups = activation.reduce((s, d) => s + d.signups, 0);
    const totalActivated = activation.reduce((s, d) => s + d.activated, 0);
    const overallActivationRate = totalSignups > 0
      ? Math.round((totalActivated / totalSignups) * 1000) / 10
      : null;

    // ── Quick Ratio ──
    const recentGA = growthAccounting.slice(-4);
    const totalNewGA = recentGA.reduce((s, w) => s + w.newUsers, 0);
    const totalResurrectedGA = recentGA.reduce((s, w) => s + w.resurrected, 0);
    const totalChurnedGA = recentGA.reduce((s, w) => s + Math.abs(w.churned), 0);
    const quickRatio = totalChurnedGA > 0
      ? Math.round(((totalNewGA + totalResurrectedGA) / totalChurnedGA) * 100) / 100
      : null;

    const result = {
      growthAccounting,
      stickinessTrend,
      dailyDau,
      powerUserCurve,
      activation,
      summary: {
        quickRatio,
        activationRate: overallActivationRate,
        dauMau,
        dauWau,
        dau: avgDau,
        wau,
        mau,
        l5PlusPct,
        totalUsers: totalPowerUsers,
      },
    };

    cache = { data: result, days, timestamp: Date.now() };
    return NextResponse.json(result);
  } catch (error: any) {
    console.error("Viral metrics error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch viral metrics" },
      { status: 500 }
    );
  }
}
