import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
export const dynamic = "force-dynamic";

// In-app star ratings from the desktop prompt ("Desktop Rating Submitted",
// fired after a user's 3rd question). Omi Desktop is not on the App Store, so
// this is the only overall-rating signal that exists for macOS.
export async function computeDesktopRatings(days: number) {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );

  if (!apiKey || !projectId) {
    return { days, available: false as const, daily: [], summary: null };
  }

  const rows = (await posthogResults(
    host,
    projectId,
    apiKey,
    `
      SELECT
        toDate(toTimeZone(timestamp, 'America/New_York')) AS day,
        round(avg(toFloatOrZero(toString(properties.rating))), 2) AS avg_rating,
        count() AS ratings
      FROM events
      WHERE event = 'Desktop Rating Submitted'
        AND timestamp >= now() - INTERVAL ${days} DAY
      GROUP BY day
      ORDER BY day
    `,
  )) as any[];

  const daily = (rows ?? []).map((row) => ({
    date: String(row[0]).slice(0, 10),
    avgRating: Number(row[1]) || 0,
    count: Number(row[2]) || 0,
  }));
  const totalCount = daily.reduce((acc, d) => acc + d.count, 0);
  const avgRating =
    totalCount > 0
      ? daily.reduce((acc, d) => acc + d.avgRating * d.count, 0) / totalCount
      : null;

  return {
    days,
    available: true as const,
    daily,
    summary: {
      avgRating: avgRating === null ? null : Math.round(avgRating * 100) / 100,
      count: totalCount,
    },
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const days = parseInt(request.nextUrl.searchParams.get("days") || "60", 10);
  try {
    return NextResponse.json(await computeDesktopRatings(days));
  } catch (error) {
    console.error("Desktop ratings stats error:", error);
    return NextResponse.json({ days, available: false, daily: [], summary: null });
  }
}
