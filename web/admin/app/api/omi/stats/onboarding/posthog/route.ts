import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getPayload, setPayload, withFreshness } from '@/lib/payload-cache';
import { POSTHOG_SERVED_MAX_ROWS, withRowLimit } from '@/lib/posthog';
import {
  ALL_EVENT_NAMES,
  ENTRY_EVENT_NAME,
  computeFunnelSteps,
} from '@/lib/onboarding-funnel';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(days: number): string {
  return `onboarding:v1:${days}`;
}

export { cacheKey as onboardingCacheKey };

class PostHogError extends Error {
  constructor(public status: number) {
    super(`PostHog API error: ${status}`);
    this.name = 'PostHogError';
  }
}

// The funnel's step list and ordering live in @/lib/onboarding-funnel, whose
// source of truth is desktop/macos/Desktop/Sources/Onboarding/OnboardingView.swift.
// Renaming, adding, or removing a step there must be mirrored in that file.

export async function computeOnboarding(days: number) {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');

    if (!apiKey || !projectId) {
      throw new Error('PostHog credentials not configured');
    }

    const escapedEventNames = ALL_EVENT_NAMES.map(
      (name) => `'${name.replace(/'/g, "\\'")}'`
    ).join(', ');
    const url = `${host}/api/projects/${projectId}/query/`;

    const body = {
      query: {
        kind: 'HogQLQuery',
        // Own fetch (bypasses posthogFetch); guard directly (#10190).
        query: withRowLimit(`
          WITH entrant_actors AS (
            SELECT actor_id
            FROM (
              SELECT
                COALESCE(person_id, distinct_id) AS actor_id,
                argMin(event, timestamp) AS first_event_name,
                min(timestamp) AS first_event_at
              FROM events
              WHERE event IN (${escapedEventNames})
                AND properties.$os = 'macOS'
              GROUP BY actor_id
            )
            WHERE first_event_name = '${ENTRY_EVENT_NAME}'
              AND first_event_at >= now() - INTERVAL ${days} DAY
          )
          SELECT
            COALESCE(person_id, distinct_id) AS actor_id,
            event
          FROM events
          WHERE event IN (${escapedEventNames})
            AND properties.$os = 'macOS'
            AND COALESCE(person_id, distinct_id) IN (SELECT actor_id FROM entrant_actors)
          GROUP BY actor_id, event
          LIMIT ${POSTHOG_SERVED_MAX_ROWS}
        `),
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
      console.error('PostHog onboarding API error:', response.status, text);
      throw new PostHogError(response.status);
    }

    const raw = await response.json();
    const rows = Array.isArray(raw.results) ? raw.results : [];

    // The grouped query is capped at the served ceiling; a result sitting at the
    // cap means actor x event rows were dropped and the funnel undercounts.
    const truncated = rows.length >= POSTHOG_SERVED_MAX_ROWS;
    const { totalUsers, steps } = computeFunnelSteps(rows);

    return {
      days,
      totalUsers,
      methodology:
        'First-ever entrants into the current macOS onboarding flow, using users whose earliest recorded onboarding event is Name inside the selected window.',
      steps,
      truncated,
    };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const searchParams = request.nextUrl.searchParams;
  const days = parseInt(searchParams.get('days') || '30', 10);
  const key = cacheKey(days);

  try {
    const cached = await getPayload<Awaited<ReturnType<typeof computeOnboarding>>>(key);
    if (cached) {
      return NextResponse.json(withFreshness(cached.data, cached.freshAt));
    }

    const payload = await computeOnboarding(days);
    await setPayload(key, payload);
    return NextResponse.json(withFreshness(payload, Date.now()));
  } catch (error) {
    if (error instanceof PostHogError) {
      return NextResponse.json({ error: `PostHog API error: ${error.status}` }, { status: 502 });
    }
    if (error instanceof Error && error.message === 'PostHog credentials not configured') {
      return NextResponse.json({ error: 'PostHog credentials not configured' }, { status: 500 });
    }
    console.error('Error fetching PostHog onboarding funnel:', error);
    return NextResponse.json(
      { error: 'Failed to fetch PostHog onboarding funnel data' },
      { status: 500 }
    );
  }
}
