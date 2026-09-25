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
  completedEstablishedRetention,
  completedWeeklyGrowthAccounting,
  rollingGrowthSummary,
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

let cache: {
  data: any;
  days: number;
  platform: string;
  timestamp: number;
} | null = null;
const CACHE_TTL = 30 * 60 * 1000;

async function hogql(
  apiKey: string,
  projectId: string,
  host: string,
  query: string
) {
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
    const platform = parsePlatformScope(
      searchParams.get("platform") ?? "macos"
    );
    const os = scopeFilterAnd(platform);
    // Mobile never emits `Sign In Completed`, so non-macOS activation cohorts
    // anchor on the user's first-ever event instead. Acquisition series
    // (weekly/daily new, cumulative, ticker) all use first-seen so every
    // panel agrees on one "new user" definition per platform.
    const activationAnchor =
      platform === "macos" ? `AND event = 'Sign In Completed' ${os}` : os;
    // The Firestore activation overlay is macOS-scoped by construction
    // (conversation-within-7-days of a macOS signup) — never smear it over
    // mobile or all-platform telemetry.
    const activationOverlay = async () =>
      platform === "macos"
        ? (
            await getPayload<FirestoreActivationCompat>(
              activationCacheKey(days)
            )
          )?.data ?? null
        : null;

    if (
      cache &&
      cache.days === days &&
      cache.platform === platform &&
      Date.now() - cache.timestamp < CACHE_TTL
    ) {
      return NextResponse.json(
        applyFirestoreActivationCompat(cache.data, await activationOverlay())
      );
    }

    // Run all queries in parallel - each is lightweight
    const [
      weeklyNewResults,
      weeklyActiveResults,
      weeklyRetainedResults,
      establishedRetentionResults,
      dailyDauResults,
      powerUserResults,
      activationResults,
      wauResult,
      mauResult,
      allTimeResult,
      userGrowthResult,
      rolling24hDauResult,
      rolling24hNewResult,
      rolling7dNewResult,
      rollingRetentionResult,
      meaningfulUsageResults,
      assistantUsageResults,
      captureUsageResults,
    ] = await Promise.all([
      // 1. New users per week — first-seen on this platform, the same
      // person-deduped population as the daily userGrowth series. Fetch two
      // extra weeks so the first displayed complete week has prior context.
      hogql(
        apiKey,
        projectId,
        host,
        `
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
        WHERE min_ts >= toMonday(now() - interval ${days} day) - interval 14 day
        GROUP BY week
        ORDER BY week
      `
      ),

      // 2. Total active users per week. `actor` is the one identity used by
      // every growth, DAU, stickiness, and power-user query below.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          week,
          count(*) as active_users
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor,
                 toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 14 day
            ${os}
          GROUP BY actor, week
        )
        GROUP BY week
        ORDER BY week
      `
      ),

      // 3. Retained users per week (active in both current and previous week)
      // Use a self-join approach: find users active in consecutive weeks
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          curr.week as curr_week,
          count(curr.actor) as retained
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 14 day
            ${os}
          GROUP BY actor, week
        ) curr
        INNER JOIN (
          SELECT COALESCE(person_id, distinct_id) as actor, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 14 day
            ${os}
          GROUP BY actor, week
        ) prev ON curr.actor = prev.actor AND prev.week = curr.week - interval 7 day
        GROUP BY curr_week
        ORDER BY curr_week
      `
      ),

      // 4. Established-user retention: people active in each of the two
      // preceding complete weeks, then active again in the current week.
      // The route filters the current partial week after the query returns.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          anchor.week + interval 14 day as curr_week,
          count(anchor.actor) as established,
          countIf(w2.week = anchor.week + interval 14 day) as retained
        FROM (
          SELECT w0.week, w0.actor
          FROM (
            SELECT COALESCE(person_id, distinct_id) as actor, toMonday(toDate(timestamp)) as week
            FROM events
            WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 21 day
              ${os}
            GROUP BY actor, week
          ) w0
          INNER JOIN (
            SELECT COALESCE(person_id, distinct_id) as actor, toMonday(toDate(timestamp)) as week
            FROM events
            WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 21 day
              ${os}
            GROUP BY actor, week
          ) w1 ON w0.actor = w1.actor AND w1.week = w0.week + interval 7 day
        ) anchor
        LEFT JOIN (
          SELECT COALESCE(person_id, distinct_id) as actor, toMonday(toDate(timestamp)) as week
          FROM events
          WHERE timestamp >= toMonday(now() - interval ${days} day) - interval 21 day
            ${os}
          GROUP BY actor, week
        ) w2 ON w2.actor = anchor.actor
          AND w2.week = anchor.week + interval 14 day
        GROUP BY curr_week
        ORDER BY curr_week
      `
      ),

      // 5. Daily DAU for stickiness trend
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          day,
          count(*) as dau
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor, toDate(timestamp) as day
          FROM events
          WHERE timestamp >= now() - interval ${days} day
            ${os}
          GROUP BY actor, day
        )
        GROUP BY day
        ORDER BY day
      `
      ),

      // 6. Power user curve - days active per person in last 30 days
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          days_active,
          count(*) as user_count
        FROM (
          SELECT
            COALESCE(person_id, distinct_id) as actor,
            count(DISTINCT toDate(timestamp)) as days_active
          FROM events
          WHERE timestamp >= now() - interval 30 day
            ${os}
          GROUP BY actor
        )
        GROUP BY days_active
        ORDER BY days_active
      `
      ),

      // 7. Activation: new signups who created a Memory within 7 days.
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
      hogql(
        apiKey,
        projectId,
        host,
        `
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
              COALESCE(person_id, distinct_id) as s_id,
              min(timestamp) as s_ts,
              arrayMap(
                part -> toIntOrZero(part),
                splitByChar('.', coalesce(argMin(properties.$app_version, timestamp), '0'))
              ) >= [${MIN_ACTIVATION_TELEMETRY_VERSION.join(
                ", "
              )}] as reports_activation
            FROM events
            WHERE 1 = 1
              ${activationAnchor}
            GROUP BY s_id
          ) signups
          LEFT JOIN (
            SELECT COALESCE(person_id, distinct_id) as m_id, timestamp as m_ts
            FROM events
            WHERE event = 'Memory Created'
              AND (properties.memory_result IS NULL OR properties.memory_result = 'saved')
              AND (properties.memory_discarded IS NULL OR properties.memory_discarded = false)
              ${os}
              AND timestamp >= now() - interval ${days + 7} day
          ) memories ON signups.s_id = memories.m_id
          WHERE signups.s_ts >= now() - interval ${days} day
          GROUP BY s_id, s_ts, reports_activation
        )
        GROUP BY day
        ORDER BY day
      `
      ),

      // 8. WAU (rolling current 7d)
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*) FROM (
          SELECT COALESCE(person_id, distinct_id) as actor
          FROM events
          WHERE timestamp >= now() - interval 7 day
            ${os}
          GROUP BY actor
        )
      `
      ),

      // 9. MAU (current month)
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*) FROM (
          SELECT COALESCE(person_id, distinct_id) as actor
          FROM events
          WHERE timestamp >= now() - interval 30 day
            ${os}
          GROUP BY actor
        )
      `
      ),

      // 10. All-time users on this platform (person-deduped, counted since
      // each platform's PostHog instrumentation began). Keep this exact
      // grouped count aligned with the cumulative userGrowth series; an
      // approximate uniq() result can disagree with that ticker.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*)
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor
          FROM events
          WHERE 1 = 1
            ${os}
          GROUP BY actor
        )
      `
      ),

      // 11. Daily new users by first-seen date, same person-deduped
      // population as query 9 — its running sum must end at allTimeUsers so
      // the cumulative chart and the all-time ticker agree by construction.
      hogql(
        apiKey,
        projectId,
        host,
        `
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
      `
      ),

      // 12. Rolling last-24h DAU — the trailing daily bucket must not look
      // like a crash just because the day started.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*) FROM (
          SELECT COALESCE(person_id, distinct_id) as actor
          FROM events
          WHERE timestamp >= now() - interval 24 hour
            ${os}
          GROUP BY actor
        )
      `
      ),

      // 13. Rolling last-24h new users (first-seen).
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*)
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor, min(timestamp) as min_ts
          FROM events
          WHERE 1 = 1
            ${os}
          GROUP BY actor
        )
        WHERE min_ts >= now() - interval 24 hour
      `
      ),

      // 14. Rolling last-7d new users (first-seen) for the separate rolling summary.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT count(*)
        FROM (
          SELECT COALESCE(person_id, distinct_id) as actor, min(timestamp) as min_ts
          FROM events
          WHERE 1 = 1
            ${os}
          GROUP BY actor
        )
        WHERE min_ts >= now() - interval 7 day
      `
      ),

      // 15. Rolling 7d retention pair: retained (active both in the last 7d
      // and the 7d before) and prior-window active, for the trailing
      // growth-accounting bucket.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          countIf(cur = 1 AND prev = 1) as retained,
          countIf(prev = 1) as prev_active
        FROM (
          SELECT
            COALESCE(person_id, distinct_id) as actor,
            maxIf(1, timestamp >= now() - interval 7 day) as cur,
            maxIf(1, timestamp < now() - interval 7 day) as prev
          FROM events
          WHERE timestamp >= now() - interval 14 day
            ${os}
          GROUP BY actor
        )
      `
      ),

      // 16. Meaningful capture proxy: unique people with a successfully
      // saved/reconciled conversation. Flutter supplies saved/discarded;
      // macOS has no result field and its Memory Created event is already the
      // post-reconciliation conversation-created signal.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          toDate(timestamp) as day,
          uniq(COALESCE(person_id, distinct_id)) as conversation_creators,
          count(*) as saved_conversations
        FROM events
        WHERE event = 'Memory Created'
          AND (properties.memory_result IS NULL OR properties.memory_result = 'saved')
          AND (properties.memory_discarded IS NULL OR properties.memory_discarded = false)
          AND timestamp >= toDate(now()) - interval ${days} day
          AND toDate(timestamp) < toDate(now())
          ${os}
        GROUP BY day
        ORDER BY day
      `
      ),

      // 17. Successful assistant turns. This event is currently macOS-only;
      // the board labels that coverage rather than combining it with capture.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          toDate(timestamp) as day,
          uniq(COALESCE(person_id, distinct_id)) as assistant_users,
          count(*) as completed_assistant_interactions
        FROM events
        WHERE event = 'chat_agent_query_completed'
          AND timestamp >= toDate(now()) - interval ${days} day
          AND toDate(timestamp) < toDate(now())
          ${os}
        GROUP BY day
        ORDER BY day
      `
      ),

      // 18. Successful desktop capture output. A Recording Started event is
      // only an attempt; this metric requires the authoritative stopped event
      // to carry positive transcript word_count.
      hogql(
        apiKey,
        projectId,
        host,
        `
        SELECT
          toDate(timestamp) as day,
          uniq(COALESCE(person_id, distinct_id)) as transcribed_speech_users,
          count(*) as transcribed_speech_stops
        FROM events
        WHERE event = 'Desktop Recording Stopped'
          AND properties.word_count > 0
          AND timestamp >= toDate(now()) - interval ${days} day
          AND toDate(timestamp) < toDate(now())
          ${os}
        GROUP BY day
        ORDER BY day
      `
      ),
    ]);

    // ── Process Growth Accounting ──
    const weeklyNew: Record<string, number> = {};
    for (const [week, count] of weeklyNewResults as any[])
      weeklyNew[week] = Number(count ?? 0);

    const weeklyActive: Record<string, number> = {};
    for (const [week, count] of weeklyActiveResults as any[])
      weeklyActive[week] = Number(count ?? 0);

    const weeklyRetained: Record<string, number> = {};
    for (const [week, count] of weeklyRetainedResults as any[])
      weeklyRetained[week] = Number(count ?? 0);

    const weeklyInputs = Array.from(
      new Set([
        ...Object.keys(weeklyNew),
        ...Object.keys(weeklyActive),
        ...Object.keys(weeklyRetained),
      ])
    ).map((week) => ({
      week,
      active: weeklyActive[week] ?? 0,
      newUsers: weeklyNew[week] ?? 0,
      retained: weeklyRetained[week] ?? 0,
    }));
    const growthAccounting = completedWeeklyGrowthAccounting(
      weeklyInputs,
      new Date(),
      days
    );
    const allWeeks = growthAccounting.map((point) => point.week);

    const establishedInputs = (establishedRetentionResults as any[]).map(
      ([week, established, retained]) => ({
        week,
        established: Number(established ?? 0),
        retained: Number(retained ?? 0),
      })
    );
    const establishedRetention = completedEstablishedRetention(
      establishedInputs,
      new Date(),
      days
    );

    // Rolling summary is deliberately separate from the complete-week
    // history. It is useful for current monitoring but must never masquerade
    // as a calendar week in the growth chart.
    const rollingPair = (rollingRetentionResult as any[])[0] ?? [0, 0];
    const rollingGrowth = rollingGrowthSummary({
      active: Number((wauResult as any[])[0]?.[0] ?? 0),
      priorActive: Number(rollingPair[1] ?? 0),
      newUsers: Number((rolling7dNewResult as any[])[0]?.[0] ?? 0),
      retained: Number(rollingPair[0] ?? 0),
    });

    // ── Process DAU for Stickiness ──
    const dailyDau: { date: string; dau: number }[] = [];
    for (const [day, dau] of dailyDauResults as any[]) {
      dailyDau.push({ date: day, dau });
    }
    dailyDau.sort((a, b) => a.date.localeCompare(b.date));

    // Trailing daily bucket = the last 24 hours, not since-midnight.
    const rolling24hDau = Number((rolling24hDauResult as any[])[0]?.[0] ?? 0);
    const todayUtc = new Date().toISOString().slice(0, 10);
    if (
      dailyDau.length > 0 &&
      dailyDau[dailyDau.length - 1].date === todayUtc
    ) {
      dailyDau[dailyDau.length - 1].dau = rolling24hDau;
    } else {
      dailyDau.push({ date: todayUtc, dau: rolling24hDau });
    }

    // Weekly stickiness: avg DAU / WAU for each week
    const wau = (wauResult as any[])[0]?.[0] ?? 0;
    const mau = (mauResult as any[])[0]?.[0] ?? 0;
    const allTimeUsers = (allTimeResult as any[])[0]?.[0] ?? 0;

    // ── User growth (first-seen daily + cumulative) ──
    const userGrowth: { date: string; users: number; cumulative: number }[] =
      [];
    let cumulative = 0;
    for (const [day, users] of userGrowthResult as any[]) {
      cumulative += users;
      userGrowth.push({ date: day, users, cumulative });
    }
    // Trailing bucket shows first-seen users of the last 24 hours; the
    // cumulative line stays calendar-exact (ends at allTimeUsers).
    const rolling24hNew = Number((rolling24hNewResult as any[])[0]?.[0] ?? 0);
    if (
      userGrowth.length > 0 &&
      userGrowth[userGrowth.length - 1].date === todayUtc
    ) {
      userGrowth[userGrowth.length - 1].users = rolling24hNew;
    } else if (userGrowth.length > 0) {
      userGrowth.push({ date: todayUtc, users: rolling24hNew, cumulative });
    }
    const recentDau = dailyDau.slice(-7);
    const avgDau =
      recentDau.length > 0
        ? Math.round(
            recentDau.reduce((s, d) => s + d.dau, 0) / recentDau.length
          )
        : 0;
    const dauMau = mau > 0 ? Math.round((avgDau / mau) * 1000) / 10 : 0;
    const dauWau = wau > 0 ? Math.round((avgDau / wau) * 1000) / 10 : 0;

    // Weekly stickiness trend
    const stickinessTrend: {
      week: string;
      dauWau: number;
      avgDau: number;
      wau: number;
    }[] = [];
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
      const weekAvgDau =
        weekDauCount > 0 ? Math.round(weekDauSum / weekDauCount) : 0;
      const weekWau = weeklyActive[week] ?? 0;
      stickinessTrend.push({
        week,
        avgDau: weekAvgDau,
        wau: weekWau,
        dauWau:
          weekWau > 0 ? Math.round((weekAvgDau / weekWau) * 1000) / 10 : 0,
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
    const powerUserCurve: { daysActive: number; users: number; pct: number }[] =
      [];
    for (let d = 1; d <= maxDays; d++) {
      const users = powerUserMap[d] ?? 0;
      powerUserCurve.push({
        daysActive: d,
        users,
        pct:
          totalPowerUsers > 0
            ? Math.round((users / totalPowerUsers) * 1000) / 10
            : 0,
      });
    }

    // L5+/7 metric: users active 5+ days per week (approximate from 30-day data)
    const l5Plus = powerUserCurve
      .filter((p) => p.daysActive >= 20) // ~5 days/week over 30 days
      .reduce((s, p) => s + p.users, 0);
    const l5PlusPct =
      totalPowerUsers > 0
        ? Math.round((l5Plus / totalPowerUsers) * 1000) / 10
        : 0;

    // ── Process meaningful usage proxies ──
    // Keep each successful event family separate. Their coverage and unit of
    // success differ, so a composite "engaged" number would hide gaps.
    const usageByDay = new Map<
      string,
      {
        conversationCreators: number;
        savedConversations: number;
        assistantUsers: number;
        completedAssistantInteractions: number;
        transcribedSpeechUsers: number;
        transcribedSpeechStops: number;
      }
    >();
    const usagePoint = (day: unknown) => {
      const key = String(day ?? "");
      const current = usageByDay.get(key) ?? {
        conversationCreators: 0,
        savedConversations: 0,
        assistantUsers: 0,
        completedAssistantInteractions: 0,
        transcribedSpeechUsers: 0,
        transcribedSpeechStops: 0,
      };
      usageByDay.set(key, current);
      return current;
    };
    for (const [
      day,
      creators,
      conversations,
    ] of meaningfulUsageResults as any[]) {
      const point = usagePoint(day);
      point.conversationCreators = Number(creators ?? 0);
      point.savedConversations = Number(conversations ?? 0);
    }
    for (const [day, users, interactions] of assistantUsageResults as any[]) {
      const point = usagePoint(day);
      point.assistantUsers = Number(users ?? 0);
      point.completedAssistantInteractions = Number(interactions ?? 0);
    }
    for (const [day, users, stops] of captureUsageResults as any[]) {
      const point = usagePoint(day);
      point.transcribedSpeechUsers = Number(users ?? 0);
      point.transcribedSpeechStops = Number(stops ?? 0);
    }
    const meaningfulUsage = Array.from(usageByDay, ([date, values]) => ({
      date,
      ...values,
    }))
      .filter((point) => point.date)
      .sort((a, b) => a.date.localeCompare(b.date));

    // ── Process Activation ──
    const activation: (DailyActivationPoint & { rate: number })[] = [];
    for (const [
      day,
      signups,
      activated,
      capableSignups,
      capableActivated,
    ] of activationResults as any[]) {
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
    const totalInactiveGA = recentGA.reduce((s, w) => s + w.inactive, 0);
    const quickRatio =
      totalInactiveGA > 0
        ? Math.round(
            ((totalNewGA + totalResurrectedGA) / totalInactiveGA) * 100
          ) / 100
        : null;

    const result = applyFirestoreActivationCompat(
      {
        userGrowth,
        growthAccounting,
        establishedRetention,
        rollingGrowth,
        meaningfulUsage,
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
          rollingActive: rollingGrowth.active,
          rollingPriorActive: rollingGrowth.priorActive,
          rollingNewUsers: rollingGrowth.newUsers,
          rollingRetained: rollingGrowth.retained,
          rollingResurrected: rollingGrowth.resurrected,
          rollingInactive: rollingGrowth.inactive,
          rollingInactiveRate: rollingGrowth.inactiveRate,
          rollingNetActiveChange: rollingGrowth.netActiveChange,
        },
      },
      await activationOverlay()
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
