import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { posthogResults } from '@/lib/posthog';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

// Run the k-factor proxy HogQL query through posthogResults (Firestore
// query-cache + 429 backoff + stale fallback) and shape the panel payload.
// Exported so the precompute cron can warm the underlying query cache.
export async function computeKFactor(days: number) {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');

  if (!apiKey || !projectId) {
    return {
      days,
      available: false as const,
      kFactor: null,
      reason: 'PostHog credentials not configured.',
    };
  }

  const query = `
          SELECT
            event,
            uniq(COALESCE(person_id, distinct_id)) AS unique_users,
            count() AS total_events
          FROM events
          WHERE event IN ('Sign In Completed', 'Memory Share Button Clicked')
            AND timestamp >= now() - INTERVAL ${days} DAY
            AND properties.$os = 'macOS'
          GROUP BY event
        `;

  const rows = (await posthogResults(host, projectId, apiKey, query)) as any[];

  let newUsers = 0;
  let sharers = 0;
  let shareEvents = 0;

  for (const row of rows) {
    const eventName = row[0];
    const uniqueUsers = Number(row[1] ?? 0);
    const totalEvents = Number(row[2] ?? 0);

    if (eventName === 'Sign In Completed') {
      newUsers = uniqueUsers;
    }
    if (eventName === 'Memory Share Button Clicked') {
      sharers = uniqueUsers;
      shareEvents = totalEvents;
    }
  }

  const shareRatePct = newUsers > 0 ? (sharers / newUsers) * 100 : 0;
  const sharesPerSharer = sharers > 0 ? shareEvents / sharers : 0;
  const sharesPerNewUser = newUsers > 0 ? shareEvents / newUsers : 0;

  return {
    days,
    available: false as const,
    kFactor: null,
    reason:
      'Referral attribution is not instrumented on macOS yet. Current desktop analytics only expose sharing activity, not invite acceptance or referred sign-ups.',
    proxy: {
      newUsers,
      sharers,
      shareEvents,
      shareRatePct: Math.round(shareRatePct * 10) / 10,
      sharesPerSharer: Math.round(sharesPerSharer * 100) / 100,
      sharesPerNewUser: Math.round(sharesPerNewUser * 100) / 100,
    },
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const searchParams = request.nextUrl.searchParams;
  const days = parseInt(searchParams.get('days') || '30', 10);

  try {
    const payload = await computeKFactor(days);
    return NextResponse.json(payload);
  } catch (error) {
    // PostHog still failing (e.g. 429 with no cached fallback) — degrade
    // gracefully so the panel never hard-errors with a 502/500.
    console.error('Error fetching PostHog k-factor proxy:', error);
    return NextResponse.json({
      days,
      available: false as const,
      kFactor: null,
      reason: 'PostHog data is temporarily unavailable (rate-limited). Try again shortly.',
    });
  }
}
