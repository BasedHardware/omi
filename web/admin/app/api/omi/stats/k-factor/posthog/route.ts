import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// K-factor is measured as the daily sum of three word-of-mouth signals, each a
// real, server-observed PostHog event:
//   1) friend  — "Onboarding How Did You Hear" with source = 'Friend'
//   2) referral — "Referral Program Opened" (referral system usage)
//   3) share    — "Conversation Shared" (sharing conversation summaries)
// Older builds queried "Referral Link Issued/Claimed", which are never emitted,
// so the panel always read null. These event names are verified against live data.
// Exported so the precompute cron can warm the underlying query cache.
export interface KFactorDaily {
  date: string;
  friends: number;
  referrals: number;
  shares: number;
  total: number;
}

export async function computeKFactor(days: number) {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );

  if (!apiKey || !projectId) {
    return {
      days,
      available: false as const,
      kFactor: null,
      reason: "PostHog credentials not configured.",
    };
  }

  const dailySeries = (event: string, extraFilter = "") => `
          SELECT toDate(timestamp) AS day, count() AS n
          FROM events
          WHERE event = '${event}'
            AND timestamp >= now() - INTERVAL ${days} DAY
            ${extraFilter}
          GROUP BY day
          ORDER BY day
        `;

  const [friendRows, referralRows, shareRows] = await Promise.all([
    posthogResults(
      host,
      projectId,
      apiKey,
      dailySeries("Onboarding How Did You Hear", "AND properties.source = 'Friend'"),
    ) as Promise<any[]>,
    posthogResults(
      host,
      projectId,
      apiKey,
      dailySeries("Referral Program Opened"),
    ) as Promise<any[]>,
    posthogResults(
      host,
      projectId,
      apiKey,
      dailySeries("Conversation Shared"),
    ) as Promise<any[]>,
  ]);

  const toMap = (rows: any[]) => {
    const m = new Map<string, number>();
    for (const r of rows ?? []) {
      const day = String(r?.[0] ?? "").slice(0, 10);
      if (day) m.set(day, Number(r?.[1] ?? 0));
    }
    return m;
  };
  const fMap = toMap(friendRows);
  const rMap = toMap(referralRows);
  const sMap = toMap(shareRows);

  // Continuous day axis so the daily graph has no gaps.
  const daily: KFactorDaily[] = [];
  const today = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setUTCDate(d.getUTCDate() - i);
    const key = d.toISOString().slice(0, 10);
    const friends = fMap.get(key) ?? 0;
    const referrals = rMap.get(key) ?? 0;
    const shares = sMap.get(key) ?? 0;
    daily.push({ date: key, friends, referrals, shares, total: friends + referrals + shares });
  }

  const windowSum = (sel: (p: KFactorDaily) => number, n = days) =>
    daily.slice(-n).reduce((s, p) => s + sel(p), 0);

  const totals = {
    friends: windowSum((p) => p.friends),
    referrals: windowSum((p) => p.referrals),
    shares: windowSum((p) => p.shares),
    total: windowSum((p) => p.total),
  };
  const weekly = {
    friends: windowSum((p) => p.friends, 7),
    referrals: windowSum((p) => p.referrals, 7),
    shares: windowSum((p) => p.shares, 7),
    total: windowSum((p) => p.total, 7),
  };

  return {
    days,
    available: true as const,
    // Headline k-factor = total viral signals over the window (sum of all three).
    kFactor: totals.total,
    daily,
    totals,
    weekly,
    reason:
      "K-factor = friend sign-ups + referral opens + conversation shares (server-side PostHog).",
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const searchParams = request.nextUrl.searchParams;
  const days = parseInt(searchParams.get("days") || "30", 10);

  try {
    const payload = await computeKFactor(days);
    return NextResponse.json(payload);
  } catch (error) {
    // PostHog still failing (e.g. 429 with no cached fallback) — degrade
    // gracefully so the panel never hard-errors with a 502/500.
    console.error("Error fetching PostHog k-factor proxy:", error);
    return NextResponse.json({
      days,
      available: false as const,
      kFactor: null,
      reason:
        "PostHog data is temporarily unavailable (rate-limited). Try again shortly.",
    });
  }
}
