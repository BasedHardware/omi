import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
import { getPayload, setPayload, withFreshness } from '@/lib/payload-cache';
import { POSTHOG_SERVED_MAX_ROWS, withRowLimit } from '@/lib/posthog';
import {
  ENTRY_EVENT_NAME,
  ENTRY_PROPERTY_NAME,
  ENTRY_PROPERTY_VALUE,
  FIRST_RUN_ENTRY_EVENT_NAME,
  FIRST_RUN_ENTRY_PROPERTY_NAME,
  FIRST_RUN_ENTRY_PROPERTY_VALUE,
  FIRST_RUN_EVENT_NAMES,
  ONBOARDING_EVENT_NAMES,
  computeFirstRunFunnelSteps,
  computeFunnelSteps,
} from '@/lib/onboarding-funnel';
export const dynamic = 'force-dynamic';
export const maxDuration = 3600;

function cacheKey(days: number): string {
  return `onboarding:v2:${days}`;
}

export { cacheKey as onboardingCacheKey };

class PostHogError extends Error {
  constructor(public status: number) {
    super(`PostHog API error: ${status}`);
    this.name = 'PostHogError';
  }
}

// The funnels' step lists and ordering live in @/lib/onboarding-funnel, whose
// source of truth is desktop/macos/Desktop/Sources/Onboarding/Scenario/ and
// desktop/macos/Desktop/Sources/ProactiveAssistants/FirstRun/. Renaming,
// adding, or removing a beat/step there must be mirrored in that file.

/** Builds the HogQL for one funnel: entrant gating + the actor/event/property rows it feeds to computeFunnel*. */
function funnelQuery(opts: {
  eventNames: string[];
  entryEventName: string;
  entryPropertyName: string;
  entryPropertyValue: string;
  days: number;
}): string {
  const escapedEventNames = opts.eventNames
    .map((name) => `'${name.replace(/'/g, "\\'")}'`)
    .join(', ');

  return `
    WITH entrant_actors AS (
      SELECT actor_id
      FROM (
        SELECT
          COALESCE(person_id, distinct_id) AS actor_id,
          argMin(event, timestamp) AS first_event_name,
          argMin(toString(properties.${opts.entryPropertyName}), timestamp) AS first_event_property,
          min(timestamp) AS first_event_at
        FROM events
        WHERE event IN (${escapedEventNames})
          AND properties.$os = 'macOS'
        GROUP BY actor_id
      )
      WHERE first_event_name = '${opts.entryEventName}'
        AND first_event_property = '${opts.entryPropertyValue}'
        AND first_event_at >= now() - INTERVAL ${opts.days} DAY
    )
    SELECT
      COALESCE(person_id, distinct_id) AS actor_id,
      event,
      toString(properties.${opts.entryPropertyName}) AS property_value
    FROM events
    WHERE event IN (${escapedEventNames})
      AND properties.$os = 'macOS'
      AND COALESCE(person_id, distinct_id) IN (SELECT actor_id FROM entrant_actors)
    GROUP BY actor_id, event, property_value
    LIMIT ${POSTHOG_SERVED_MAX_ROWS}
  `;
}

async function runFunnelQuery(
  host: string,
  projectId: string,
  apiKey: string,
  hogql: string,
): Promise<unknown[][]> {
  const url = `${host}/api/projects/${projectId}/query/`;

  // Own fetch (bypasses posthogFetch); guard directly (#10190).
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      query: { kind: 'HogQLQuery', query: withRowLimit(hogql) },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    console.error('PostHog onboarding API error:', response.status, text);
    throw new PostHogError(response.status);
  }

  const raw = await response.json();
  return Array.isArray(raw.results) ? raw.results : [];
}

export async function computeOnboarding(days: number) {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || 'https://us.posthog.com').replace(/\/$/, '');

    if (!apiKey || !projectId) {
      throw new Error('PostHog credentials not configured');
    }

    const [onboardingRows, firstRunRows] = await Promise.all([
      runFunnelQuery(
        host,
        projectId,
        apiKey,
        funnelQuery({
          eventNames: ONBOARDING_EVENT_NAMES,
          entryEventName: ENTRY_EVENT_NAME,
          entryPropertyName: ENTRY_PROPERTY_NAME,
          entryPropertyValue: ENTRY_PROPERTY_VALUE,
          days,
        }),
      ),
      runFunnelQuery(
        host,
        projectId,
        apiKey,
        funnelQuery({
          eventNames: FIRST_RUN_EVENT_NAMES,
          entryEventName: FIRST_RUN_ENTRY_EVENT_NAME,
          entryPropertyName: FIRST_RUN_ENTRY_PROPERTY_NAME,
          entryPropertyValue: FIRST_RUN_ENTRY_PROPERTY_VALUE,
          days,
        }),
      ),
    ]);

    // Each grouped query is capped at the served ceiling; a result sitting at
    // the cap means actor x event rows were dropped and that funnel undercounts.
    const truncated = onboardingRows.length >= POSTHOG_SERVED_MAX_ROWS;
    const firstRunTruncated = firstRunRows.length >= POSTHOG_SERVED_MAX_ROWS;

    const { totalUsers, steps } = computeFunnelSteps(onboardingRows);
    const firstRunFunnel = computeFirstRunFunnelSteps(firstRunRows);

    return {
      days,
      totalUsers,
      methodology:
        'First-ever entrants into the current macOS onboarding flow, using users whose earliest recorded onboarding event is the "hello" beat inside the selected window.',
      steps,
      truncated,
      firstRun: {
        totalUsers: firstRunFunnel.totalUsers,
        methodology:
          'First-ever entrants into the post-onboarding first-run walkthrough, using users whose earliest recorded first-run event is the "openWork" step inside the selected window.',
        steps: firstRunFunnel.steps,
        truncated: firstRunTruncated,
      },
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
