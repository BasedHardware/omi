/**
 * TV dashboard snapshot — product metrics shaped like omi-tv-metrics prototype.
 * PostHog via posthogResults + Stripe via computeRevenue. No Prometheus / no M1.
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
  'Phone Mic Recording Started','Action Items Page Opened','Action Item Completed',
  'Action Item Manually Added','Action Item Edited','Conversation List Item Clicked',
  'Conversation Detail Opened','Daily Summary Detail Viewed','Rewind Screenshot Viewed',
  'Task Added','Task Completed','Memory Created','Memory Extracted','App Launched'
)`;

const PLATFORM_EXPR = `multiIf(
  properties['$os'] = 'macOS', 'macos',
  properties['$os'] = 'Windows', 'windows',
  properties['$os'] IN ('iOS','iPadOS'), 'ios',
  properties['$os'] = 'Android', 'android',
  'other'
)`;

const HABIT_COND = `event IN (
  'floating_bar_query_sent','Floating Bar Query Sent',
  'floating_bar_ptt_started','Floating Bar PTT Started',
  'Phone Mic Recording Started'
)`;

const CHAT_EVENTS = `event IN ('Chat Message Sent','floating_bar_query_sent','Floating Bar Query Sent')`;

export type PlatformKey = "macos" | "windows" | "ios" | "android";

export type SeriesPoint = {
  t: number; // unix seconds
  total?: number;
  macos?: number;
  windows?: number;
  ios?: number;
  android?: number;
  memories_created?: number;
  v?: number;
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
    byHours: Record<string, { total: number | null; platforms: Record<string, number | null> }>;
    wau: number | null;
    series: SeriesPoint[];
  };
  features: {
    conversation: {
      byHours: Record<string, number | null>;
      platforms: Record<string, Record<string, number | null>>;
      series: SeriesPoint[];
    };
    chat: {
      byHours: Record<string, number | null>;
      platforms: Record<string, Record<string, number | null>>;
      series: SeriesPoint[];
    };
    habit: {
      byHours: Record<string, number | null>;
      platforms: Record<string, Record<string, number | null>>;
      series: SeriesPoint[];
    };
  };
  fun: {
    memoriesByHours: Record<string, number | null>;
    series: SeriesPoint[];
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

  const series: SeriesPoint[] = [];
  if (total != null && rows.length) {
    let running = total;
    const rev: SeriesPoint[] = [];
    for (let i = rows.length - 1; i >= 0; i--) {
      const day = rows[i].day;
      const ts = Date.parse(`${day}T00:00:00Z`) / 1000;
      rev.push({ t: ts, v: Math.round(running), total: Math.round(running) });
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
  };
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

function rowObj(row: unknown): Record<string, unknown> {
  if (Array.isArray(row)) {
    // callers pass column names separately when needed
    return {};
  }
  if (row && typeof row === "object") return row as Record<string, unknown>;
  return {};
}

function asRows(results: unknown[], columns?: string[]): Record<string, unknown>[] {
  if (!results?.length) return [];
  if (Array.isArray(results[0])) {
    const cols = columns || [];
    return (results as unknown[][]).map((r) => {
      const o: Record<string, unknown> = {};
      r.forEach((v, i) => {
        o[cols[i] || String(i)] = v;
      });
      // also keep numeric indices
      r.forEach((v, i) => {
        o[String(i)] = v;
      });
      return o;
    });
  }
  return results.map((r) => rowObj(r));
}

function bucketTs(raw: unknown): number | null {
  if (raw == null) return null;
  if (typeof raw === "number") return raw > 1e12 ? raw / 1000 : raw;
  const n = Date.parse(String(raw));
  return Number.isNaN(n) ? null : n / 1000;
}

function posthogCreds(): { host: string; projectId: string; apiKey: string } | null {
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
  featPlat: Record<string, unknown>[],
  prefix: "conversation_users" | "chat_users" | "habit_users",
): {
  byHours: Record<string, number | null>;
  platforms: Record<string, Record<string, number | null>>;
} {
  const bh = emptyHours();
  const platforms: Record<string, Record<string, number | null>> = {};
  const sums: Record<string, number> = { "12": 0, "24": 0, "72": 0 };
  const any: Record<string, boolean> = { "12": false, "24": false, "72": false };
  for (const r of featPlat) {
    const plat = String(r.platform ?? r[0] ?? "other");
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
): SeriesPoint[] {
  const byT = new Map<number, SeriesPoint>();
  for (const r of rows) {
    const t =
      bucketTs(r.bucket ?? r.t ?? r[0]) ??
      bucketTs(r.day);
    if (t == null) continue;
    const plat = String(r.platform ?? r[1] ?? "other");
    const v =
      num(r[valueKey] ?? r.active ?? r[2] ?? r.users ?? r.conversation_users ?? r.chat_users ?? r.habit_users) ??
      0;
    const cur = byT.get(t) || { t, total: 0, macos: 0, windows: 0, ios: 0, android: 0 };
    if (plat === "macos" || plat === "windows" || plat === "ios" || plat === "android") {
      cur[plat] = (cur[plat] || 0) + v;
    }
    cur.total = (cur.total || 0) + v;
    byT.set(t, cur);
  }
  return Array.from(byT.values()).sort((a, b) => a.t - b.t);
}

export async function buildTvSnapshot(opts: {
  includeRevenue: boolean;
}): Promise<TvSnapshot> {
  const cacheKey = `tv-snapshot:v3:rev=${opts.includeRevenue ? 1 : 0}`;
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
      const byProduct = (rev.byProduct || []).map(
        (p: {
          productId: string;
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
        subscriptionCount: byProduct.reduce((a, p) => a + p.subscriptions, 0),
        byProduct,
        unavailable: !!rev.unavailable,
      };
      if (rev.partial) warnings.push("stripe: partial");
    } catch (e) {
      warnings.push(`stripe: ${e instanceof Error ? e.message : String(e)}`);
      revenue = {
        mrr: null,
        arr: null,
        subscriptionCount: null,
        byProduct: [],
        unavailable: true,
      };
    }
  }

  const emptyActivity: TvSnapshot["activity"] = {
    byHours: {
      "12": { total: null, platforms: {} },
      "24": { total: null, platforms: {} },
      "72": { total: null, platforms: {} },
    },
    wau: null,
    series: [],
  };
  const emptyFeat = {
    byHours: emptyHours(),
    platforms: {} as Record<string, Record<string, number | null>>,
    series: [] as SeriesPoint[],
  };

  let posthogOk = false;
  let activity = emptyActivity;
  let features: TvSnapshot["features"] = {
    conversation: { ...emptyFeat, platforms: {} },
    chat: { ...emptyFeat, platforms: {} },
    habit: { ...emptyFeat, platforms: {} },
  };
  let fun: TvSnapshot["fun"] = {
    memoriesByHours: emptyHours(),
    series: [],
  };
  let million = daysUntilMillion(null, []);

  const creds = posthogCreds();
  if (!creds) {
    warnings.push("posthog: POSTHOG_PERSONAL_API_KEY / PROJECT_ID missing");
  } else {
    const bm = 10;
    const wh = 72;
    const lim = Math.ceil((wh * 60) / bm) + 5;

    const qActivityPlat = `
SELECT
  ${PLATFORM_EXPR} AS platform,
  uniqIf(person_id, timestamp >= now() - INTERVAL 12 HOUR) AS dau_12h,
  uniqIf(person_id, timestamp >= now() - INTERVAL 24 HOUR) AS dau_24h,
  uniqIf(person_id, timestamp >= now() - INTERVAL 72 HOUR) AS dau_72h,
  uniqIf(person_id, timestamp >= now() - INTERVAL 7 DAY) AS wau
FROM events
WHERE timestamp >= now() - INTERVAL 7 DAY AND timestamp < now()
  AND event IN ${CORE_EVENTS}
GROUP BY platform
ORDER BY dau_72h DESC
LIMIT 10`.trim();

    const qActivity10m = `
SELECT
  toStartOfInterval(timestamp, INTERVAL ${bm} MINUTE) AS bucket,
  ${PLATFORM_EXPR} AS platform,
  uniq(person_id) AS active
FROM events
WHERE timestamp >= now() - INTERVAL ${wh} HOUR AND timestamp < now()
  AND event IN ${CORE_EVENTS}
GROUP BY bucket, platform
ORDER BY bucket ASC
LIMIT ${lim * 4}`.trim();

    const qFeaturesPlat = `
SELECT
  ${PLATFORM_EXPR} AS platform,
  uniqIf(person_id, event = 'Phone Mic Recording Started' AND timestamp >= now() - INTERVAL 12 HOUR) AS conversation_users_12h,
  uniqIf(person_id, event = 'Phone Mic Recording Started' AND timestamp >= now() - INTERVAL 24 HOUR) AS conversation_users_24h,
  uniqIf(person_id, event = 'Phone Mic Recording Started' AND timestamp >= now() - INTERVAL 72 HOUR) AS conversation_users_72h,
  uniqIf(person_id, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 12 HOUR) AS chat_users_12h,
  uniqIf(person_id, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 24 HOUR) AS chat_users_24h,
  uniqIf(person_id, ${CHAT_EVENTS} AND timestamp >= now() - INTERVAL 72 HOUR) AS chat_users_72h,
  uniqIf(person_id, ${HABIT_COND} AND timestamp >= now() - INTERVAL 12 HOUR) AS habit_users_12h,
  uniqIf(person_id, ${HABIT_COND} AND timestamp >= now() - INTERVAL 24 HOUR) AS habit_users_24h,
  uniqIf(person_id, ${HABIT_COND} AND timestamp >= now() - INTERVAL 72 HOUR) AS habit_users_72h
FROM events
WHERE timestamp >= now() - INTERVAL 72 HOUR AND timestamp < now()
  AND event IN (
    'Phone Mic Recording Started',
    'Chat Message Sent','floating_bar_query_sent','Floating Bar Query Sent',
    'floating_bar_ptt_started','Floating Bar PTT Started'
  )
GROUP BY platform
LIMIT 10`.trim();

    const qFeatures10m = `
SELECT
  toStartOfInterval(timestamp, INTERVAL ${bm} MINUTE) AS bucket,
  ${PLATFORM_EXPR} AS platform,
  uniqIf(person_id, event = 'Phone Mic Recording Started') AS conversation_users,
  uniqIf(person_id, ${CHAT_EVENTS}) AS chat_users,
  uniqIf(person_id, ${HABIT_COND}) AS habit_users
FROM events
WHERE timestamp >= now() - INTERVAL ${wh} HOUR AND timestamp < now()
  AND event IN (
    'Phone Mic Recording Started',
    'Chat Message Sent','floating_bar_query_sent','Floating Bar Query Sent',
    'floating_bar_ptt_started','Floating Bar PTT Started'
  )
GROUP BY bucket, platform
ORDER BY bucket ASC
LIMIT ${lim * 4}`.trim();

    const qFunHours = `
SELECT
  countIf(event IN ('Memory Created','Memory Extracted') AND timestamp >= now() - INTERVAL 12 HOUR) AS m_12h,
  countIf(event IN ('Memory Created','Memory Extracted') AND timestamp >= now() - INTERVAL 24 HOUR) AS m_24h,
  countIf(event IN ('Memory Created','Memory Extracted') AND timestamp >= now() - INTERVAL 72 HOUR) AS m_72h
FROM events
WHERE timestamp >= now() - INTERVAL 72 HOUR AND timestamp < now()
  AND event IN ('Memory Created','Memory Extracted')
LIMIT 1`.trim();

    const qFun10m = `
SELECT
  toStartOfInterval(timestamp, INTERVAL ${bm} MINUTE) AS bucket,
  countIf(event IN ('Memory Created','Memory Extracted')) AS memories_created
FROM events
WHERE timestamp >= now() - INTERVAL ${wh} HOUR AND timestamp < now()
  AND event IN ('Memory Created','Memory Extracted')
GROUP BY bucket
ORDER BY bucket ASC
LIMIT ${lim}`.trim();

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
      ph(creds, qFunHours),
      ph(creds, qFun10m),
      ph(creds, qPersonsTotal),
      ph(creds, qPersonsDaily),
    ]);

    const labels = [
      "activity_plat",
      "activity_10m",
      "features_plat",
      "features_10m",
      "fun_hours",
      "fun_10m",
      "persons_total",
      "persons_daily",
    ];
    results.forEach((r, i) => {
      if (r.status === "rejected") warnings.push(`${labels[i]}: ${r.reason}`);
    });

    const get = (i: number) =>
      results[i].status === "fulfilled" ? (results[i] as PromiseFulfilledResult<unknown[]>).value : [];

    // Activity by platform hours
    const actPlat = asRows(get(0), [
      "platform",
      "dau_12h",
      "dau_24h",
      "dau_72h",
      "wau",
    ]);
    const byHours: TvSnapshot["activity"]["byHours"] = {
      "12": { total: 0, platforms: {} },
      "24": { total: 0, platforms: {} },
      "72": { total: 0, platforms: {} },
    };
    let wau = 0;
    let wauAny = false;
    for (const r of actPlat) {
      const plat = String(r.platform ?? r[0] ?? "other");
      const d12 = num(r.dau_12h ?? r[1]);
      const d24 = num(r.dau_24h ?? r[2]);
      const d72 = num(r.dau_72h ?? r[3]);
      const w = num(r.wau ?? r[4]);
      if (plat === "other") continue;
      if (d12 != null) {
        byHours["12"].platforms[plat] = d12;
        byHours["12"].total = (byHours["12"].total || 0) + d12;
      }
      if (d24 != null) {
        byHours["24"].platforms[plat] = d24;
        byHours["24"].total = (byHours["24"].total || 0) + d24;
      }
      if (d72 != null) {
        byHours["72"].platforms[plat] = d72;
        byHours["72"].total = (byHours["72"].total || 0) + d72;
      }
      if (w != null) {
        wau += w;
        wauAny = true;
      }
    }
    // null out zeros if nothing
    for (const h of ["12", "24", "72"] as const) {
      if (!Object.keys(byHours[h].platforms).length) byHours[h].total = null;
    }

    const actSeries = pivotPlatformSeries(
      asRows(get(1), ["bucket", "platform", "active"]),
      "active",
    );

    // Features by platform
    const featPlat = asRows(get(2), [
      "platform",
      "conversation_users_12h",
      "conversation_users_24h",
      "conversation_users_72h",
      "chat_users_12h",
      "chat_users_24h",
      "chat_users_72h",
      "habit_users_12h",
      "habit_users_24h",
      "habit_users_72h",
    ]);
    const convH = buildFeatHours(featPlat, "conversation_users");
    const chatH = buildFeatHours(featPlat, "chat_users");
    const habitH = buildFeatHours(featPlat, "habit_users");

    const feat10m = asRows(get(3), [
      "bucket",
      "platform",
      "conversation_users",
      "chat_users",
      "habit_users",
    ]);
    const convSeries = pivotPlatformSeries(feat10m, "conversation_users");
    const chatSeries = pivotPlatformSeries(feat10m, "chat_users");
    const habitSeries = pivotPlatformSeries(feat10m, "habit_users");

    // Fun memories
    const funRow = asRows(get(4), ["m_12h", "m_24h", "m_72h"])[0] || {};
    const memoriesByHours = {
      "12": num(funRow.m_12h ?? funRow[0]),
      "24": num(funRow.m_24h ?? funRow[1]),
      "72": num(funRow.m_72h ?? funRow[2]),
    };
    const fun10m = asRows(get(5), ["bucket", "memories_created"]);
    const funSeries: SeriesPoint[] = fun10m
      .map((r) => {
        const t = bucketTs(r.bucket ?? r[0]);
        const v = num(r.memories_created ?? r[1]) ?? 0;
        return t == null ? null : { t, memories_created: v, v };
      })
      .filter(Boolean) as SeriesPoint[];

    // Million
    const totRow = asRows(get(6), ["total_users"])[0] || {};
    const totalUsers = num(totRow.total_users ?? totRow[0]);
    const dailyNew = asRows(get(7), ["day", "new_users"]).map((r) => ({
      day: String(r.day ?? r[0] ?? ""),
      newUsers: num(r.new_users ?? r[1]) ?? 0,
    }));
    million = daysUntilMillion(totalUsers, dailyNew);

    activity = {
      byHours,
      wau: wauAny ? wau : null,
      series: actSeries,
    };
    features = {
      conversation: { ...convH, series: convSeries },
      chat: { ...chatH, series: chatSeries },
      habit: { ...habitH, series: habitSeries },
    };
    fun = { memoriesByHours, series: funSeries };
    posthogOk =
      actSeries.length > 0 ||
      byHours["72"].total != null ||
      million.totalUsers != null;
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
    fun,
    million,
  };

  await setPayload(cacheKey, snap).catch(() => undefined);
  return snap;
}
