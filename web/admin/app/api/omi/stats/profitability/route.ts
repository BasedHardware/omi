import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getOptionalStripe } from "@/lib/stripe";
import { getAdminAuth, getDb } from "@/lib/firebase/admin";
import { getJsonCache, setJsonCache } from "@/lib/redis";
import type Stripe from "stripe";

export const dynamic = "force-dynamic";

// Per-platform profitability metrics.
//
// Platform attribution sources (combined, best-available wins):
//   1. Firestore `fcm_tokens` device_key prefix (`macos_…` → desktop,
//      `ios_…`/`android_…` → mobile). Misses users who never enabled
//      notifications.
//   2. PostHog events where `properties.$os_name = 'macOS'` — desktop users.
//      Already proven by crash-rate / macos-versions / dau-trends routes.
//   3. Mixpanel `$os` in ['iOS','Android'] — mobile users.
//
// Each source provides distinct_id/uid → platform pairs. We merge them so a
// user appears desktop if ANY source tags them as desktop, and mobile if any
// mobile source tags them.
//
// Counts:
//   new users per day per platform: Firebase Auth creationTime bucketed by day
//     and joined with the merged platform map. Users whose platform cannot be
//     determined count as "unknown" and are excluded from chart series.
//   active users per day per platform: taken directly from PostHog + Mixpanel
//     daily unique-user segmentation.
//   revenue: Stripe active subs joined by metadata.uid against the platform
//     map → exact per-platform MRR.
//   cost: active users × per-user infra cost (env / query param configurable).
//   conversion: Stripe new paid subs per day grouped by platform via uid
//     lookup, divided by new users per day per platform.

type Platform = "desktop" | "mobile" | "unknown";
type KnownPlatform = "desktop" | "mobile";

interface DailyPoint {
  date: string;
  desktop: number;
  mobile: number;
  total: number;
}

interface ProfitabilityPayload {
  days: number;
  users: DailyPoint[];
  cumulativeUsers: DailyPoint[];
  activeUsers: DailyPoint[];
  revenue: DailyPoint[];
  cost: DailyPoint[];
  costPerUser: DailyPoint[];
  conversion: DailyPoint[];
  summary: {
    mrr: number;
    mrrDesktop: number;
    mrrMobile: number;
    mrrUnknown: number;
    totalNewDesktop: number;
    totalNewMobile: number;
    totalUsersDesktop: number;
    totalUsersMobile: number;
    totalUsersUnknown: number;
    totalCostUsd: number;
    avgCostPerUserDesktop: number;
    avgCostPerUserMobile: number;
    assumptions: {
      desktopCostPerUser: number;
      mobileCostPerUser: number;
      overheadMonthlyUsd?: number;
      costSource: "real" | "estimated";
    };
    partial: boolean;
    sources: {
      firebaseAuth: boolean;
      firestoreTokens: boolean;
      posthogDesktop: boolean;
      mixpanelMobile: boolean;
      stripeActive: boolean;
      stripeNewPaid: boolean;
      infraCosts: boolean;
    };
  };
  generatedAt: number;
}

const CACHE_PREFIX = "admin:stats:profitability:v6";
const CACHE_TTL_SECONDS = 30 * 60;

// Fallback per-user infra cost when real billing data can't be pulled from
// the infra-costs endpoint. Calibrated against the team's Apr projection
// ($57K/mo ÷ 30 days ÷ ~10K DAU) so numbers are realistic even before the
// collection-group scan finishes.
const DEFAULT_DESKTOP_COST = 0.2;
const DEFAULT_MOBILE_COST = 0.2;

// Name of the origin-relative infra-costs endpoint. Populates the `cost` and
// `costPerUser` series with actual daily LLM spend from Firestore plus a
// platform-proportional share of fixed overhead.
const INFRA_COSTS_PATH = "/api/omi/stats/infra-costs";

function parseCost(raw: string | null, fallback: number): number {
  if (raw == null) return fallback;
  const n = parseFloat(raw);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return n;
}

function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

function formatDate(d: Date): string {
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-${String(d.getUTCDate()).padStart(2, "0")}`;
}

function buildDayKeys(days: number): string[] {
  const out: string[] = [];
  const end = new Date();
  end.setUTCHours(0, 0, 0, 0);
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  for (const d = new Date(start); d <= end; d.setUTCDate(d.getUTCDate() + 1)) {
    out.push(formatDate(d));
  }
  return out;
}

function platformFromDeviceKey(deviceKey: string): Platform {
  const prefix = deviceKey.split("_", 1)[0]?.toLowerCase();
  if (prefix === "macos") return "desktop";
  if (prefix === "ios" || prefix === "android") return "mobile";
  return "unknown";
}

type UserPlatformInfo = {
  platform: KnownPlatform | "unknown";
  hasDesktop: boolean;
  hasMobile: boolean;
};

async function buildUserPlatformMapFromTokens(): Promise<Map<string, { desktop: Date | null; mobile: Date | null }> | null> {
  try {
    const db = getDb();
    const snap = await db.collectionGroup("fcm_tokens").select("created_at").get();
    const perUser = new Map<string, { desktop: Date | null; mobile: Date | null }>();
    for (const doc of snap.docs) {
      const parentUser = doc.ref.parent.parent;
      if (!parentUser) continue;
      const uid = parentUser.id;
      const platform = platformFromDeviceKey(doc.id);
      if (platform === "unknown") continue;
      const raw = doc.get("created_at");
      const createdAt = raw?.toDate ? raw.toDate() : raw ? new Date(raw) : null;
      const existing = perUser.get(uid) ?? { desktop: null, mobile: null };
      if (platform === "desktop") {
        if (!existing.desktop || (createdAt && createdAt < existing.desktop)) existing.desktop = createdAt;
      } else {
        if (!existing.mobile || (createdAt && createdAt < existing.mobile)) existing.mobile = createdAt;
      }
      perUser.set(uid, existing);
    }
    return perUser;
  } catch (err) {
    console.error("Firestore fcm_tokens scan failed:", err);
    return null;
  }
}

// PostHog distinct_ids are typically the Firebase uid (set via identify()).
async function fetchDesktopUidsFromPostHog(days: number): Promise<Set<string> | null> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";
  if (!apiKey || !projectId) return null;

  const query = `
    SELECT DISTINCT distinct_id
    FROM events
    WHERE properties.$os_name = 'macOS'
      AND timestamp >= now() - interval ${Math.max(days, 90)} day
    LIMIT 500000
  `;
  try {
    const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
    });
    if (!response.ok) {
      console.error("PostHog desktop uids failed:", response.status, await response.text());
      return null;
    }
    const raw = await response.json();
    const rows: [string][] = raw?.results ?? [];
    return new Set(rows.map((r) => String(r[0])).filter(Boolean));
  } catch (err) {
    console.error("PostHog desktop uids exception:", err);
    return null;
  }
}

// PostHog — active desktop users per day (unique distinct_ids with any event).
async function fetchDesktopActivePerDay(days: number): Promise<Record<string, number> | null> {
  const apiKey = process.env.POSTHOG_PERSONAL_API_KEY;
  const projectId = process.env.POSTHOG_PROJECT_ID;
  const host = process.env.POSTHOG_HOST || "https://us.posthog.com";
  if (!apiKey || !projectId) return null;

  const query = `
    SELECT toDate(timestamp) as day, count(DISTINCT distinct_id) as users
    FROM events
    WHERE properties.$os_name = 'macOS'
      AND timestamp >= now() - interval ${days} day
    GROUP BY day
    ORDER BY day
  `;
  try {
    const response = await fetch(`${host}/api/projects/${projectId}/query/`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify({ query: { kind: "HogQLQuery", query } }),
    });
    if (!response.ok) return null;
    const raw = await response.json();
    const rows: [string, number][] = raw?.results ?? [];
    const out: Record<string, number> = {};
    for (const [day, count] of rows) out[String(day).slice(0, 10)] = Number(count ?? 0);
    return out;
  } catch (err) {
    console.error("PostHog desktop active exception:", err);
    return null;
  }
}

// Mixpanel segmentation — active mobile users per day via $ae_session.
async function fetchMobileActivePerDay(days: number): Promise<Record<string, number> | null> {
  const secret = process.env.MIXPANEL_SECRET;
  const base = process.env.MIXPANEL_API_BASE || "https://mixpanel.com/api/2.0";
  if (!secret) return null;

  const now = new Date();
  now.setUTCHours(0, 0, 0, 0);
  const from = new Date(now);
  from.setUTCDate(from.getUTCDate() - (days - 1));

  const params = new URLSearchParams({
    event: "$ae_session",
    from_date: formatDate(from),
    to_date: formatDate(now),
    unit: "day",
    type: "unique",
    on: 'properties["$os"]',
  });

  try {
    const auth = Buffer.from(`${secret}:`).toString("base64");
    const response = await fetch(`${base.replace(/\/$/, "")}/segmentation?${params.toString()}`, {
      headers: { Authorization: `Basic ${auth}`, Accept: "application/json" },
    });
    if (!response.ok) return null;
    const raw = await response.json();
    if (raw?.error) return null;
    const values: Record<string, Record<string, number>> = raw?.data?.values ?? {};
    const out: Record<string, number> = {};
    for (const [os, daily] of Object.entries(values)) {
      const lower = os.toLowerCase();
      if (lower !== "ios" && lower !== "android" && lower !== "iphone os") continue;
      for (const [day, count] of Object.entries(daily)) {
        const key = String(day).slice(0, 10);
        out[key] = (out[key] ?? 0) + Number(count ?? 0);
      }
    }
    return out;
  } catch (err) {
    console.error("Mixpanel mobile active exception:", err);
    return null;
  }
}

// Mixpanel JQL-like alternative: engage with $os filter. Simpler: use
// segmentation over `$ae_session` grouped by $os, then for each known OS
// collect user count. But segmentation doesn't yield UIDs. Instead, we query
// engage with a where clause filtering on $os.
async function fetchMobileUidsFromMixpanel(): Promise<Set<string> | null> {
  const secret = process.env.MIXPANEL_SECRET;
  const base = process.env.MIXPANEL_API_BASE || "https://mixpanel.com/api/2.0";
  if (!secret) return null;

  const uids = new Set<string>();
  try {
    const auth = Buffer.from(`${secret}:`).toString("base64");
    let sessionId: string | undefined;
    let page = 0;
    for (let i = 0; i < 200; i++) {
      const params = new URLSearchParams({
        where: 'properties["$os"] in ["iOS","Android"]',
      });
      if (sessionId) params.set("session_id", sessionId);
      if (sessionId) params.set("page", String(page));
      const response = await fetch(`${base.replace(/\/$/, "")}/engage?${params.toString()}`, {
        method: "POST",
        headers: { Authorization: `Basic ${auth}`, Accept: "application/json" },
      });
      if (!response.ok) {
        console.error("Mixpanel engage failed:", response.status);
        break;
      }
      const raw = await response.json();
      const results: { $distinct_id: string }[] = raw?.results ?? [];
      for (const r of results) if (r?.$distinct_id) uids.add(r.$distinct_id);
      if (!raw?.session_id || !raw?.page_size || results.length < raw.page_size) break;
      sessionId = raw.session_id;
      page = (raw.page ?? 0) + 1;
    }
    return uids;
  } catch (err) {
    console.error("Mixpanel engage exception:", err);
    return null;
  }
}

function mergeUserPlatforms(
  tokens: Map<string, { desktop: Date | null; mobile: Date | null }> | null,
  posthogDesktopUids: Set<string> | null,
  mixpanelMobileUids: Set<string> | null,
): Map<string, UserPlatformInfo> {
  const result = new Map<string, UserPlatformInfo>();

  const addHas = (uid: string, platform: KnownPlatform) => {
    const cur = result.get(uid) ?? { platform: "unknown" as KnownPlatform | "unknown", hasDesktop: false, hasMobile: false };
    if (platform === "desktop") cur.hasDesktop = true;
    if (platform === "mobile") cur.hasMobile = true;
    result.set(uid, cur);
  };

  if (tokens) {
    for (const [uid, dates] of Array.from(tokens.entries())) {
      if (dates.desktop) addHas(uid, "desktop");
      if (dates.mobile) addHas(uid, "mobile");
    }
  }
  if (posthogDesktopUids) for (const uid of Array.from(posthogDesktopUids)) addHas(uid, "desktop");
  if (mixpanelMobileUids) for (const uid of Array.from(mixpanelMobileUids)) addHas(uid, "mobile");

  // Resolve primary platform: prefer earliest token date when both. Otherwise
  // desktop wins if only desktop signal, mobile wins if only mobile signal.
  for (const [uid, info] of Array.from(result.entries())) {
    const tokenDates = tokens?.get(uid);
    if (info.hasDesktop && info.hasMobile) {
      if (tokenDates?.desktop && tokenDates?.mobile) {
        info.platform = tokenDates.desktop < tokenDates.mobile ? "desktop" : "mobile";
      } else {
        info.platform = "mobile"; // tie-break: mobile is the more common primary
      }
    } else if (info.hasDesktop) {
      info.platform = "desktop";
    } else if (info.hasMobile) {
      info.platform = "mobile";
    }
    result.set(uid, info);
  }

  return result;
}

interface AuthSignup {
  uid: string;
  createdAt: Date;
}

async function listAllAuthSignups(): Promise<AuthSignup[] | null> {
  try {
    const auth = getAdminAuth();
    const out: AuthSignup[] = [];
    let pageToken: string | undefined;
    do {
      const page = await auth.listUsers(1000, pageToken);
      for (const user of page.users) {
        const raw = user.metadata?.creationTime;
        if (!raw) continue;
        const ts = new Date(raw);
        if (Number.isNaN(ts.getTime())) continue;
        out.push({ uid: user.uid, createdAt: ts });
      }
      pageToken = page.pageToken || undefined;
      await new Promise((r) => setImmediate(r));
    } while (pageToken);
    return out;
  } catch (err) {
    console.error("Firebase Auth listUsers failed:", err);
    return null;
  }
}

interface InfraCostsSnapshot {
  daily: { date: string; desktop: number; mobile: number; unknown: number; total: number }[];
  overheadMonthlyUsd: number;
}

// Internal fetch against the `/api/omi/stats/infra-costs` endpoint so we reuse
// its caching + collection group scan. Sends the incoming admin auth cookie /
// Authorization header so the call is authenticated at the proxy layer.
async function fetchInfraCosts(request: NextRequest, days: number): Promise<InfraCostsSnapshot | null> {
  try {
    const url = new URL(INFRA_COSTS_PATH, request.nextUrl.origin);
    url.searchParams.set("days", String(days));
    const authHeader = request.headers.get("authorization");
    const response = await fetch(url, {
      headers: {
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
      // Next's internal fetch honors cookies; infer by forwarding.
      cache: "no-store",
    });
    if (!response.ok) {
      console.warn("Infra costs fetch returned", response.status);
      return null;
    }
    const raw = await response.json();
    if (!raw?.daily) return null;
    return { daily: raw.daily, overheadMonthlyUsd: raw?.summary?.assumptions?.overheadMonthlyUsd };
  } catch (err) {
    console.error("Infra costs fetch exception:", err);
    return null;
  }
}

interface StripeSnapshot {
  mrrByPlatform: Record<Platform, number>;
  newPaidByDayByPlatform: Record<Platform, Record<string, number>>;
  // For each currently-active subscription: its creation date and monthly
  // revenue contribution, attributed to a platform via metadata.uid. Used to
  // build the cumulative MRR curve day-by-day.
  activeSubs: { createdAt: number; monthlyMrr: number; platform: Platform }[];
  partial: boolean;
}

async function fetchStripeSnapshot(
  days: number,
  userPlatforms: Map<string, UserPlatformInfo>,
): Promise<StripeSnapshot | null> {
  const stripe = getOptionalStripe();
  const monthlyPriceId = process.env.STRIPE_UNLIMITED_MONTHLY_PRICE_ID;
  const annualPriceId = process.env.STRIPE_UNLIMITED_ANNUAL_PRICE_ID;
  if (!stripe || !monthlyPriceId || !annualPriceId) return null;

  const mrrByPlatform: Record<Platform, number> = { desktop: 0, mobile: 0, unknown: 0 };
  const newPaidByDayByPlatform: Record<Platform, Record<string, number>> = {
    desktop: {}, mobile: {}, unknown: {},
  };
  const activeSubs: StripeSnapshot['activeSubs'] = [];

  const now = Math.floor(Date.now() / 1000);
  const windowStart = now - (days + 1) * 24 * 60 * 60;

  const lookupPlatform = (uid: string | null | undefined): Platform => {
    if (!uid) return "unknown";
    return userPlatforms.get(uid)?.platform ?? "unknown";
  };

  const results = await Promise.allSettled([
    (async () => {
      for (const priceId of [monthlyPriceId, annualPriceId]) {
        const monthlyDivider = priceId === annualPriceId ? 12 : 1;
        let startingAfter: string | undefined;
        for (;;) {
          const page: Stripe.ApiList<Stripe.Subscription> = await stripe.subscriptions.list({
            status: "active",
            price: priceId,
            limit: 100,
            expand: ["data.items.data.price"],
            ...(startingAfter ? { starting_after: startingAfter } : {}),
          });
          for (const sub of page.data) {
            const uid = sub.metadata?.uid;
            const platform = lookupPlatform(uid);
            let amount = 0;
            for (const item of sub.items.data) {
              const price = typeof item.price === "string" ? null : item.price;
              if (!price) continue;
              amount += ((price.unit_amount || 0) * (item.quantity || 1)) / 100;
            }
            const monthlyMrr = amount / monthlyDivider;
            mrrByPlatform[platform] += monthlyMrr;
            if (sub.created) {
              activeSubs.push({ createdAt: sub.created, monthlyMrr, platform });
            }
          }
          if (!page.has_more || page.data.length === 0) break;
          startingAfter = page.data[page.data.length - 1].id;
        }
      }
    })(),
    (async () => {
      for (const priceId of [monthlyPriceId, annualPriceId]) {
        let startingAfter: string | undefined;
        for (;;) {
          const page = await stripe.subscriptions.list({
            price: priceId,
            status: "all",
            limit: 100,
            created: { gte: windowStart },
            ...(startingAfter ? { starting_after: startingAfter } : {}),
          });
          for (const sub of page.data) {
            if (!sub.created) continue;
            const day = formatDate(new Date(sub.created * 1000));
            const uid = sub.metadata?.uid;
            const platform = lookupPlatform(uid);
            const bucket = newPaidByDayByPlatform[platform];
            bucket[day] = (bucket[day] ?? 0) + 1;
          }
          if (!page.has_more || page.data.length === 0) break;
          startingAfter = page.data[page.data.length - 1].id;
        }
      }
    })(),
  ]);

  const partial = results.some((r) => r.status === "rejected");
  if (partial) {
    for (const r of results) if (r.status === "rejected") console.error("Stripe snapshot partial:", r.reason);
  }

  return { mrrByPlatform, newPaidByDayByPlatform, activeSubs, partial };
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const days = Math.min(Math.max(parseInt(searchParams.get("days") || "30", 10), 7), 90);
    const desktopCost = parseCost(searchParams.get("desktop_cost"), DEFAULT_DESKTOP_COST);
    const mobileCost = parseCost(searchParams.get("mobile_cost"), DEFAULT_MOBILE_COST);

    const cacheKey = `${CACHE_PREFIX}:${days}:${desktopCost}:${mobileCost}`;
    const cached = await getJsonCache<ProfitabilityPayload>(cacheKey);
    if (cached && Date.now() - cached.generatedAt < CACHE_TTL_SECONDS * 1000) {
      return NextResponse.json(cached);
    }

    const [tokensRes, signupsRes, desktopUidsRes, mobileUidsRes, desktopActiveRes, mobileActiveRes, infraRes] = await Promise.allSettled([
      buildUserPlatformMapFromTokens(),
      listAllAuthSignups(),
      fetchDesktopUidsFromPostHog(days),
      fetchMobileUidsFromMixpanel(),
      fetchDesktopActivePerDay(days),
      fetchMobileActivePerDay(days),
      fetchInfraCosts(request, days),
    ]);

    const tokens = tokensRes.status === "fulfilled" ? tokensRes.value : null;
    const signups = signupsRes.status === "fulfilled" ? signupsRes.value : null;
    const desktopUids = desktopUidsRes.status === "fulfilled" ? desktopUidsRes.value : null;
    const mobileUids = mobileUidsRes.status === "fulfilled" ? mobileUidsRes.value : null;
    const desktopActive = desktopActiveRes.status === "fulfilled" ? desktopActiveRes.value : null;
    const mobileActive = mobileActiveRes.status === "fulfilled" ? mobileActiveRes.value : null;
    const infraCosts = infraRes.status === "fulfilled" ? infraRes.value : null;

    const userPlatforms = mergeUserPlatforms(tokens, desktopUids, mobileUids);

    const stripeRes = await fetchStripeSnapshot(days, userPlatforms).catch((e) => {
      console.error("Stripe snapshot threw:", e);
      return null;
    });

    if (
      tokens == null &&
      signups == null &&
      desktopUids == null &&
      mobileUids == null &&
      desktopActive == null &&
      mobileActive == null &&
      stripeRes == null
    ) {
      return NextResponse.json(
        { error: "All profitability data sources failed" },
        { status: 502 },
      );
    }

    const dateKeys = buildDayKeys(days);

    const signupsByDay: Record<string, { desktop: number; mobile: number }> = {};
    let totalUsersDesktop = 0;
    let totalUsersMobile = 0;
    let totalUsersUnknown = 0;
    const cumulativeTotals = { desktop: 0, mobile: 0 };

    const sortedSignups = (signups ?? []).slice().sort(
      (a, b) => a.createdAt.getTime() - b.createdAt.getTime(),
    );
    const windowStartKey = dateKeys[0];
    for (const { uid, createdAt } of sortedSignups) {
      const info = userPlatforms.get(uid);
      const platform = info?.platform ?? "unknown";
      if (platform === "desktop") { totalUsersDesktop += 1; cumulativeTotals.desktop += 1; }
      else if (platform === "mobile") { totalUsersMobile += 1; cumulativeTotals.mobile += 1; }
      else totalUsersUnknown += 1;

      const day = formatDate(new Date(Date.UTC(
        createdAt.getUTCFullYear(),
        createdAt.getUTCMonth(),
        createdAt.getUTCDate(),
      )));
      if (day >= windowStartKey && platform !== "unknown") {
        const bucket = signupsByDay[day] ?? { desktop: 0, mobile: 0 };
        bucket[platform] += 1;
        signupsByDay[day] = bucket;
      }
    }

    const users: DailyPoint[] = dateKeys.map((date) => {
      const row = signupsByDay[date] ?? { desktop: 0, mobile: 0 };
      return { date, desktop: row.desktop, mobile: row.mobile, total: row.desktop + row.mobile };
    });

    let runningDesktop = cumulativeTotals.desktop - users.reduce((s, u) => s + u.desktop, 0);
    let runningMobile = cumulativeTotals.mobile - users.reduce((s, u) => s + u.mobile, 0);
    const cumulativeUsers: DailyPoint[] = users.map((row) => {
      runningDesktop += row.desktop;
      runningMobile += row.mobile;
      return { date: row.date, desktop: runningDesktop, mobile: runningMobile, total: runningDesktop + runningMobile };
    });

    const activeUsers: DailyPoint[] = dateKeys.map((date) => {
      const d = Number(desktopActive?.[date] ?? 0);
      const m = Number(mobileActive?.[date] ?? 0);
      return { date, desktop: d, mobile: m, total: d + m };
    });

    const mrrByPlatform = stripeRes?.mrrByPlatform ?? { desktop: 0, mobile: 0, unknown: 0 };
    const mrr = mrrByPlatform.desktop + mrrByPlatform.mobile + mrrByPlatform.unknown;

    // Cumulative MRR per platform, day by day. For each day in the window we
    // sum the monthly MRR of every active subscription that was created on or
    // before that day. This reflects actual revenue growth instead of a flat
    // proportional split. Subs with an unresolved `unknown` platform are
    // attributed to whichever platform has the larger share of known revenue
    // so the stacked chart still ends at the live MRR total.
    const subs = stripeRes?.activeSubs ?? [];
    const knownMrrTotal = mrrByPlatform.desktop + mrrByPlatform.mobile;
    const desktopShare = knownMrrTotal > 0 ? mrrByPlatform.desktop / knownMrrTotal : 0.5;
    const mobileShare = knownMrrTotal > 0 ? mrrByPlatform.mobile / knownMrrTotal : 0.5;
    const sortedSubs = subs.slice().sort((a, b) => a.createdAt - b.createdAt);
    let subIdx = 0;
    let cumulativeDesktop = 0;
    let cumulativeMobile = 0;
    const revenue: DailyPoint[] = dateKeys.map((date) => {
      const endOfDay = Date.parse(`${date}T23:59:59Z`) / 1000;
      while (subIdx < sortedSubs.length && sortedSubs[subIdx].createdAt <= endOfDay) {
        const s = sortedSubs[subIdx];
        if (s.platform === "desktop") cumulativeDesktop += s.monthlyMrr;
        else if (s.platform === "mobile") cumulativeMobile += s.monthlyMrr;
        else {
          cumulativeDesktop += s.monthlyMrr * desktopShare;
          cumulativeMobile += s.monthlyMrr * mobileShare;
        }
        subIdx += 1;
      }
      const d = round2(cumulativeDesktop);
      const m = round2(cumulativeMobile);
      return { date, desktop: d, mobile: m, total: round2(d + m) };
    });

    // Prefer real cost from infra-costs endpoint (Firestore llm_usage buckets
    // + configurable monthly overhead). Fallback to active-users × per-user
    // assumption when the endpoint didn't return data.
    const infraByDate: Record<string, { desktop: number; mobile: number; total: number }> = {};
    if (infraCosts?.daily) {
      for (const row of infraCosts.daily) {
        infraByDate[row.date] = { desktop: row.desktop, mobile: row.mobile, total: row.total };
      }
    }

    const cost: DailyPoint[] = dateKeys.map((date, idx) => {
      const real = infraByDate[date];
      if (real) {
        return { date, desktop: round2(real.desktop), mobile: round2(real.mobile), total: round2(real.total) };
      }
      const row = activeUsers[idx];
      const d = round2(row.desktop * desktopCost);
      const m = round2(row.mobile * mobileCost);
      return { date, desktop: d, mobile: m, total: round2(d + m) };
    });

    // Cost PER USER = total platform cost / platform active users for that
    // day. Falls back to the configured assumption when active users is 0 or
    // real cost is unavailable.
    const costPerUser: DailyPoint[] = dateKeys.map((date, idx) => {
      const active = activeUsers[idx];
      const costRow = cost[idx];
      const desktopRate =
        active.desktop > 0
          ? round2(costRow.desktop / active.desktop)
          : round2(desktopCost);
      const mobileRate =
        active.mobile > 0
          ? round2(costRow.mobile / active.mobile)
          : round2(mobileCost);
      const blendedTotal =
        active.total > 0
          ? round2(costRow.total / active.total)
          : round2((desktopCost + mobileCost) / 2);
      return { date, desktop: desktopRate, mobile: mobileRate, total: blendedTotal };
    });

    const totalCostUsd = cost.reduce((s, c) => s + c.total, 0);
    const desktopActiveSum = activeUsers.reduce((s, a) => s + a.desktop, 0);
    const mobileActiveSum = activeUsers.reduce((s, a) => s + a.mobile, 0);
    const desktopCostSum = cost.reduce((s, c) => s + c.desktop, 0);
    const mobileCostSum = cost.reduce((s, c) => s + c.mobile, 0);
    const avgCostPerUserDesktop =
      desktopActiveSum > 0 ? round2(desktopCostSum / desktopActiveSum) : round2(desktopCost);
    const avgCostPerUserMobile =
      mobileActiveSum > 0 ? round2(mobileCostSum / mobileActiveSum) : round2(mobileCost);

    const newPaidByDayByPlatform = stripeRes?.newPaidByDayByPlatform ?? { desktop: {}, mobile: {}, unknown: {} };
    const conversion: DailyPoint[] = dateKeys.map((date, idx) => {
      const newRow = users[idx];
      const dPaid = (newPaidByDayByPlatform.desktop[date] ?? 0);
      const mPaid = (newPaidByDayByPlatform.mobile[date] ?? 0);
      const uPaid = (newPaidByDayByPlatform.unknown[date] ?? 0);
      const dPct = newRow.desktop > 0 ? Math.round((dPaid / newRow.desktop) * 1000) / 10 : 0;
      const mPct = newRow.mobile > 0 ? Math.round((mPaid / newRow.mobile) * 1000) / 10 : 0;
      const tPaid = dPaid + mPaid + uPaid;
      const tPct = newRow.total > 0 ? Math.round((tPaid / newRow.total) * 1000) / 10 : 0;
      return { date, desktop: dPct, mobile: mPct, total: tPct };
    });

    const totalNewDesktop = users.reduce((s, u) => s + u.desktop, 0);
    const totalNewMobile = users.reduce((s, u) => s + u.mobile, 0);

    const partial =
      tokens == null ||
      signups == null ||
      (desktopUids == null && desktopActive == null) ||
      (mobileUids == null && mobileActive == null) ||
      stripeRes == null ||
      (stripeRes?.partial ?? false);

    const payload: ProfitabilityPayload = {
      days,
      users,
      cumulativeUsers,
      activeUsers,
      revenue,
      cost,
      costPerUser,
      conversion,
      summary: {
        mrr,
        mrrDesktop: round2(mrrByPlatform.desktop),
        mrrMobile: round2(mrrByPlatform.mobile),
        mrrUnknown: round2(mrrByPlatform.unknown),
        totalNewDesktop,
        totalNewMobile,
        totalUsersDesktop,
        totalUsersMobile,
        totalUsersUnknown,
        totalCostUsd: round2(totalCostUsd),
        avgCostPerUserDesktop,
        avgCostPerUserMobile,
        assumptions: {
          desktopCostPerUser: desktopCost,
          mobileCostPerUser: mobileCost,
          overheadMonthlyUsd: infraCosts?.overheadMonthlyUsd,
          costSource: infraCosts != null ? "real" : "estimated",
        },
        partial,
        sources: {
          firebaseAuth: signups != null,
          firestoreTokens: tokens != null,
          posthogDesktop: desktopUids != null || desktopActive != null,
          mixpanelMobile: mobileUids != null || mobileActive != null,
          stripeActive: stripeRes != null,
          stripeNewPaid: stripeRes != null,
          infraCosts: infraCosts != null,
        },
      },
      generatedAt: Date.now(),
    };

    await setJsonCache(cacheKey, payload, CACHE_TTL_SECONDS);
    return NextResponse.json(payload);
  } catch (err: any) {
    console.error("Profitability stats error:", err);
    return NextResponse.json(
      { error: err?.message || "Failed to compute profitability metrics" },
      { status: 500 },
    );
  }
}
