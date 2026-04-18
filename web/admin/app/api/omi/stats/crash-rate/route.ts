import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

let cache: { data: CrashRatePoint[]; days: number; timestamp: number } | null =
  null;
const CACHE_TTL = 30 * 60 * 1000;

interface CrashRatePoint {
  date: string;
  crashes: number;
  users: number;
  crashFreeRate: number;
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
    const days = Math.min(parseInt(searchParams.get("days") || "30", 10), 90);

    if (cache && cache.days === days && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json({ data: cache.data, days });
    }

    // Query crashes and active users per day in a single HogQL query
    const hogql = `
      SELECT
        toDate(timestamp) as day,
        countIf(event = 'App Crash Detected') as crashes,
        countIf(DISTINCT distinct_id, event = 'App Became Active') as users
      FROM events
      WHERE (event = 'App Crash Detected' OR event = 'App Became Active')
        AND properties.$os_name = 'macOS'
        AND timestamp >= now() - interval ${days} day
      GROUP BY day
      ORDER BY day
    `;

    const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        query: { kind: "HogQLQuery", query: hogql },
      }),
    });

    if (!response.ok) {
      // HogQL countIf with DISTINCT might not be supported — fall back to two queries
      const [crashRes, dauRes] = await Promise.allSettled([
        fetch(`${host}/api/projects/${projectId}/query/`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query: {
              kind: "HogQLQuery",
              query: `
                SELECT toDate(timestamp) as day, count() as crashes
                FROM events
                WHERE event = 'App Crash Detected'
                  AND properties.$os_name = 'macOS'
                  AND timestamp >= now() - interval ${days} day
                GROUP BY day ORDER BY day
              `,
            },
          }),
        }),
        fetch(`${host}/api/projects/${projectId}/query/`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            query: {
              kind: "HogQLQuery",
              query: `
                SELECT toDate(timestamp) as day, count(DISTINCT distinct_id) as users
                FROM events
                WHERE event = 'App Became Active'
                  AND properties.$os_name = 'macOS'
                  AND timestamp >= now() - interval ${days} day
                GROUP BY day ORDER BY day
              `,
            },
          }),
        }),
      ]);

      const crashMap: Record<string, number> = {};
      const dauMap: Record<string, number> = {};

      if (crashRes.status === "fulfilled" && crashRes.value.ok) {
        const raw = await crashRes.value.json();
        for (const [date, count] of raw.results || []) {
          crashMap[date] = count;
        }
      }

      if (dauRes.status === "fulfilled" && dauRes.value.ok) {
        const raw = await dauRes.value.json();
        for (const [date, count] of raw.results || []) {
          dauMap[date] = count;
        }
      }

      const data = buildDateSeries(days, crashMap, dauMap);
      cache = { data, days, timestamp: Date.now() };
      return NextResponse.json({ data, days });
    }

    // Single-query path succeeded
    const raw = await response.json();
    const results: [string, number, number][] = raw.results || [];

    const crashMap: Record<string, number> = {};
    const dauMap: Record<string, number> = {};
    for (const [date, crashes, users] of results) {
      crashMap[date] = crashes;
      dauMap[date] = users;
    }

    const data = buildDateSeries(days, crashMap, dauMap);
    cache = { data, days, timestamp: Date.now() };
    return NextResponse.json({ data, days });
  } catch (error: any) {
    console.error("Crash rate error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch crash rate" },
      { status: 500 }
    );
  }
}

function buildDateSeries(
  days: number,
  crashMap: Record<string, number>,
  dauMap: Record<string, number>
): CrashRatePoint[] {
  const toDate = new Date();
  const fromDate = new Date();
  fromDate.setDate(fromDate.getDate() - days);

  const formatDate = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

  const data: CrashRatePoint[] = [];
  const current = new Date(fromDate);
  while (current <= toDate) {
    const dateStr = formatDate(current);
    const crashes = crashMap[dateStr] ?? 0;
    const users = dauMap[dateStr] ?? 0;
    const crashFreeRate = users > 0 ? Math.round((1 - crashes / users) * 1000) / 10 : 100;
    data.push({ date: dateStr, crashes, users, crashFreeRate });
    current.setDate(current.getDate() + 1);
  }
  return data;
}
