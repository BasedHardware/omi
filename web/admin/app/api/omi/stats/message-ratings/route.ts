import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";

export const dynamic = "force-dynamic";

// macOS thumbs up/down on assistant responses (`message_rated`, always
// filtered to $os_name = 'macOS'). The positive share is ONE number per
// bucket: thumbs_up / (thumbs_up + thumbs_down) * 100.
//
// `source` splits text (main-window chat) from voice (floating-bar
// responses); events recorded before the dimension shipped count only toward
// the combined "all" series.
type RatioPoint = {
  date: string;
  all: number | null;
  text: number | null;
  voice: number | null;
  upAll: number;
  downAll: number;
};

function ratio(up: number, down: number): number | null {
  const total = up + down;
  return total > 0 ? Math.round((1000 * up) / total) / 10 : null;
}

function mondayKey(ymd: string): string {
  const d = new Date(ymd + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
  return d.toISOString().slice(0, 10);
}

export async function computeMessageRatings(days: number) {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );
  if (!apiKey || !projectId) {
    throw new Error("PostHog credentials not configured");
  }

  const rows = (await posthogResults(
    host,
    projectId,
    apiKey,
    `
      SELECT
        toDate(toTimeZone(timestamp, 'America/New_York')) AS day,
        coalesce(toString(properties.source), 'legacy') AS src,
        countIf(properties.rating = 'thumbs_up') AS up,
        countIf(properties.rating = 'thumbs_down') AS down
      FROM events
      WHERE event = 'message_rated'
        AND properties.$os_name = 'macOS'
        AND timestamp >= now() - INTERVAL ${days} DAY
      GROUP BY day, src
      ORDER BY day
    `,
  )) as any[];

  type Bucket = { up: Record<string, number>; down: Record<string, number> };
  const byDay = new Map<string, Bucket>();
  for (const [day, src, up, down] of rows ?? []) {
    const key = String(day).slice(0, 10);
    const bucket = byDay.get(key) ?? { up: {}, down: {} };
    bucket.up[src] = (bucket.up[src] ?? 0) + Number(up);
    bucket.down[src] = (bucket.down[src] ?? 0) + Number(down);
    byDay.set(key, bucket);
  }

  const sum = (rec: Record<string, number>, keys?: string[]) =>
    Object.entries(rec)
      .filter(([k]) => !keys || keys.includes(k))
      .reduce((a, [, v]) => a + v, 0);

  const toPoint = (date: string, b: Bucket): RatioPoint => ({
    date,
    all: ratio(sum(b.up), sum(b.down)),
    text: ratio(sum(b.up, ["text"]), sum(b.down, ["text"])),
    voice: ratio(sum(b.up, ["voice"]), sum(b.down, ["voice"])),
    upAll: sum(b.up),
    downAll: sum(b.down),
  });

  const daily = Array.from(byDay.entries())
    .map(([date, bucket]) => toPoint(date, bucket))
    .sort((a, b) => (a.date < b.date ? -1 : 1));

  const byWeek = new Map<string, Bucket>();
  byDay.forEach((bucket, day) => {
    const week = mondayKey(day);
    const acc = byWeek.get(week) ?? { up: {}, down: {} };
    for (const [k, v] of Object.entries(bucket.up))
      acc.up[k] = (acc.up[k] ?? 0) + (v as number);
    for (const [k, v] of Object.entries(bucket.down))
      acc.down[k] = (acc.down[k] ?? 0) + (v as number);
    byWeek.set(week, acc);
  });
  const weekly = Array.from(byWeek.entries())
    .map(([week, bucket]) => ({ ...toPoint(week, bucket), week }))
    .sort((a, b) => (a.week < b.week ? -1 : 1));

  // Legacy shape kept for the existing "Message ratings" volumes panel and
  // /dashboard/classic.
  const data = daily.map((p) => ({
    date: p.date,
    thumbs_up: p.upAll,
    thumbs_down: p.downAll,
    ratio: p.all,
  }));

  return { days, data, daily, weekly };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const days = Math.min(
      parseInt(request.nextUrl.searchParams.get("days") || "30", 10) || 30,
      180,
    );
    return NextResponse.json(await computeMessageRatings(days));
  } catch (error: any) {
    console.error("Message ratings error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch message ratings" },
      { status: 502 },
    );
  }
}
