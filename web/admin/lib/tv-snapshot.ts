/**
 * TV dashboard snapshot: aggregate product metrics only (no PII).
 * Reuses admin Stripe/PostHog patterns; no Prometheus.
 */

import { posthogResults } from "@/lib/posthog";
import { computeRevenue } from "@/app/api/omi/stats/revenue/route";
import { getPayload, setPayload } from "@/lib/payload-cache";

export const MILLION_USERS = 1_000_000;
export const MILLION_RATE_DAYS = 7;

export type TvSnapshot = {
  generatedAt: string;
  title: string;
  sources: {
    stripe: boolean;
    posthog: boolean;
  };
  partial: boolean;
  warnings: string[];
  revenue: {
    mrr: number | null;
    arr: number | null;
    byProduct: Array<{ productId: string; name: string; mrr: number; subscriptions: number }>;
    unavailable?: boolean;
  } | null;
  activity: {
    dau1d: number | null;
    wau7d: number | null;
    desktopDau: number | null;
    mobileDau: number | null;
    chatUsers1d: number | null;
    memoryUsers1d: number | null;
    daily: Array<{ day: string; dau: number }>;
    detail: string;
  };
  million: {
    days: number | null;
    totalUsers: number | null;
    perDay: number | null;
    target: number;
    rateDays: number;
    series: Array<{ day: string; total: number; newUsers: number }>;
    detail: string;
  };
  features: {
    floatingBarQueries30d: number | null;
    floatingBarUsers30d: number | null;
  };
};

export function daysUntilMillion(
  totalUsers: number | null,
  dailyNew: Array<{ day: string; newUsers: number }>,
  opts: { target?: number; rateDays?: number } = {},
): TvSnapshot["million"] {
  const target = opts.target ?? MILLION_USERS;
  const rateDays = opts.rateDays ?? MILLION_RATE_DAYS;
  const total =
    totalUsers == null || !Number.isFinite(totalUsers) ? null : Math.round(totalUsers);
  const rows = dailyNew.filter((r) => r.day);
  const news = rows.map((r) => (Number.isFinite(r.newUsers) ? r.newUsers : 0));
  const recent = news.slice(-rateDays);
  const perDay = recent.length ? recent.reduce((a, b) => a + b, 0) / recent.length : null;

  let days: number | null = null;
  if (total != null && total >= target) days = 0;
  else if (total != null && perDay != null && perDay > 0) {
    days = Math.ceil((target - total) / perDay);
  }

  const series: Array<{ day: string; total: number; newUsers: number }> = [];
  if (total != null && rows.length) {
    let running = total;
    const rev: typeof series = [];
    for (let i = rows.length - 1; i >= 0; i--) {
      rev.push({ day: rows[i].day, total: Math.round(running), newUsers: news[i] });
      running -= news[i];
    }
    rev.reverse();
    series.push(...rev);
  }

  return {
    days,
    totalUsers: total,
    perDay: perDay == null ? null : Math.round(perDay * 10) / 10,
    target,
    rateDays,
    series,
    detail: "PostHog persons + 7d avg new persons/day",
  };
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function posthogCreds(): { host: string; projectId: string; apiKey: string } | null {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";
  if (!apiKey || !projectId) return null;
  return { host, projectId, apiKey };
}

async function loadPosthogActivity(creds: {
  host: string;
  projectId: string;
  apiKey: string;
}): Promise<{
  activity: TvSnapshot["activity"];
  million: TvSnapshot["million"];
  floating: TvSnapshot["features"];
  warnings: string[];
}> {
  const warnings: string[] = [];
  const activityQ = `
SELECT
  uniqIf(person_id, timestamp >= now() - INTERVAL 1 DAY) AS dau_1d,
  uniqIf(person_id, timestamp >= now() - INTERVAL 7 DAY) AS wau_7d,
  uniqIf(person_id, timestamp >= now() - INTERVAL 1 DAY AND properties['$os'] = 'macOS') AS desktop_dau,
  uniqIf(person_id, timestamp >= now() - INTERVAL 1 DAY AND properties['$os'] IN ('iOS', 'iPadOS', 'Android')) AS mobile_dau,
  uniqIf(person_id, timestamp >= now() - INTERVAL 1 DAY AND event = 'Chat Message Sent') AS chat_users_1d,
  uniqIf(person_id, timestamp >= now() - INTERVAL 1 DAY AND event IN ('Memory Created', 'Memory Extracted')) AS memory_users_1d
FROM events
WHERE timestamp >= now() - INTERVAL 7 DAY
LIMIT 1
`.trim();

  const dailyQ = `
SELECT
  toDate(timestamp) AS day,
  uniq(person_id) AS dau
FROM events
WHERE timestamp >= now() - INTERVAL 14 DAY
  AND timestamp < toStartOfDay(now())
GROUP BY day
ORDER BY day ASC
LIMIT 20
`.trim();

  const personsTotalQ = `
SELECT count() AS total_users
FROM persons
LIMIT 1
`.trim();

  const personsDailyQ = `
SELECT
  toDate(created_at) AS day,
  count() AS new_users
FROM persons
WHERE created_at >= now() - INTERVAL 30 DAY
  AND created_at < toStartOfDay(now())
GROUP BY day
ORDER BY day ASC
LIMIT 40
`.trim();

  const floatingQ = `
SELECT
  countIf(event IN ('floating_bar_query_sent', 'floating_bar_ask_omi_opened')) AS queries_30d,
  uniqIf(person_id, event IN ('floating_bar_query_sent', 'floating_bar_ask_omi_opened')) AS users_30d
FROM events
WHERE timestamp >= now() - INTERVAL 30 DAY
  AND properties['$os'] = 'macOS'
LIMIT 1
`.trim();

  const [activityR, dailyR, totalR, newR, floatR] = await Promise.allSettled([
    posthogResults(creds.host, creds.projectId, creds.apiKey, activityQ),
    posthogResults(creds.host, creds.projectId, creds.apiKey, dailyQ),
    posthogResults(creds.host, creds.projectId, creds.apiKey, personsTotalQ),
    posthogResults(creds.host, creds.projectId, creds.apiKey, personsDailyQ),
    posthogResults(creds.host, creds.projectId, creds.apiKey, floatingQ),
  ]);

  const activityRow =
    activityR.status === "fulfilled" && Array.isArray(activityR.value[0])
      ? (activityR.value[0] as unknown[])
      : activityR.status === "fulfilled" && activityR.value[0] && typeof activityR.value[0] === "object"
        ? Object.values(activityR.value[0] as object)
        : null;
  if (activityR.status === "rejected") warnings.push(`activity: ${activityR.reason}`);

  // HogQL results are usually arrays of values matching SELECT order
  const a = activityRow ?? [];
  // When results are objects with named keys:
  const aObj =
    activityR.status === "fulfilled" &&
    activityR.value[0] &&
    !Array.isArray(activityR.value[0]) &&
    typeof activityR.value[0] === "object"
      ? (activityR.value[0] as Record<string, unknown>)
      : null;

  const pick = (idx: number, key: string) =>
    aObj ? num(aObj[key]) : num(a[idx]);

  const daily: Array<{ day: string; dau: number }> = [];
  if (dailyR.status === "fulfilled") {
    for (const row of dailyR.value) {
      if (Array.isArray(row)) {
        daily.push({ day: String(row[0]), dau: num(row[1]) ?? 0 });
      } else if (row && typeof row === "object") {
        const o = row as Record<string, unknown>;
        daily.push({ day: String(o.day ?? o[0]), dau: num(o.dau ?? o[1]) ?? 0 });
      }
    }
  } else {
    warnings.push(`daily: ${dailyR.reason}`);
  }

  let totalUsers: number | null = null;
  if (totalR.status === "fulfilled") {
    const row = totalR.value[0];
    if (Array.isArray(row)) totalUsers = num(row[0]);
    else if (row && typeof row === "object")
      totalUsers = num((row as Record<string, unknown>).total_users);
  } else {
    warnings.push(`persons_total: ${totalR.reason}`);
  }

  const dailyNew: Array<{ day: string; newUsers: number }> = [];
  if (newR.status === "fulfilled") {
    for (const row of newR.value) {
      if (Array.isArray(row)) {
        dailyNew.push({ day: String(row[0]), newUsers: num(row[1]) ?? 0 });
      } else if (row && typeof row === "object") {
        const o = row as Record<string, unknown>;
        dailyNew.push({
          day: String(o.day),
          newUsers: num(o.new_users) ?? 0,
        });
      }
    }
  } else {
    warnings.push(`persons_daily: ${newR.reason}`);
  }

  let floatingBarQueries30d: number | null = null;
  let floatingBarUsers30d: number | null = null;
  if (floatR.status === "fulfilled") {
    const row = floatR.value[0];
    if (Array.isArray(row)) {
      floatingBarQueries30d = num(row[0]);
      floatingBarUsers30d = num(row[1]);
    } else if (row && typeof row === "object") {
      const o = row as Record<string, unknown>;
      floatingBarQueries30d = num(o.queries_30d);
      floatingBarUsers30d = num(o.users_30d);
    }
  } else {
    warnings.push(`floating_bar: ${floatR.reason}`);
  }

  return {
    activity: {
      dau1d: pick(0, "dau_1d"),
      wau7d: pick(1, "wau_7d"),
      desktopDau: pick(2, "desktop_dau"),
      mobileDau: pick(3, "mobile_dau"),
      chatUsers1d: pick(4, "chat_users_1d"),
      memoryUsers1d: pick(5, "memory_users_1d"),
      daily,
      detail: "PostHog distinct persons · 1d/7d windows",
    },
    million: daysUntilMillion(totalUsers, dailyNew),
    floating: {
      floatingBarQueries30d,
      floatingBarUsers30d,
    },
    warnings,
  };
}

export async function buildTvSnapshot(opts: {
  includeRevenue: boolean;
}): Promise<TvSnapshot> {
  const cacheKey = `tv-snapshot:v1:rev=${opts.includeRevenue ? 1 : 0}`;
  const cached = await getPayload<TvSnapshot>(cacheKey);
  if (cached?.data && Date.now() - cached.freshAt < 2 * 60 * 1000) {
    return cached.data;
  }

  const warnings: string[] = [];
  let revenue: TvSnapshot["revenue"] = null;
  let stripeOk = false;

  if (opts.includeRevenue) {
    try {
      const rev = await computeRevenue();
      stripeOk = !rev.unavailable;
      revenue = {
        mrr: rev.unavailable ? null : rev.mrr,
        arr: rev.unavailable ? null : rev.arr,
        byProduct: (rev.byProduct || []).map(
          (p: {
            productId: string;
            productName: string;
            mrr: number;
            subscriptionCount: number;
          }) => ({
            productId: p.productId,
            name: p.productName,
            mrr: p.mrr,
            subscriptions: p.subscriptionCount,
          }),
        ),
        unavailable: !!rev.unavailable,
      };
      if (rev.partial) warnings.push("stripe: partial subscription page");
    } catch (e) {
      warnings.push(`stripe: ${e instanceof Error ? e.message : String(e)}`);
      revenue = { mrr: null, arr: null, byProduct: [], unavailable: true };
    }
  }

  const creds = posthogCreds();
  let posthogOk = false;
  let activity: TvSnapshot["activity"] = {
    dau1d: null,
    wau7d: null,
    desktopDau: null,
    mobileDau: null,
    chatUsers1d: null,
    memoryUsers1d: null,
    daily: [],
    detail: "PostHog not configured",
  };
  let million: TvSnapshot["million"] = daysUntilMillion(null, []);
  let features: TvSnapshot["features"] = {
    floatingBarQueries30d: null,
    floatingBarUsers30d: null,
  };

  if (creds) {
    try {
      const ph = await loadPosthogActivity(creds);
      activity = ph.activity;
      million = ph.million;
      features = ph.floating;
      warnings.push(...ph.warnings);
      posthogOk =
        activity.dau1d != null ||
        million.totalUsers != null ||
        activity.daily.length > 0;
    } catch (e) {
      warnings.push(`posthog: ${e instanceof Error ? e.message : String(e)}`);
    }
  } else {
    warnings.push("posthog: POSTHOG_PERSONAL_API_KEY / PROJECT_ID missing");
  }

  const snap: TvSnapshot = {
    generatedAt: new Date().toISOString(),
    title: "Omi TV",
    sources: { stripe: stripeOk, posthog: posthogOk },
    partial: warnings.length > 0,
    warnings,
    revenue: opts.includeRevenue ? revenue : null,
    activity,
    million,
    features,
  };

  // Cache ~2 minutes worth via payload helper (its internal TTL may be longer;
  // key versioning keeps TV reasonably fresh).
  await setPayload(cacheKey, snap).catch(() => undefined);
  return snap;
}
