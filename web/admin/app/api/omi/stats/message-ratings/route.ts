import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

// Module-level cache (30 min TTL)
let cache: { data: { date: string; thumbs_up: number; thumbs_down: number; ratio: number }[]; days: number; timestamp: number } | null = null;
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
      return NextResponse.json({ data: cache.data, days });
    }

    // Query PostHog for message_rated events from macOS desktop app
    const hogql = `
      SELECT
        toDate(timestamp) as day,
        countIf(properties.rating = 'thumbs_up') as thumbs_up,
        countIf(properties.rating = 'thumbs_down') as thumbs_down
      FROM events
      WHERE event = 'message_rated'
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

    const result = await response.json();
    const rows: [string, number, number][] = result?.results ?? [];

    const data = rows.map(([date, thumbs_up, thumbs_down]) => {
      const total = thumbs_up + thumbs_down;
      return {
        date: date.slice(0, 10),
        thumbs_up,
        thumbs_down,
        ratio: total > 0 ? Math.round((thumbs_up / total) * 100) : 0,
      };
    });

    cache = { data, days, timestamp: Date.now() };

    return NextResponse.json({ data, days });
  } catch (error) {
    console.error("Message ratings error:", error);
    return NextResponse.json(
      { error: "Failed to fetch message ratings" },
      { status: 500 }
    );
  }
}
