import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');

    if (!apiKey || !projectId) {
      return NextResponse.json({ error: 'PostHog credentials not configured' }, { status: 500 });
    }

    const searchParams = request.nextUrl.searchParams;
    const days = parseInt(searchParams.get('days') || '30', 10);
    const url = `${host}/api/projects/${projectId}/query/`;

    const body = {
      query: {
        kind: 'HogQLQuery',
        query: `
          SELECT
            event,
            uniq(COALESCE(person_id, distinct_id)) AS unique_users,
            count() AS total_events
          FROM events
          WHERE event IN ('Sign In Completed', 'Memory Share Button Clicked')
            AND timestamp >= now() - INTERVAL ${days} DAY
            AND properties.$os = 'macOS'
          GROUP BY event
        `,
      },
    };

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      console.error('PostHog k-factor API error:', response.status, text);
      return NextResponse.json({ error: `PostHog API error: ${response.status}` }, { status: 502 });
    }

    const raw = await response.json();
    const rows = Array.isArray(raw.results) ? raw.results : [];

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

    return NextResponse.json({
      days,
      available: false,
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
    });
  } catch (error) {
    console.error('Error fetching PostHog k-factor proxy:', error);
    return NextResponse.json(
      { error: 'Failed to fetch PostHog k-factor proxy data' },
      { status: 500 }
    );
  }
}
