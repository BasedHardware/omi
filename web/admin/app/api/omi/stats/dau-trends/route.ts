import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

// Module-level cache (30 min TTL)
let cache: { data: { date: string; dau: number }[]; days: number; timestamp: number } | null = null;
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
    const days = Math.min(parseInt(searchParams.get("days") || "60", 10), 90);

    if (cache && cache.days === days && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json({ data: cache.data, days });
    }

    // Use PostHog HogQL for daily unique macOS users with "App Became Active"
    const hogql = `
      SELECT
        toDate(timestamp) as day,
        count(DISTINCT distinct_id) as users
      FROM events
      WHERE event = 'App Became Active'
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
      const text = await response.text();
      console.error("PostHog query error:", response.status, text);
      return NextResponse.json(
        { error: `PostHog API error: ${response.status}` },
        { status: 502 }
      );
    }

    const raw = await response.json();
    const results: [string, number][] = raw.results || [];

    // Build map from results
    const dateMap: Record<string, number> = {};
    for (const [date, count] of results) {
      dateMap[date] = count;
    }

    // Generate complete date series
    const toDate = new Date();
    const fromDate = new Date();
    fromDate.setDate(fromDate.getDate() - days);

    const formatDate = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

    const data: { date: string; dau: number }[] = [];
    const current = new Date(fromDate);
    while (current <= toDate) {
      const dateStr = formatDate(current);
      data.push({ date: dateStr, dau: dateMap[dateStr] ?? 0 });
      current.setDate(current.getDate() + 1);
    }

    cache = { data, days, timestamp: Date.now() };
    return NextResponse.json({ data, days });
  } catch (error: any) {
    console.error("DAU trends error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch DAU trends" },
      { status: 500 }
    );
  }
}
