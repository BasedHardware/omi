import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getPayload, setPayload, withFreshness } from "@/lib/payload-cache";
import { toGrafanaActivationPayload } from "@/lib/activation-compat";
import { posthogResults } from "@/lib/posthog";
import {
  rollUpActivationCohort,
  type ActivationCohortMember,
  type ActivationSeries,
} from "@/lib/growth-metrics";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Activation (Nik, 2026-08-28): a macOS signup counts as activated when they
// ask 2+ questions within their first 48 hours. Signup = first-seen
// macOS actor in PostHog (the same person-deduped anchor every other board
// cohort uses); question = typed chat (`Chat Message Sent`, every main-window
// chat surface) PLUS floating-bar/push-to-talk queries
// (`floating_bar_query_sent`) — PTT is ~a third of question volume and must
// count (Nik, 2026-09-01). Only questions asked AFTER `Onboarding Completed`
// count: the onboarding chat itself sends questions, and finishing onboarding
// is part of being activated — a user who never completed it is not
// activated regardless of onboarding-chat activity (Nik, 2026-09-01). Signups younger than the 48h window are not
// yet matured and are excluded so the rate is never depressed by users whose
// window is still open. Replaces the older Firestore definition (>=1
// conversation within 7 days).
export const ACTIVATION_QUESTIONS = 2;
export const ACTIVATION_WINDOW_HOURS = 48;

export function activationCacheKey(days: number): string {
  return `activation:v4:macos-2q48h-ptt-postonb:${days}`;
}

export type ActivationDailyPoint = {
  date: string;
  signups: number;
  activated: number;
  rate: number;
};

function nycDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", {
    timeZone: "America/New_York",
  });
}

export function rollUpDaily(
  members: readonly ActivationCohortMember[],
): ActivationDailyPoint[] {
  const byDay = new Map<string, { signups: number; activated: number }>();
  for (const member of members) {
    const day = nycDate(member.signupAt);
    const entry = byDay.get(day) ?? { signups: 0, activated: 0 };
    entry.signups += 1;
    if (member.activated) entry.activated += 1;
    byDay.set(day, entry);
  }
  return Array.from(byDay.entries())
    .map(([date, { signups, activated }]) => ({
      date,
      signups,
      activated,
      rate: signups > 0 ? Math.round((1000 * activated) / signups) / 10 : 0,
    }))
    .sort((a, b) => (a.date < b.date ? -1 : 1));
}

export async function computeActivation(
  days: number,
): Promise<
  ActivationSeries & { daily: ActivationDailyPoint[]; erroredUsers: number }
> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );
  if (!apiKey || !projectId) {
    throw new Error("PostHog credentials not configured");
  }

  // One query: each first-seen macOS actor in the window (matured only) with
  // their question count inside the first ACTIVATION_WINDOW_HOURS.
  const rows = (await posthogResults(
    host,
    projectId,
    apiKey,
    `
      WITH firsts AS (
        SELECT COALESCE(person_id, distinct_id) AS actor, min(timestamp) AS first_ts
        FROM events
        WHERE properties.$os_name = 'macOS'
        GROUP BY actor
        HAVING first_ts >= now() - INTERVAL ${days} DAY
          AND first_ts <= now() - INTERVAL ${ACTIVATION_WINDOW_HOURS} HOUR
      ),
      onboarded AS (
        SELECT COALESCE(person_id, distinct_id) AS actor, min(timestamp) AS onb_ts
        FROM events
        WHERE event = 'Onboarding Completed' AND properties.$os_name = 'macOS'
          AND timestamp >= now() - INTERVAL ${days + 2} DAY
        GROUP BY actor
      )
      SELECT toString(any(f.first_ts)) AS first_ts,
             countIf(
               e.event IN ('Chat Message Sent', 'floating_bar_query_sent')
               AND o.onb_ts > toDateTime(0)
               AND e.timestamp >= o.onb_ts
               AND e.timestamp >= f.first_ts
               AND e.timestamp <= f.first_ts + INTERVAL ${ACTIVATION_WINDOW_HOURS} HOUR
             ) AS questions
      FROM firsts f
      LEFT JOIN onboarded o ON o.actor = f.actor
      LEFT JOIN events e
        ON COALESCE(e.person_id, e.distinct_id) = f.actor
        AND e.timestamp >= now() - INTERVAL ${days + 2} DAY
      GROUP BY f.actor
    `,
  )) as any[];

  const members: ActivationCohortMember[] = (rows ?? []).map(
    ([firstTs, questions]) => ({
      signupAt: new Date(String(firstTs).replace(" ", "T") + "Z").toISOString(),
      activated: Number(questions) >= ACTIVATION_QUESTIONS,
    }),
  );

  return {
    ...rollUpActivationCohort(members),
    daily: rollUpDaily(members),
    erroredUsers: 0,
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    // A non-numeric `days` would otherwise reach the query as NaN.
    const requestedDays = parseInt(
      request.nextUrl.searchParams.get("days") || "60",
      10,
    );
    const days = Number.isFinite(requestedDays)
      ? Math.min(Math.max(requestedDays, 1), 180)
      : 60;
    const key = activationCacheKey(days);

    const cached =
      await getPayload<Awaited<ReturnType<typeof computeActivation>>>(key);
    if (cached) {
      return NextResponse.json(
        withFreshness(toGrafanaActivationPayload(cached.data), cached.freshAt),
      );
    }

    const payload = await computeActivation(days);
    await setPayload(key, payload);
    return NextResponse.json(
      withFreshness(toGrafanaActivationPayload(payload), Date.now()),
    );
  } catch (error: any) {
    console.error("Activation error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to compute activation" },
      { status: 500 },
    );
  }
}
