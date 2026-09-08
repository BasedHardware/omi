import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
export const dynamic = "force-dynamic";

export type RetentionPoint = { day: number; retention: number };
export type CohortRow = { date: string; users: number; data: RetentionPoint[] };

/** User-weighted mean of per-cohort retention %. A 20-person day cannot
 *  cancel a 900-person always-on day. Cohorts that have not yet reached
 *  `day` (no point) are omitted, same as the old unweighted skip. */
export function weightedRetentionMean(cohorts: CohortRow[]): RetentionPoint[] {
  const maxDays =
    cohorts.reduce((max, cohort) => {
      const local = cohort.data.reduce((m, p) => Math.max(m, p.day), -1);
      return Math.max(max, local);
    }, -1) + 1;
  const mean: RetentionPoint[] = [];
  for (let day = 0; day < maxDays; day++) {
    let retained = 0;
    let total = 0;
    for (const cohort of cohorts) {
      const point = cohort.data.find((p) => p.day === day);
      if (point == null || cohort.users <= 0) continue;
      total += cohort.users;
      retained += (point.retention / 100) * cohort.users;
    }
    if (total === 0) continue;
    mean.push({
      day,
      retention: Math.round((retained / total) * 10000) / 100,
    });
  }
  return mean;
}

async function posthogQuery(
  host: string,
  projectId: string,
  apiKey: string,
  query: string
): Promise<any[]> {
  return (await posthogResults(host, projectId, apiKey, query)) as any[];
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
    const projectId = process.env.POSTHOG_PROJECT_ID;
    const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
      /\/$/,
      ""
    );

    if (!apiKey || !projectId) {
      return NextResponse.json(
        { error: "PostHog credentials not configured" },
        { status: 500 }
      );
    }

    const searchParams = request.nextUrl.searchParams;
    const days = parseInt(searchParams.get("days") || "14", 10);
    const intervals = parseInt(searchParams.get("intervals") || "10", 10);
    const platform = searchParams.get("platform") || "";

    // Context for Claude is a *second product* reporting into this same PostHog project. Its events
    // are namespaced `cfc_*` (see `desktop/context-for-claude/docs/analytics.md`) and set no `$os`,
    // so the `macos` branch below already excludes them — but this route's default branch applies no
    // event filter at all and would otherwise cohort every actor in the project, quietly counting
    // Context installs as new Omi users and folding them into this curve.
    //
    // Excluded on the event name rather than on `properties.app` because a property comparison is
    // NULL for every Omi event, and `properties.app != '…'` would therefore drop the entire
    // numerator instead of the intended rows. `startsWith(event, …)` is total: never NULL, and true
    // for exactly the events the other product emits.
    const excludeOtherProducts = `AND NOT startsWith(event, 'cfc_')`;
    const eventFilter =
      platform === "macos"
        ? `AND properties.$os_name = 'macOS' ${excludeOtherProducts}`
        : platform === "mobile"
        ? `AND properties.$os_name IN ('iOS', 'Android', 'iPadOS') ${excludeOtherProducts}`
        : excludeOtherProducts;
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
        WHERE timestamp >= today() - INTERVAL ${days} DAY
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
      const actorId = String(row[0] ?? "");
      const cohortDate = String(row[1] ?? "").slice(0, 10);
      if (!actorId || !cohortDate) continue;
      actorToCohortDate.set(actorId, cohortDate);
    }

    if (actorToCohortDate.size === 0) {
      return NextResponse.json({
        data: [],
        cohorts: [],
        totalCohorts: 0,
        totalUsers: 0,
      });
    }

    const actorIds = Array.from(actorToCohortDate.keys())
      .map((id) => `'${id.replace(/'/g, "\\'")}'`)
      .join(", ");

    const eventRows = await posthogQuery(
      host,
      projectId,
      apiKey,
      `
        SELECT
          COALESCE(person_id, distinct_id) AS actor_id,
          toDate(timestamp) AS event_date
        FROM events
        WHERE 1 = 1
          ${eventFilter}
          AND COALESCE(person_id, distinct_id) IN (${actorIds})
          AND timestamp >= today() - INTERVAL ${days} DAY
        GROUP BY actor_id, event_date
        ORDER BY actor_id ASC, event_date ASC
        LIMIT 100000
      `
    );

    const cohortUsers = new Map<string, Map<string, Set<number>>>();
    for (const [actorId, cohortDate] of Array.from(
      actorToCohortDate.entries()
    )) {
      const users =
        cohortUsers.get(cohortDate) ?? new Map<string, Set<number>>();
      users.set(actorId, new Set<number>([0]));
      cohortUsers.set(cohortDate, users);
    }

    for (const row of eventRows) {
      const actorId = String(row[0] ?? "");
      const eventDate = String(row[1] ?? "").slice(0, 10);
      const cohortDate = actorToCohortDate.get(actorId);
      if (!actorId || !eventDate || !cohortDate) continue;

      const cohortStart = new Date(`${cohortDate}T00:00:00Z`);
      const activeDate = new Date(`${eventDate}T00:00:00Z`);
      const offset = Math.round(
        (activeDate.getTime() - cohortStart.getTime()) / 86_400_000
      );
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
          Math.max(
            0,
            Math.floor((today.getTime() - cohortStart.getTime()) / 86_400_000)
          )
        );

        const data: RetentionPoint[] = [];
        const actorOffsets = Array.from(users.values());

        for (let day = 0; day <= maxAvailableDay; day++) {
          let retainedUsers = 0;
          for (const offsets of actorOffsets) {
            if (
              day === 0 ||
              Array.from(offsets).some((value) => value >= day)
            ) {
              retainedUsers += 1;
            }
          }
          data.push({
            day,
            retention:
              actorOffsets.length > 0
                ? Math.round((retainedUsers / actorOffsets.length) * 10000) /
                  100
                : 0,
          });
        }

        return {
          date: cohortDate,
          users: actorOffsets.length,
          data,
        };
      });

    const mean = weightedRetentionMean(cohorts);

    const totalUsers = cohorts.reduce((sum, cohort) => sum + cohort.users, 0);

    return NextResponse.json({
      data: mean,
      cohorts,
      totalCohorts: cohorts.length,
      totalUsers,
    });
  } catch (error) {
    console.error("Error fetching PostHog retention:", error);
    return NextResponse.json(
      { error: "Failed to fetch PostHog retention data" },
      { status: 500 }
    );
  }
}
