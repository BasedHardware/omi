import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { posthogResults } from "@/lib/posthog";
import { getDb } from "@/lib/firebase/admin";
import {
  parsePlatformScope,
  scopeFilterAnd,
  type PlatformScope,
} from "@/lib/platform-scope";
export const dynamic = "force-dynamic";
export const maxDuration = 3600;

// The viral loop is measured from three concrete signals:
//   friend   — onboarding "How did you hear about us?" answered "Friend"
//              (macOS/Windows `Onboarding How Did You Hear`, source='Friend').
//   referral — referral-trial redemptions. Firestore `users/{uid}.referral`
//              (written transactionally on every granted claim) is the durable
//              ledger; the PostHog funnel events only started firing 2026-08-25.
//   shares   — conversation summaries shared: macOS `Share Action`
//              category='conversation' (share-link copies) + server-side
//              `Conversation Summary Shared` (delivered share emails) +
//              mobile `Conversation Shared`.
// K-factor = viral events per first-seen new user in the same window.
const REFERRAL_PROGRAM = "desktop_operator_month_v1";
const NYC_DAY = "toDate(toTimeZone(timestamp, 'America/New_York'))";

type DailyRow = {
  date: string;
  friend: number;
  referral: number;
  shares: number;
  viralEvents: number;
  newUsers: number;
  kFactor: number | null;
};

function shareEventsFilter(platform: PlatformScope): string {
  // `Conversation Summary Shared` is emitted server-side (no $os_name); the
  // share-email UI ships only on desktop, so it counts toward macos and all.
  const macosShares = `((event = 'Share Action' AND properties.category = 'conversation' AND properties.$os_name = 'macOS') OR event = 'Conversation Summary Shared')`;
  const mobileShares = `(event = 'Conversation Shared' ${scopeFilterAnd("mobile")})`;
  if (platform === "macos") return macosShares;
  if (platform === "mobile") return mobileShares;
  return `(${macosShares} OR (event = 'Share Action' AND properties.category = 'conversation') OR event = 'Conversation Shared')`;
}

function friendFilter(platform: PlatformScope): string {
  // Only macOS/Windows onboarding carries the source property; the mobile
  // acquisition step reports step-reach without the answer, so the mobile
  // scope is honestly zero rather than silently borrowing desktop data.
  return `event = 'Onboarding How Did You Hear' AND properties.source = 'Friend' ${scopeFilterAnd(platform)}`;
}

export const REFERRAL_LEDGER_PAGE_SIZE = 1000;

async function referralClaimTimes(): Promise<number[]> {
  // Firestore is the transactional record of granted referral trials
  // (backend/database/referrals.py); claimed_at is epoch seconds. Cursor
  // pagination (document-ID order, no composite index needed) reads the WHOLE
  // ledger — a bare unordered limit() silently dropped arbitrary claims once
  // the ledger outgrew it.
  const base = getDb()
    .collection("users")
    .where("referral.program", "==", REFERRAL_PROGRAM);
  const times: number[] = [];
  let cursor: any = null;
  for (;;) {
    let query = base.limit(REFERRAL_LEDGER_PAGE_SIZE);
    if (cursor) query = query.startAfter(cursor);
    const snapshot = await query.get();
    for (const doc of snapshot.docs) {
      const claimedAt = doc.get("referral.claimed_at");
      const seconds =
        typeof claimedAt === "number" ? claimedAt : claimedAt?.seconds;
      if (seconds) times.push(seconds * 1000);
    }
    if (snapshot.docs.length < REFERRAL_LEDGER_PAGE_SIZE) return times;
    cursor = snapshot.docs[snapshot.docs.length - 1];
  }
}

function nycDateDaysAgo(daysAgo: number): string {
  return new Date(Date.now() - daysAgo * 86_400_000).toLocaleDateString(
    "en-CA",
    { timeZone: "America/New_York" },
  );
}

export async function computeKFactor(days: number, platform: PlatformScope = "macos") {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = (process.env.POSTHOG_HOST || "https://us.posthog.com").replace(
    /\/$/,
    "",
  );

  if (!apiKey || !projectId) {
    return {
      days,
      platform,
      available: false as const,
      kFactor: null,
      reason: "PostHog credentials not configured.",
    };
  }

  const dailyCountQuery = (filter: string) => `
        SELECT ${NYC_DAY} AS day, count() AS events
        FROM events
        WHERE ${filter}
          AND timestamp >= now() - INTERVAL ${days} DAY
        GROUP BY day
        ORDER BY day
      `;
  // One query per signal covers both rolling windows: [24h, trailing 7d].
  const rollingCountQuery = (filter: string) => `
        SELECT
          countIf(timestamp >= now() - INTERVAL 24 HOUR) AS h24,
          count() AS d7
        FROM events
        WHERE ${filter}
          AND timestamp >= now() - INTERVAL 7 DAY
      `;
  const firstSeenSubquery = `
        SELECT COALESCE(person_id, distinct_id) AS actor, min(timestamp) AS min_ts
        FROM events
        WHERE 1 = 1
          ${scopeFilterAnd(platform)}
        GROUP BY actor
      `;
  const referralFunnelQuery = (event: string, extraFilter = "") => `
        SELECT uniq(COALESCE(person_id, distinct_id)) AS unique_users
        FROM events
        WHERE event = '${event}'
          AND timestamp >= now() - INTERVAL ${days} DAY
          AND properties.program = '${REFERRAL_PROGRAM}'
          ${extraFilter}
      `;

  const run = (query: string) =>
    posthogResults(host, projectId, apiKey, query) as Promise<any[]>;

  const [
    friendDailyRows,
    sharesDailyRows,
    newDailyRows,
    friendRollingRows,
    sharesRollingRows,
    newRollingRows,
    issuedRows,
    capturedRows,
    grantedRows,
    referralTimes,
  ] = await Promise.all([
    run(dailyCountQuery(friendFilter(platform))),
    run(dailyCountQuery(shareEventsFilter(platform))),
    run(`
        SELECT toDate(toTimeZone(min_ts, 'America/New_York')) AS day, count(*) AS new_users
        FROM (${firstSeenSubquery})
        WHERE min_ts >= now() - INTERVAL ${days} DAY
        GROUP BY day
        ORDER BY day
      `),
    run(rollingCountQuery(friendFilter(platform))),
    run(rollingCountQuery(shareEventsFilter(platform))),
    run(`
        SELECT
          countIf(min_ts >= now() - INTERVAL 24 HOUR) AS h24,
          count() AS d7
        FROM (${firstSeenSubquery})
        WHERE min_ts >= now() - INTERVAL 7 DAY
      `),
    run(referralFunnelQuery("Referral Link Issued")),
    run(referralFunnelQuery("Referral Link Captured")),
    run(referralFunnelQuery("Referral Claimed", "AND properties.claimed = true")),
    // The referral program grants a desktop trial, so redemptions belong to
    // the macos and all scopes; the mobile board honestly reports zero.
    platform === "mobile" ? Promise.resolve([]) : referralClaimTimes(),
  ]);
  const toNycDate = (ms: number) =>
    new Date(ms).toLocaleDateString("en-CA", { timeZone: "America/New_York" });

  const toDayMap = (rows: any[]) => {
    const map = new Map<string, number>();
    for (const row of rows ?? []) {
      map.set(String(row[0]).slice(0, 10), Number(row[1]) || 0);
    }
    return map;
  };
  const friendByDay = toDayMap(friendDailyRows);
  const sharesByDay = toDayMap(sharesDailyRows);
  const newByDay = toDayMap(newDailyRows);
  const referralByDay = new Map<string, number>();
  for (const ms of referralTimes) {
    const date = toNycDate(ms);
    referralByDay.set(date, (referralByDay.get(date) ?? 0) + 1);
  }

  const today = nycDateDaysAgo(0);
  const daily: DailyRow[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const date = nycDateDaysAgo(i);
    if (date > today) continue;
    const friend = friendByDay.get(date) ?? 0;
    const referral = referralByDay.get(date) ?? 0;
    const shares = sharesByDay.get(date) ?? 0;
    const newUsers = newByDay.get(date) ?? 0;
    const viralEvents = friend + referral + shares;
    daily.push({
      date,
      friend,
      referral,
      shares,
      viralEvents,
      newUsers,
      kFactor: newUsers > 0 ? viralEvents / newUsers : null,
    });
  }

  const [friend24h, friend7d] = friendRollingRows?.[0] ?? [0, 0];
  const [shares24h, shares7d] = sharesRollingRows?.[0] ?? [0, 0];
  const [new24h, new7d] = newRollingRows?.[0] ?? [0, 0];
  const referral24h = referralTimes.filter(
    (ms) => ms >= Date.now() - 86_400_000,
  ).length;
  const referral7d = referralTimes.filter(
    (ms) => ms >= Date.now() - 7 * 86_400_000,
  ).length;

  // Window totals come from the CALENDAR buckets only. A trailing-24h window
  // overlaps yesterday's calendar bucket, so summing it alongside yesterday
  // would double-count the overlapping hours.
  const totals = daily.reduce(
    (acc, row) => ({
      friend: acc.friend + row.friend,
      referral: acc.referral + row.referral,
      shares: acc.shares + row.shares,
      newUsers: acc.newUsers + row.newUsers,
    }),
    { friend: 0, referral: 0, shares: 0, newUsers: 0 },
  );
  const viralEvents = totals.friend + totals.referral + totals.shares;

  // Weekly tracker: NYC Monday buckets aggregated from the calendar daily
  // series (same non-overlap rule as the totals above); only the
  // last bucket is the rolling trailing 7 days, never a partial calendar week.
  const weekOf = (ymd: string) => {
    const d = new Date(ymd + "T12:00:00Z");
    const shift = (d.getUTCDay() + 6) % 7;
    d.setUTCDate(d.getUTCDate() - shift);
    return d.toISOString().slice(0, 10);
  };
  const weeklyMap = new Map<string, DailyRow>();
  for (const row of daily) {
    const week = weekOf(row.date);
    const bucket =
      weeklyMap.get(week) ??
      ({ date: week, friend: 0, referral: 0, shares: 0, viralEvents: 0, newUsers: 0, kFactor: null } as DailyRow);
    bucket.friend += row.friend;
    bucket.referral += row.referral;
    bucket.shares += row.shares;
    bucket.viralEvents += row.viralEvents;
    bucket.newUsers += row.newUsers;
    weeklyMap.set(week, bucket);
  }
  const weekly = Array.from(weeklyMap.values())
    .map(({ date, ...rest }) => ({ week: date, ...rest }))
    .sort((a, b) => (a.week < b.week ? -1 : 1));
  if (weekly.length > 0) {
    const rolling = {
      week: weekly[weekly.length - 1].week,
      friend: Number(friend7d) || 0,
      referral: referral7d,
      shares: Number(shares7d) || 0,
      viralEvents: 0,
      newUsers: Number(new7d) || 0,
      kFactor: null as number | null,
    };
    rolling.viralEvents = rolling.friend + rolling.referral + rolling.shares;
    rolling.kFactor =
      rolling.newUsers > 0 ? rolling.viralEvents / rolling.newUsers : null;
    weekly[weekly.length - 1] = rolling;
  }
  for (const bucket of weekly) {
    if (bucket.kFactor === null && bucket.newUsers > 0) {
      bucket.kFactor = bucket.viralEvents / bucket.newUsers;
    }
  }

  // Display-only, applied AFTER every aggregation: the newest chart bar shows
  // the rolling last 24 hours instead of a partial calendar day.
  const last = daily[daily.length - 1];
  if (last && last.date === today) {
    last.friend = Math.max(last.friend, Number(friend24h) || 0);
    last.shares = Math.max(last.shares, Number(shares24h) || 0);
    last.referral = Math.max(last.referral, referral24h);
    last.newUsers = Math.max(last.newUsers, Number(new24h) || 0);
    last.viralEvents = last.friend + last.referral + last.shares;
    last.kFactor = last.newUsers > 0 ? last.viralEvents / last.newUsers : null;
  }

  const issued = Number(issuedRows?.[0]?.[0] ?? 0);
  const captured = Number(capturedRows?.[0]?.[0] ?? 0);
  const granted = Number(grantedRows?.[0]?.[0] ?? 0);

  return {
    days,
    platform,
    available: true as const,
    kFactor: totals.newUsers > 0 ? viralEvents / totals.newUsers : null,
    reason:
      "K-factor = viral events (friend signups + referral redemptions + summary shares) per first-seen new user.",
    funnel: { issued, captured, granted },
    summary: {
      ...totals,
      viralEvents,
      kFactor: totals.newUsers > 0 ? viralEvents / totals.newUsers : null,
      friend7d: Number(friend7d) || 0,
      referral7d,
      shares7d: Number(shares7d) || 0,
    },
    daily,
    weekly,
  };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  const searchParams = request.nextUrl.searchParams;
  const days = parseInt(searchParams.get("days") || "30", 10);
  const platform = parsePlatformScope(searchParams.get("platform"));

  try {
    const payload = await computeKFactor(days, platform);
    return NextResponse.json(payload);
  } catch (error) {
    // PostHog still failing (e.g. 429 with no cached fallback) — degrade
    // gracefully so the panel never hard-errors with a 502/500.
    console.error("Error fetching PostHog k-factor proxy:", error);
    return NextResponse.json({
      days,
      platform,
      available: false as const,
      kFactor: null,
      reason:
        "PostHog data is temporarily unavailable (rate-limited). Try again shortly.",
    });
  }
}
