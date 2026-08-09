/**
 * TV dashboard snapshot — product metrics shaped like omi-tv-metrics prototype.
 * PostHog via posthogResults + Stripe via computeRevenue. No Prometheus / no M1 / no habit.
 */

import { posthogResults } from "@/lib/posthog";
import { computeRevenue } from "@/app/api/omi/stats/revenue/route";
import { getPayload, setPayload } from "@/lib/payload-cache";

export const MILLION_USERS = 1_000_000;
export const MILLION_RATE_DAYS = 7;
export const WINDOW_HOURS = [12, 24, 72] as const;
export type WindowHours = (typeof WINDOW_HOURS)[number];

const CORE_EVENTS = `(
  'Chat Message Sent','floating_bar_query_sent','Floating Bar Query Sent',
  'Phone Mic Recording Started','Desktop Recording Started','Action Items Page Opened','Action Item Completed',
  'Action Item Manually Added','Action Item Edited','Conversation List Item Clicked',
  'Conversation Detail Opened','Daily Summary Detail Viewed','Rewind Screenshot Viewed',
  'Task Added','Task Completed','Memory Created','Memory Extracted','App Launched'
)`;

const PLATFORM_EXPR = `multiIf(
  coalesce(properties['$os_name'], properties['$os']) = 'macOS', 'macos',
  coalesce(properties['$os_name'], properties['$os']) = 'Windows', 'windows',
  coalesce(properties['$os_name'], properties['$os']) IN ('iOS','iPadOS'), 'ios',
  coalesce(properties['$os_name'], properties['$os']) = 'Android', 'android',
  'other'
)`;

const CHAT_EVENTS = `event IN ('Chat Message Sent','floating_bar_query_sent','Floating Bar Query Sent')`;
const MEMORY_EVENTS = `event = 'Memory Extracted'`;
const CONV_EVENT = `event IN ('Phone Mic Recording Started','Desktop Recording Started')`;

export type SeriesPoint = {
  t: number;
  total?: number;
  macos?: number;
  windows?: number;
  ios?: number;
  android?: number;
  v?: number;
};

export type FeatBoard = {
  byHours: Record<string, number | null>;
  platforms: Record<string, Record<string, number | null>>;
  series: SeriesPoint[];
};

export type TvSnapshot = {
  generatedAt: string;
  title: string;
  sources: { stripe: boolean; posthog: boolean };
  partial: boolean;
  warnings: string[];
  revenue: {
    mrr: number | null;
    arr: number | null;
    subscriptionCount: number | null;
    byProduct: Array<{ name: string; arr: number; subscriptions: number }>;
    unavailable?: boolean;
  } | null;
  activity: {
    byHours: Record<
      string,
      { total: number | null; platforms: Record<string, number | null> }
    >;
    wau: number | null;
    series: SeriesPoint[];
  };
  features: {
    conversation: FeatBoard;
    chat: FeatBoard;
    memories: FeatBoard;
  };
  million: {
    days: number | null;
    totalUsers: number | null;
    perDay: number | null;
    target: number;
    rateDays: number;
    series: SeriesPoint[];
  };
};

export function daysUntilMillion(
  totalUsers: number | null,
  dailyNew: Array<{ day: string; newUsers: number }>,
  opts: { target?: number; rateDays?: number; asOf?: Date | string } = {},
): TvSnapshot["million"] {
  const target = opts.target ?? MILLION_USERS;
  const rateDays = opts.rateDays ?? MILLION_RATE_DAYS;
  const total =
    totalUsers == null || !Number.isFinite(totalUsers)
      ? null
      : Math.round(totalUsers);

  const byDay = new Map<string, number>();
  for (const r of dailyNew) {
    if (!r.day) continue;
    byDay.set(r.day, Number.isFinite(r.newUsers) ? r.newUsers : 0);
  }
  const daysSorted = Array.from(byDay.keys()).sort();

  let perDay: number | null = null;
  // Anchor to latest *completed* UTC day (yesterday), not the last day that happened to have rows.
  const asOf = opts.asOf ? new Date(opts.asOf) : new Date();
  const end = new Date(
    Date.UTC(asOf.getUTCFullYear(), asOf.getUTCMonth(), asOf.getUTCDate()),
  );
  end.setUTCDate(end.getUTCDate() - 1);
  const endMs = end.getTime();
  if (daysSorted.length) {
    let sum = 0;
    for (let i = 0; i < rateDays; i++) {
      const d = new Date(endMs - i * 86400000);
      const key = d.toISOString().slice(0, 10);
      sum += byDay.get(key) ?? 0;
    }
    perDay = sum / rateDays;
  }

  let days: number | null = null;
  if (total != null && total >= target) days = 0;
  else if (total != null && perDay != null && perDay > 0) {
    days = Math.ceil((target - total) / perDay);
  }

  const series: SeriesPoint[] = [];
  if (total != null && daysSorted.length) {
    let running = total;
    const rev: SeriesPoint[] = [];
    for (let i = daysSorted.length - 1; i >= 0; i--) {
      const day = daysSorted[i];
      const ts = Date.parse(`${day}T00:00:00Z`) / 1000;
      rev.push({ t: ts, v: Math.round(running), total: Math.round(running) });
      running -= byDay.get(day) ?? 0;
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
  };
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function asRows(
  results: unknown[],
  columns: string[],
): Record<string, unknown>[] {
  if (!results?.length) return [];
  if (Array.isArray(results[0])) {
    return (results as unknown[][]).map((r) => {
      const o: Record<string, unknown> = {};
      r.forEach((v, i) => {
        o[columns[i] || String(i)] = v;
        o[String(i)] = v;
      });
      return o;
    });
  }
  return results.map((r) =>
    r && typeof r === "object" ? (r as Record<string, unknown>) : {},
  );
}

function bucketTs(raw: unknown): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") return raw > 1e12 ? raw / 1000 : raw;
  const n = Date.parse(String(raw));
  return Number.isNaN(n) ? null : n / 1000;
}

function posthogCreds(): {
  host: string;
  projectId: string;
  apiKey: string;
} | null {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";
  if (!apiKey || !projectId) return null;
  return { host, projectId, apiKey };
}

async function ph(
  creds: { host: string; projectId: string; apiKey: string },
  query: string,
): Promise<unknown[]> {
  return posthogResults(creds.host, creds.projectId, creds.apiKey, query);
}

function emptyHours(): Record<string, number | null> {
  return { "12": null, "24": null, "72": null };
}

function buildFeatHours(
  rows: Record<string, unknown>[],
  prefix: string,
): {
  byHours: Record<string, number | null>;
  platforms: Record<string, Record<string, number | null>>;
} {
  const bh = emptyHours();
  const platforms: Record<string, Record<string, number | null>> = {};
  const sums: Record<string, number> = { "12": 0, "24": 0, "72": 0 };
  const any: Record<string, boolean> = {
    "12": false,
    "24": false,
    "72": false,
  };
  for (const r of rows) {
    const plat = String(r.platform ?? "other");
    if (plat === "other") continue;
    platforms[plat] = emptyHours();
    for (const [h, suffix] of [
      ["12", "_12h"],
      ["24", "_24h"],
      ["72", "_72h"],
    ] as const) {
      const v = num(r[`${prefix}${suffix}`]);
      platforms[plat][h] = v;
      if (v != null) {
        sums[h] += v;
        any[h] = true;
      }
    }
  }
  for (const h of ["12", "24", "72"] as const) {
    bh[h] = any[h] ? sums[h] : null;
  }
  return { byHours: bh, platforms };
}

function pivotPlatformSeries(
  rows: Record<string, unknown>[],
  valueKey: string,
  opts: {
    bucketMinutes?: number;
    windowHours?: number;
    /** When false (query rejected), skip zero-fill so a failed query
     *  doesn't produce a synthetic all-zero trend. */
    queryOk?: boolean;
  } = {},
): SeriesPoint[] {
  const bm = opts.bucketMinutes ?? 10;
  const wh = opts.windowHours ?? 72;
  const queryOk = opts.queryOk ?? true;
  const byT = new Map<number, SeriesPoint>();
  for (const r of rows) {
    const t = bucketTs(r.bucket ?? r.t);
    if (t == null) continue;
    const plat = String(r.platform ?? "other");
    const v = num(r[valueKey] ?? r.active) ?? 0;
    const cur = byT.get(t) || {
      t,
      total: 0,
      macos: 0,
      windows: 0,
      ios: 0,
      android: 0,
    };
    if (
      plat === "macos" ||
      plat === "windows" ||
      plat === "ios" ||
      plat === "android"
    ) {
      cur[plat] = (Number(cur[plat]) || 0) + v;
    }
    if (plat !== "other") {
      cur.total = (Number(cur.total) || 0) + v;
    }
    byT.set(t, cur);
  }

  // Zero-fill missing completed 10-minute buckets so charts don't connect
  // across quiet periods or present a stale bucket as the latest point.
  // Only fill when the query actually succeeded — otherwise a failed trend
  // query produces a misleading synthetic all-zero series.
  if (queryOk) {
    const nowSec = Date.now() / 1000;
    const bucketSec = bm * 60;
    const lastCompleted =
      Math.floor(nowSec / bucketSec) * bucketSec - bucketSec;
    const firstBucket = lastCompleted - wh * 3600;
    for (let t = firstBucket; t <= lastCompleted; t += bucketSec) {
      if (!byT.has(t)) {
        byT.set(t, { t, total: 0, macos: 0, windows: 0, ios: 0, android: 0 });
      }
    }
  }

  return Array.from(byT.values()).sort((a, b) => a.t - b.t);
}

export async function buildTvSnapshot(opts: {
  includeRevenue: boolean;
}): Promise<TvSnapshot> {
  const cacheKey = `tv-snapshot:v6:rev=${opts.includeRevenue ? 1 : 0}`;
  const cached = await getPayload<TvSnapshot>(cacheKey);
  if (cached?.data && Date.now() - cached.freshAt < 2 * 60 * 1000) {
    return cached.data;
  }

  const warnings: string[] = [];
  let revenue: TvSnapshot["revenue"] = null;
  let stripeOk = false;

  // Kick off Stripe early so a slow enumeration doesn't block PostHog.
  const stripeP = opts.includeRevenue
    ? computeRevenue()
        .then((rev) => {
          stripeOk = !rev.unavailable;
          const byProduct = (rev.byProduct || []).map(
            (p: {
              productName: string;
              mrr: number;
              subscriptionCount: number;
            }) => ({
              name: p.productName,
              arr: (p.mrr || 0) * 12,
              subscriptions: p.subscriptionCount || 0,
            }),
          );
          revenue = {
            mrr: rev.unavailable ? null : rev.mrr,
            arr: rev.unavailable ? null : rev.arr,
            subscriptionCount: rev.unavailable
              ? null
              : byProduct.reduce((a, p) => a + p.subscriptions, 0),
            byProduct,
            unavailable: !!rev.unavailable,
          };
          if (rev.partial) warnings.push("stripe: partial");
          if (rev.unavailable) warnings.push("stripe: unavailable");
        })
        .catch((e) => {
          warnings.push(
            `stripe: ${e instanceof Error ? e.message : String(e)}`,
          );
          revenue = {
            mrr: null,
            arr: null,
            subscriptionCount: null,
            byProduct: [],
            unavailable: true,
          };
        })
    : Promise.resolve();

  const emptyFeat = (): FeatBoard => ({
    byHours: emptyHours(),
    platforms: {},
    series: [],
  });

  let posthogOk = false;
  let activity: TvSnapshot["activity"] = {
    byHours: {
      "12": { total: null, platforms: {} },
      "24": { total: null, platforms: {} },
      "72": { total: null, platforms: {} },
    },
    wau: null,
    series: [],
  };
  let features: TvSnapshot["features"] = {
    conversation: emptyFeat(),
    chat: emptyFeat(),
    memories: emptyFeat(),
  };
  let million = daysUntilMillion(null, []);

  const creds = posthogCreds();
  if (!creds) {
    warnings.push("posthog: POSTHOG_PERSONAL_API_KEY / PROJECT_ID missing");
  } else {
    const bm = 10;
    const wh = 72;
    const lim = Math.ceil((wh * 60) / bm) + 5;

    // Exclude the currently open 10m bucket so charts don't dip on a partial window.
    const bucketCut = `toStartOfInterval(now(), INTERVAL ${bm} MINUTE)`;

    // Use COALESCE(person_id, distinct_id) to count events whose person_id hasn't
    // been materialized yet, matching established PostHog routes in this package.
    const actorExpr = "COALESCE(person_id, distinct_id)";

    const qActivityPlat = `
SELECT
  ${PLATFORM_EXPR} AS platform,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 12 HOUR) AS dau_12h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 24 HOUR) AS dau_24h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 72 HOUR) AS dau_72h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 7 DAY) AS wau
FROM events
WHERE timestamp >= now() - INTERVAL 7 DAY AND timestamp < now()
  AND event IN ${CORE_EVENTS}
GROUP BY platform
ORDER BY dau_72h DESC
LIMIT 10`.trim();

    // Global uniques (not sum of platforms — multi-platform people counted once).
    const qActivityTotals = `
SELECT
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 12 HOUR) AS dau_12h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 24 HOUR) AS dau_24h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 72 HOUR) AS dau_72h,
  uniqIf(${actorExpr}, timestamp >= now() - INTERVAL 7 DAY) AS wau
FROM events
WHERE timestamp >= now() - INTERVAL 7 DAY AND timestamp < now()
  AND event IN ${CORE_EVENTS}
LIMIT 1`.trim();

    const qActivity10m = `
SELECT
  toStartOfInterval(timestamp, INTERVAL ${bm} MINUTE) AS bucket,
  ${PLATFORM_EXPR} AS platform,
  uniq(${actorExpr}) AS active
FROM events
WHERE timestamp >= now() - INTERVAL ${wh} HOUR
  AND timestamp < ${bucketCut}
  AND event IN ${CORE_EVENTS}
GROUP BY bucket, platform
ORDER BY bucket ASC
LIMIT ${lim * 5}`.trim();

    // Conversation = phone/desktop recording start. Chat = message / floating bar query sent.
    // Memories = Memory Extracted volume only (Memory Created is a historical conversation alias).
    const qFeaturesPlat = `
SELECT
  ${PLATFORM_EXPR} AS platform,
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 12 HOUR) AS conversation_users_12h,
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 24 HOUR) AS conversation_users_24h,
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 72 HOUR) AS conversation_users_72h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 12 HOUR) AS chat_users_12h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 24 HOUR) AS chat_users_24h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 72 HOUR) AS chat_users_72h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 12 HOUR) AS memory_events_12h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 24 HOUR) AS memory_events_24h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 72 HOUR) AS memory_events_72h
FROM events
WHERE timestamp >= now() - INTERVAL 72 HOUR AND timestamp < now()
  AND (
    ${CONV_EVENT} OR ${CHAT_EVENTS} OR ${MEMORY_EVENTS}
  )
GROUP BY platform
LIMIT 10`.trim();

    const qFeaturesTotals = `
SELECT
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 12 HOUR) AS conversation_users_12h,
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 24 HOUR) AS conversation_users_24h,
  uniqIf(${actorExpr}, ${CONV_EVENT} AND timestamp >= now() - INTERVAL 72 HOUR) AS conversation_users_72h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 12 HOUR) AS chat_users_12h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 24 HOUR) AS chat_users_24h,
  uniqIf(${actorExpr}, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 72 HOUR) AS chat_users_72h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 12 HOUR) AS memory_events_12h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 24 HOUR) AS memory_events_24h,
  countIf(${MEMORY_EVENTS} AND timestamp >= now() - INTERVAL 72 HOUR) AS memory_events_72h
FROM events
WHERE timestamp >= now() - INTERVAL 72 HOUR AND timestamp < now()
  AND (
    ${CONV_EVENT} OR ${CHAT_EVENTS} OR ${MEMORY_EVENTS}
  )
LIMIT 1`.trim();

    const qFeatures10m = `
SELECT
  toStartOfInterval(timestamp, INTERVAL ${bm} MINUTE) AS bucket,
  ${PLATFORM_EXPR} AS platform,
  uniqIf(${actorExpr}, ${CONV_EVENT}) AS conversation_users,
  uniqIf(${actorExpr}, ${CHAT_EVENTS}) AS chat_users,
  countIf(${MEMORY_EVENTS}) AS memory_events
FROM events
WHERE timestamp >= now() - INTERVAL ${wh} HOUR
  AND timestamp < ${bucketCut}
  AND (
    ${CONV_EVENT} OR ${CHAT_EVENTS} OR ${MEMORY_EVENTS}
  )
GROUP BY bucket, platform
ORDER BY bucket ASC
LIMIT ${lim * 5}`.trim();

    const qPersonsTotal = `SELECT count() AS total_users FROM persons LIMIT 1`;
    const qPersonsDaily = `
SELECT toDate(created_at) AS day, count() AS new_users
FROM persons
WHERE created_at >= now() - INTERVAL 30 DAY AND created_at < toStartOfDay(now())
GROUP BY day ORDER BY day ASC LIMIT 40`.trim();

    const results = await Promise.allSettled([
      ph(creds, qActivityPlat),
      ph(creds, qActivity10m),
      ph(creds, qFeaturesPlat),
      ph(creds, qFeatures10m),
      ph(creds, qPersonsTotal),
      ph(creds, qPersonsDaily),
      ph(creds, qActivityTotals),
      ph(creds, qFeaturesTotals),
    ]);

    const labels = [
      "activity_plat",
      "activity_10m",
      "features_plat",
      "features_10m",
      "persons_total",
      "persons_daily",
      "activity_totals",
      "features_totals",
    ];
    results.forEach((r, i) => {
      if (r.status === "rejected") warnings.push(`${labels[i]}: ${r.reason}`);
    });

    const get = (i: number) =>
      results[i].status === "fulfilled"
        ? (results[i] as PromiseFulfilledResult<unknown[]>).value
        : [];

    const actPlat = asRows(get(0), [
      "platform",
      "dau_12h",
      "dau_24h",
      "dau_72h",
      "wau",
    ]);
    const actTotals =
      asRows(get(6), ["dau_12h", "dau_24h", "dau_72h", "wau"])[0] || {};
    const byHours: TvSnapshot["activity"]["byHours"] = {
      "12": { total: num(actTotals.dau_12h), platforms: {} },
      "24": { total: num(actTotals.dau_24h), platforms: {} },
      "72": { total: num(actTotals.dau_72h), platforms: {} },
    };
    for (const r of actPlat) {
      const plat = String(r.platform ?? "other");
      if (plat === "other") continue;
      const d12 = num(r.dau_12h);
      const d24 = num(r.dau_24h);
      const d72 = num(r.dau_72h);
      if (d12 != null) byHours["12"].platforms[plat] = d12;
      if (d24 != null) byHours["24"].platforms[plat] = d24;
      if (d72 != null) byHours["72"].platforms[plat] = d72;
    }
    const wau = num(actTotals.wau);

    const actSeries = pivotPlatformSeries(
      asRows(get(1), ["bucket", "platform", "active"]),
      "active",
      { queryOk: results[1].status === "fulfilled" },
    );

    const featPlat = asRows(get(2), [
      "platform",
      "conversation_users_12h",
      "conversation_users_24h",
      "conversation_users_72h",
      "chat_users_12h",
      "chat_users_24h",
      "chat_users_72h",
      "memory_events_12h",
      "memory_events_24h",
      "memory_events_72h",
    ]);
    const featTotals =
      asRows(get(7), [
        "conversation_users_12h",
        "conversation_users_24h",
        "conversation_users_72h",
        "chat_users_12h",
        "chat_users_24h",
        "chat_users_72h",
        "memory_events_12h",
        "memory_events_24h",
        "memory_events_72h",
      ])[0] || {};
    const convH = buildFeatHours(featPlat, "conversation_users");
    const chatH = buildFeatHours(featPlat, "chat_users");
    const memH = buildFeatHours(featPlat, "memory_events");
    // If the global totals query failed, platform-summed values could
    // double-count multi-platform users, so null the headline totals.
    const featTotalsOk = results[7].status === "fulfilled";
    for (const [board, prefix] of [
      [convH, "conversation_users"],
      [chatH, "chat_users"],
      [memH, "memory_events"],
    ] as const) {
      for (const h of ["12", "24", "72"] as const) {
        const v = num(featTotals[`${prefix}_${h}h`]);
        if (v != null) {
          board.byHours[h] = v;
        } else if (!featTotalsOk) {
          board.byHours[h] = null;
        }
      }
    }

    const feat10m = asRows(get(3), [
      "bucket",
      "platform",
      "conversation_users",
      "chat_users",
      "memory_events",
    ]);
    const feat10mOk = results[3].status === "fulfilled";
    const convSeries = pivotPlatformSeries(feat10m, "conversation_users", {
      queryOk: feat10mOk,
    });
    const chatSeries = pivotPlatformSeries(feat10m, "chat_users", {
      queryOk: feat10mOk,
    });
    const memSeries = pivotPlatformSeries(feat10m, "memory_events", {
      queryOk: feat10mOk,
    });

    const totRow = asRows(get(4), ["total_users"])[0] || {};
    const totalUsers = num(totRow.total_users);
    const dailyNew = asRows(get(5), ["day", "new_users"]).map((r) => ({
      day: String(r.day ?? ""),
      newUsers: num(r.new_users) ?? 0,
    }));
    million = daysUntilMillion(totalUsers, dailyNew);

    activity = {
      byHours,
      wau,
      series: actSeries,
    };
    features = {
      conversation: { ...convH, series: convSeries },
      chat: { ...chatH, series: chatSeries },
      memories: { ...memH, series: memSeries },
    };
    // Determine success from settled query status, not from actSeries.length
    // (pivotPlatformSeries zero-fills buckets even when the query rejected).
    // Count any fulfilled query that can populate a visible board.
    posthogOk =
      results[0].status === "fulfilled" ||
      results[1].status === "fulfilled" ||
      results[2].status === "fulfilled" ||
      results[3].status === "fulfilled" ||
      results[4].status === "fulfilled" ||
      results[6].status === "fulfilled" ||
      results[7].status === "fulfilled";
  }

  // Ensure Stripe has settled before evaluating sources / building the
  // snapshot. Without this, a fast PostHog path can reach the source check
  // while stripeOk is still false and revenue is still null, dropping
  // ARR/MRR from otherwise successful responses.
  await stripeP;

  if (!posthogOk && !(opts.includeRevenue && stripeOk)) {
    // Nothing useful to show — fail rather than caching an empty board.
    // Use a sentinel message so the route handler can classify it as 502.
    const detail = warnings[0] || "unknown";
    throw new Error(`No TV metric sources available (${detail})`);
  }

  const snap: TvSnapshot = {
    generatedAt: new Date().toISOString(),
    title: "Omi TV",
    sources: { stripe: stripeOk, posthog: posthogOk },
    partial: warnings.length > 0,
    warnings,
    revenue: opts.includeRevenue ? revenue : null,
    activity,
    features,
    million,
  };

  await setPayload(cacheKey, snap).catch(() => undefined);
  return snap;
}
