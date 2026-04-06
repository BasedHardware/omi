import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';

type RetentionPoint = { day: number; retention: number };
type CohortRow = { date: string; users: number; data: RetentionPoint[] };

async function posthogQuery(host: string, projectId: string, apiKey: string, query: string) {
  const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({
      query: {
        kind: 'HogQLQuery',
        query,
      },
    }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`PostHog API error: ${response.status} ${text}`);
  }

  const raw = await response.json();
  return Array.isArray(raw.results) ? raw.results : [];
}

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
    const days = parseInt(searchParams.get('days') || '14', 10);
    const intervals = parseInt(searchParams.get('intervals') || '10', 10);
    const platform = searchParams.get('platform') || '';

    const eventFilter = platform === 'macos' ? `AND properties.$os = 'macOS'` : '';
    const url = `${host}/api/projects/${projectId}/query/`;

    const cohortRows = await posthogQuery(
      host,
      projectId,
      apiKey,
      `
        SELECT
          COALESCE(person_id, distinct_id) AS actor_id,
          min(toDate(timestamp)) AS cohort_date
        FROM events
        WHERE event = 'App Became Active'
          ${eventFilter}
        GROUP BY actor_id
        HAVING cohort_date >= today() - INTERVAL ${days} DAY
          AND cohort_date <= today()
        ORDER BY cohort_date ASC, actor_id ASC
        LIMIT 100000
      `
    );

    const actorToCohortDate = new Map<string, string>();
    for (const row of cohortRows) {
      const actorId = String(row[0] ?? '');
      const cohortDate = String(row[1] ?? '').slice(0, 10);
      if (!actorId || !cohortDate) continue;
      actorToCohortDate.set(actorId, cohortDate);
    }

    if (actorToCohortDate.size === 0) {
      return NextResponse.json({ data: [], cohorts: [], totalCohorts: 0, totalUsers: 0 });
    }

    const actorIds = Array.from(actorToCohortDate.keys())
      .map((id) => `'${id.replace(/'/g, "\\'")}'`)
      .join(', ');

    const eventRows = await posthogQuery(
      host,
      projectId,
      apiKey,
      `
        SELECT
          COALESCE(person_id, distinct_id) AS actor_id,
          toDate(timestamp) AS event_date
        FROM events
        WHERE event = 'App Became Active'
          ${eventFilter}
          AND COALESCE(person_id, distinct_id) IN (${actorIds})
          AND timestamp >= today() - INTERVAL ${days} DAY
        GROUP BY actor_id, event_date
        ORDER BY actor_id ASC, event_date ASC
        LIMIT 100000
      `
    );

    const cohortUsers = new Map<string, Map<string, Set<number>>>();
    for (const [actorId, cohortDate] of Array.from(actorToCohortDate.entries())) {
      const users = cohortUsers.get(cohortDate) ?? new Map<string, Set<number>>();
      users.set(actorId, new Set<number>([0]));
      cohortUsers.set(cohortDate, users);
    }

    for (const row of eventRows) {
      const actorId = String(row[0] ?? '');
      const eventDate = String(row[1] ?? '').slice(0, 10);
      const cohortDate = actorToCohortDate.get(actorId);
      if (!actorId || !eventDate || !cohortDate) continue;

      const cohortStart = new Date(`${cohortDate}T00:00:00Z`);
      const activeDate = new Date(`${eventDate}T00:00:00Z`);
      const offset = Math.round((activeDate.getTime() - cohortStart.getTime()) / 86_400_000);
      if (offset < 0 || offset > intervals) continue;

      const users = cohortUsers.get(cohortDate);
      const offsets = users?.get(actorId);
      if (!users || !offsets) continue;
      offsets.add(offset);
    }

    const today = new Date();
    today.setUTCHours(0, 0, 0, 0);

    const cohorts: CohortRow[] = Array.from(cohortUsers.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([cohortDate, users]) => {
        const cohortStart = new Date(`${cohortDate}T00:00:00Z`);
        const maxAvailableDay = Math.min(
          intervals,
          Math.max(0, Math.floor((today.getTime() - cohortStart.getTime()) / 86_400_000))
        );

        const data: RetentionPoint[] = [];
        const actorOffsets = Array.from(users.values());

        for (let day = 0; day <= maxAvailableDay; day++) {
          let retainedUsers = 0;
          for (const offsets of actorOffsets) {
            if (day === 0 || Array.from(offsets).some((value) => value >= day)) {
              retainedUsers += 1;
            }
          }
          data.push({
            day,
            retention: actorOffsets.length > 0 ? Math.round((retainedUsers / actorOffsets.length) * 10000) / 100 : 0,
          });
        }

        return {
          date: cohortDate,
          users: actorOffsets.length,
          data,
        };
      });

    const maxDays = cohorts.reduce((max, cohort) => Math.max(max, cohort.data.length), 0);
    const mean: RetentionPoint[] = [];

    for (let day = 0; day < maxDays; day++) {
      const values = cohorts
        .map((cohort) => cohort.data.find((point) => point.day === day)?.retention)
        .filter((value): value is number => value != null);

      if (values.length === 0) continue;

      const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
      mean.push({
        day,
        retention: Math.round(avg * 100) / 100,
      });
    }

    const totalUsers = cohorts.reduce((sum, cohort) => sum + cohort.users, 0);

    return NextResponse.json({
      data: mean,
      cohorts,
      totalCohorts: cohorts.length,
      totalUsers,
    });
  } catch (error) {
    console.error('Error fetching PostHog retention:', error);
    return NextResponse.json(
      { error: 'Failed to fetch PostHog retention data' },
      { status: 500 }
    );
  }
}
