import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";

export const dynamic = "force-dynamic";

const GITHUB_REPO = "BasedHardware/omi";
const MACOS_TAG_SUFFIX = "-macos";
const IOS_BUNDLE_ID = "com.friend-app-with-wearable.ios12";
// TestFlight builds reach PostHog weeks before the App Store release; a
// version counts as publicly released on the first day it has this many
// distinct iOS users (public rollouts jump to thousands/day, betas stay low).
const IOS_PUBLIC_DAILY_USERS = 200;

type PlatformRelease = {
  version: string | null;
  date: string | null; // YYYY-MM-DD
  daysSince: number | null;
  display: string;
};

let cache: { data: any; days: number; timestamp: number } | null = null;
const CACHE_TTL = 15 * 60 * 1000;

function nycToday(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

function nycDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-CA", { timeZone: "America/New_York" });
}

function daysBetween(fromYmd: string, toYmd: string): number {
  return Math.round(
    (Date.parse(toYmd + "T00:00:00Z") - Date.parse(fromYmd + "T00:00:00Z")) / 86_400_000,
  );
}

function shortDate(ymd: string): string {
  return new Date(ymd + "T12:00:00Z").toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function buildRelease(version: string | null, date: string | null): PlatformRelease {
  if (!version || !date) {
    return { version, date, daysSince: null, display: "no releases found" };
  }
  const daysSince = daysBetween(date, nycToday());
  // Age lives in the separate color-thresholded `daysSince` field; keeping it
  // out of the display string stops the stat tile from wrapping.
  return { version, date, daysSince, display: `${version} · ${shortDate(date)}` };
}

async function fetchMacosReleases(days: number): Promise<{ dates: string[]; latest: PlatformRelease }> {
  const headers: Record<string, string> = {
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  }

  const dates: string[] = [];
  let latest: { version: string; date: string } | null = null;
  const cutoff = Date.now() - days * 86_400_000;

  for (let page = 1; page <= 3; page++) {
    const res = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/releases?per_page=100&page=${page}`,
      { headers, cache: "no-store" },
    );
    if (!res.ok) {
      throw new Error(`GitHub releases fetch failed: ${res.status}`);
    }
    const releases: any[] = await res.json();
    if (releases.length === 0) break;

    let sawOlderThanWindow = false;
    for (const release of releases) {
      const tag: string = release.tag_name ?? "";
      if (!tag.endsWith(MACOS_TAG_SUFFIX)) continue;
      const createdAt: string = release.created_at ?? release.published_at;
      if (!createdAt) continue;
      if (!latest) {
        const version = tag.replace(/^v/, "").replace(/\+.*$/, "").replace(MACOS_TAG_SUFFIX, "");
        latest = { version, date: nycDate(createdAt) };
      }
      if (Date.parse(createdAt) < cutoff) {
        sawOlderThanWindow = true;
        continue;
      }
      dates.push(nycDate(createdAt));
    }
    if (sawOlderThanWindow) break;
  }

  return {
    dates,
    latest: buildRelease(latest?.version ?? null, latest?.date ?? null),
  };
}

async function fetchIosReleases(days: number): Promise<{ dates: string[]; latest: PlatformRelease }> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";

  // Latest release: the App Store itself (exact version + release date).
  let latest: PlatformRelease;
  try {
    const res = await fetch(`https://itunes.apple.com/lookup?bundleId=${IOS_BUNDLE_ID}`, {
      cache: "no-store",
    });
    const body = await res.json();
    const app = body?.results?.[0];
    latest = buildRelease(
      app?.version ?? null,
      app?.currentVersionReleaseDate ? nycDate(app.currentVersionReleaseDate) : null,
    );
  } catch {
    latest = buildRelease(null, null);
  }

  // Release timeline: first day each version clears the public-rollout bar.
  let dates: string[] = [];
  if (apiKey && projectId) {
    const rows = (await posthogResults(
      host,
      projectId,
      apiKey,
      `
        SELECT v, min(d) AS release_day
        FROM (
          SELECT properties.$app_version AS v,
                 toDate(toTimeZone(timestamp, 'America/New_York')) AS d,
                 uniq(distinct_id) AS u
          FROM events
          WHERE event = 'Memory Created'
            AND properties.$os_name = 'iOS'
            AND timestamp >= now() - INTERVAL ${days + 14} DAY
          GROUP BY v, d
          HAVING u >= ${IOS_PUBLIC_DAILY_USERS}
        )
        GROUP BY v
        ORDER BY release_day
      `,
    )) as [string, string][];
    const cutoff = nycDate(new Date(Date.now() - days * 86_400_000).toISOString());
    dates = rows.map(([, day]) => String(day).slice(0, 10)).filter((d) => d >= cutoff);
  }

  return { dates, latest };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const days = Math.min(
      parseInt(request.nextUrl.searchParams.get("days") || "30", 10),
      90,
    );

    if (cache && cache.days === days && Date.now() - cache.timestamp < CACHE_TTL) {
      return NextResponse.json(cache.data);
    }

    const [macos, ios] = await Promise.all([
      fetchMacosReleases(days),
      fetchIosReleases(days),
    ]);

    const perDay = new Map<string, { macos: number; ios: number }>();
    const today = nycToday();
    for (let i = days - 1; i >= 0; i--) {
      const d = nycDate(new Date(Date.now() - i * 86_400_000).toISOString());
      if (d <= today) perDay.set(d, { macos: 0, ios: 0 });
    }
    for (const d of macos.dates) {
      const bucket = perDay.get(d);
      if (bucket) bucket.macos += 1;
    }
    for (const d of ios.dates) {
      const bucket = perDay.get(d);
      if (bucket) bucket.ios += 1;
    }

    const data = {
      days,
      latest: { macos: macos.latest, ios: ios.latest },
      daily: Array.from(perDay.entries()).map(([date, counts]) => ({ date, ...counts })),
    };
    cache = { data, days, timestamp: Date.now() };
    return NextResponse.json(data);
  } catch (error: any) {
    console.error("Releases stats error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch release stats" },
      { status: 500 },
    );
  }
}
