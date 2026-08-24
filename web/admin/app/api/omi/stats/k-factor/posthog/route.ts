import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
import {
  parsePlatformScope,
  scopeFilterAnd,
  type PlatformScope,
} from "@/lib/platform-scope";
export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// Run the referral funnel HogQL queries through posthogResults (Firestore
// query-cache + 429 backoff + stale fallback) and shape the panel payload.
// Exported so the precompute cron can warm the underlying query cache.
export async function computeKFactor(
  days: number,
  platform: PlatformScope = "macos",
) {
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

  const uniqueUsersQuery = (event: string, extraFilter = "") => `
          SELECT uniq(COALESCE(person_id, distinct_id)) AS unique_users
          FROM events
          WHERE event = '${event}'
            AND timestamp >= now() - INTERVAL ${days} DAY
            AND properties.program = 'desktop_operator_month_v1'
            ${extraFilter}
            ${scopeFilterAnd(platform, "properties.$os_name")}
        `;

  const [issuedRows, capturedRows, grantedRows] = await Promise.all([
    posthogResults(
      host,
      projectId,
      apiKey,
      uniqueUsersQuery("Referral Link Issued"),
    ) as Promise<any[]>,
    posthogResults(
      host,
      projectId,
      apiKey,
      uniqueUsersQuery("Referral Link Captured"),
    ) as Promise<any[]>,
    posthogResults(
      host,
      projectId,
      apiKey,
      uniqueUsersQuery("Referral Claimed", "AND properties.claimed = true"),
    ) as Promise<any[]>,
  ]);

  const issued = Number(issuedRows?.[0]?.[0] ?? 0);
  const captured = Number(capturedRows?.[0]?.[0] ?? 0);
  const granted = Number(grantedRows?.[0]?.[0] ?? 0);

  return {
    days,
    available: true as const,
    kFactor: issued > 0 ? granted / issued : null,
    reason:
      "Referral grants are measured from the server-side referral funnel.",
    funnel: { issued, captured, granted },
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const searchParams = request.nextUrl.searchParams;
  const days = parseInt(searchParams.get("days") || "30", 10);
  const platform = parsePlatformScope(searchParams.get("platform") ?? "macos");

  try {
    const payload = await computeKFactor(days, platform);
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
