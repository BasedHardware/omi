import { NextRequest, NextResponse } from 'next/server';
import { verifyAdmin } from '@/lib/auth';

export const dynamic = 'force-dynamic';

const GITHUB_REPO = 'BasedHardware/omi';
const RELEASE_TAG_SUFFIX = '-macos';
const RELEASE_LIMIT = 30;

const POSTHOG_API_KEY = process.env.POSTHOG_PERSONAL_API_KEY;
const POSTHOG_PROJECT_ID = process.env.POSTHOG_PROJECT_ID || '302298';
const POSTHOG_BASE = 'https://us.posthog.com';

// --- Types ---

interface ReleaseRow {
  version: string;
  tag: string;
  published_at: string;
  html_url: string;
  crash_rate: number | null;
  crash_count: number | null;
  session_count: number | null;
  feedback_count: number | null;
  broken_count: number | null;
  rating: number | null;
  summary: string | null;
}

// --- GitHub ---

async function fetchGithubReleases(): Promise<any[]> {
  const headers: Record<string, string> = {
    Accept: 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
  };
  if (process.env.GITHUB_TOKEN) {
    headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
  }
  const res = await fetch(
    `https://api.github.com/repos/${GITHUB_REPO}/releases?per_page=100`,
    { headers, cache: 'no-store' }
  );
  if (!res.ok) throw new Error(`GitHub ${res.status}: ${await res.text()}`);
  return res.json();
}

function parseVersion(tag: string): string | null {
  const m = tag.match(/^v(\d+\.\d+\.\d+)\+\d+-macos$/);
  return m ? m[1] : null;
}

// --- PostHog ---

async function posthogQuery(query: string): Promise<any> {
  if (!POSTHOG_API_KEY) return null;
  const res = await fetch(`${POSTHOG_BASE}/api/projects/${POSTHOG_PROJECT_ID}/query/`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${POSTHOG_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: { kind: 'HogQLQuery', query } }),
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text();
    console.error(`PostHog query error ${res.status}: ${text}`);
    return null;
  }
  return res.json();
}

interface VersionMetrics {
  crashes: number;
  launches: number;
  feedbacks: number;
  brokens: number;
  resets: number;
}

async function fetchPostHogMetrics(
  versions: string[]
): Promise<Map<string, VersionMetrics>> {
  const results = new Map<string, VersionMetrics>();
  if (!POSTHOG_API_KEY || versions.length === 0) return results;

  // Initialize all versions
  for (const v of versions) {
    results.set(v, { crashes: 0, launches: 0, feedbacks: 0, brokens: 0, resets: 0 });
  }

  // Single query: counts per event per version, last 60 days
  const data = await posthogQuery(`
    SELECT
      properties.$app_version AS version,
      event,
      count() AS cnt,
      count(DISTINCT distinct_id) AS users
    FROM events
    WHERE event IN (
      'App Crash Detected',
      'App Launched',
      'Feedback Submitted',
      'Screen Capture Broken Detected',
      'Screen Capture Reset Clicked'
    )
    AND timestamp >= now() - INTERVAL 60 DAY
    AND properties.$app_version IS NOT NULL
    GROUP BY version, event
  `);

  if (!data?.results) return results;

  for (const row of data.results) {
    const [version, event, count] = row;
    if (!version || !results.has(version)) continue;
    const m = results.get(version)!;
    switch (event) {
      case 'App Crash Detected': m.crashes = count; break;
      case 'App Launched': m.launches = count; break;
      case 'Feedback Submitted': m.feedbacks = count; break;
      case 'Screen Capture Broken Detected': m.brokens = count; break;
      case 'Screen Capture Reset Clicked': m.resets = count; break;
    }
  }

  return results;
}

// --- Rating + Summary ---

function computeRatingAndSummary(
  m: VersionMetrics
): { rating: number; summary: string } {
  const crashRate = m.launches > 0 ? m.crashes / m.launches : 0;
  const issues: string[] = [];
  let score = 5.0;

  // Crash rate scoring
  if (crashRate >= 0.05) {
    score -= 2.5;
    issues.push(`high crash rate (${(crashRate * 100).toFixed(1)}%)`);
  } else if (crashRate >= 0.02) {
    score -= 1.5;
    issues.push(`elevated crash rate (${(crashRate * 100).toFixed(1)}%)`);
  } else if (crashRate >= 0.005) {
    score -= 0.5;
    issues.push(`minor crash rate (${(crashRate * 100).toFixed(1)}%)`);
  }

  // Screen capture broken scoring
  if (m.brokens > 100) {
    score -= 1.5;
    issues.push(`${m.brokens} screen capture failures`);
  } else if (m.brokens > 20) {
    score -= 0.75;
    issues.push(`${m.brokens} screen capture failures`);
  } else if (m.brokens > 5) {
    score -= 0.25;
    issues.push(`${m.brokens} screen capture failures`);
  }

  // Feedback scoring
  if (m.feedbacks > 10) {
    score -= 1.0;
    issues.push(`${m.feedbacks} user complaints`);
  } else if (m.feedbacks > 3) {
    score -= 0.5;
    issues.push(`${m.feedbacks} user complaints`);
  } else if (m.feedbacks > 0) {
    score -= 0.25;
    issues.push(`${m.feedbacks} user complaint${m.feedbacks === 1 ? '' : 's'}`);
  }

  // Reset clicks
  if (m.resets > 5) {
    score -= 0.5;
    issues.push(`${m.resets} permission reset clicks`);
  }

  score = Math.max(0, Math.min(5, Math.round(score * 10) / 10));

  let summary: string;
  if (m.launches === 0) {
    summary = 'No usage data yet';
    score = 0;
  } else if (issues.length === 0) {
    summary = `Clean release — ${m.launches} sessions, no significant issues`;
  } else {
    summary = issues.join(', ');
    // Capitalize first letter
    summary = summary.charAt(0).toUpperCase() + summary.slice(1);
  }

  return { rating: score, summary };
}

// --- Handler ---

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  let github_error: string | null = null;
  let posthog_error: string | null = null;

  // 1. GitHub releases
  let githubReleases: any[] = [];
  try {
    githubReleases = await fetchGithubReleases();
  } catch (err: any) {
    github_error = err?.message || String(err);
    return NextResponse.json(
      { releases: [], github_error, posthog_error: null, partial: true },
      { status: 502 }
    );
  }

  const desktopReleases = githubReleases
    .filter((r) => typeof r.tag_name === 'string' && r.tag_name.endsWith(RELEASE_TAG_SUFFIX))
    .filter((r) => parseVersion(r.tag_name) !== null)
    .slice(0, RELEASE_LIMIT);

  const versions = desktopReleases.map((r) => parseVersion(r.tag_name)!);

  // 2. PostHog metrics
  let metricsMap = new Map<string, VersionMetrics>();
  try {
    metricsMap = await fetchPostHogMetrics(versions);
  } catch (err: any) {
    posthog_error = err?.message || String(err);
  }

  // 3. Compose rows
  const rows: ReleaseRow[] = desktopReleases.map((r) => {
    const version = parseVersion(r.tag_name)!;
    const m = metricsMap.get(version);
    const crashRate = m && m.launches > 0 ? m.crashes / m.launches : null;
    const { rating, summary } = m ? computeRatingAndSummary(m) : { rating: null, summary: null };

    return {
      version,
      tag: r.tag_name,
      published_at: r.published_at,
      html_url: r.html_url,
      crash_rate: crashRate,
      crash_count: m?.crashes ?? null,
      session_count: m?.launches ?? null,
      feedback_count: m?.feedbacks ?? null,
      broken_count: m?.brokens ?? null,
      rating,
      summary,
    };
  });

  return NextResponse.json({
    releases: rows,
    github_error: null,
    posthog_error,
    partial: posthog_error !== null,
  });
}
