import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

let cache: { data: any; days: number; timestamp: number } | null = null;
const CACHE_TTL = 30 * 60 * 1000;

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
    const days = Math.min(parseInt(searchParams.get("days") || "30", 10), 90);

    if (cache && cache.days === days && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json(cache.data);
    }

    // Query 1: Daily total queries and unique users
    const totalQuery = `
      SELECT
        toDate(timestamp) as day,
        count() as total_queries,
        count(DISTINCT distinct_id) as unique_users
      FROM events
      WHERE event = 'floating_bar_query_sent'
        AND properties.$os_name = 'macOS'
        AND timestamp >= now() - interval ${days} day
      GROUP BY day
      ORDER BY day
    `;

    // Query 2: Daily voice queries (PTT ended with transcript)
    const voiceQuery = `
      SELECT
        toDate(timestamp) as day,
        count() as voice_queries
      FROM events
      WHERE event = 'floating_bar_ptt_ended'
        AND properties.$os_name = 'macOS'
        AND properties.had_transcript = true
        AND timestamp >= now() - interval ${days} day
      GROUP BY day
      ORDER BY day
    `;

    // Query 3: Daily sessions (unique floating bar opens, not follow-ups)
    const sessionsQuery = `
      SELECT
        toDate(timestamp) as day,
        count() as sessions,
        count(DISTINCT distinct_id) as session_users
      FROM events
      WHERE event = 'floating_bar_ask_omi_opened'
        AND properties.$os_name = 'macOS'
        AND timestamp >= now() - interval ${days} day
      GROUP BY day
      ORDER BY day
    `;

    const [totalRes, voiceRes, sessionsRes] = await Promise.all([
      fetch(`${host}/api/projects/${projectId}/query/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: { kind: "HogQLQuery", query: totalQuery } }),
      }),
      fetch(`${host}/api/projects/${projectId}/query/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: { kind: "HogQLQuery", query: voiceQuery } }),
      }),
      fetch(`${host}/api/projects/${projectId}/query/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: { kind: "HogQLQuery", query: sessionsQuery } }),
      }),
    ]);

    if (!totalRes.ok || !voiceRes.ok || !sessionsRes.ok) {
      const failedRes = !totalRes.ok ? totalRes : !voiceRes.ok ? voiceRes : sessionsRes;
      const text = await failedRes.text();
      console.error("PostHog query error:", text);
      return NextResponse.json(
        { error: "PostHog API error" },
        { status: 502 }
      );
    }

    const totalResult = await totalRes.json();
    const voiceResult = await voiceRes.json();
    const sessionsResult = await sessionsRes.json();

    const totalRows: [string, number, number][] = totalResult?.results ?? [];
    const voiceRows: [string, number][] = voiceResult?.results ?? [];
    const sessionsRows: [string, number, number][] = sessionsResult?.results ?? [];

    // Build lookups by date
    const voiceByDate: Record<string, number> = {};
    for (const [date, count] of voiceRows) {
      voiceByDate[date.slice(0, 10)] = count;
    }
    const sessionsByDate: Record<string, { sessions: number; users: number }> = {};
    for (const [date, sessions, users] of sessionsRows) {
      sessionsByDate[date.slice(0, 10)] = { sessions, users };
    }

    // Combine into daily data
    const daily = totalRows.map(([date, totalQueries, uniqueUsers]) => {
      const d = date.slice(0, 10);
      const voice = voiceByDate[d] || 0;
      const text = totalQueries - voice;
      const avgPerUser = uniqueUsers > 0 ? Math.round((totalQueries / uniqueUsers) * 10) / 10 : 0;
      const sess = sessionsByDate[d] || { sessions: 0, users: 0 };
      const avgSessionsPerUser = sess.users > 0 ? Math.round((sess.sessions / sess.users) * 10) / 10 : 0;
      return {
        date: d,
        total_queries: totalQueries,
        text_queries: text,
        voice_queries: voice,
        unique_users: uniqueUsers,
        avg_per_user: avgPerUser,
        sessions: sess.sessions,
        avg_sessions_per_user: avgSessionsPerUser,
      };
    });

    // Summary stats
    const totalAllQueries = daily.reduce((s, d) => s + d.total_queries, 0);
    const totalAllVoice = daily.reduce((s, d) => s + d.voice_queries, 0);
    const totalAllText = daily.reduce((s, d) => s + d.text_queries, 0);
    const totalAllUsers = daily.reduce((s, d) => s + d.unique_users, 0);
    const totalAllSessions = daily.reduce((s, d) => s + d.sessions, 0);
    const activeDays = daily.filter((d) => d.total_queries > 0).length;

    const result = {
      data: daily,
      days,
      summary: {
        totalQueries: totalAllQueries,
        totalVoice: totalAllVoice,
        totalText: totalAllText,
        totalSessions: totalAllSessions,
        overallAvgPerUserPerDay: totalAllUsers > 0 ? Math.round((totalAllQueries / totalAllUsers) * 10) / 10 : 0,
        overallAvgSessionsPerUserPerDay: totalAllUsers > 0 ? Math.round((totalAllSessions / totalAllUsers) * 10) / 10 : 0,
        activeDays,
      },
    };

    cache = { data: result, days, timestamp: Date.now() };

    return NextResponse.json(result);
  } catch (error) {
    console.error("Floating bar usage error:", error);
    return NextResponse.json(
      { error: "Failed to fetch floating bar usage" },
      { status: 500 }
    );
  }
}
