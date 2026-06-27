import { getAdminAuth } from "@/lib/firebase/admin";
import { getJsonCache, setJsonCache } from "@/lib/redis";

// The Firestore `users` collection has a `created_at` field that was
// backfilled for ~63K existing users on a single day in late 2024, so it
// can't be used to derive signup history. Firebase Auth's
// `metadata.creationTime` is set by the Auth service on account creation
// and is the authoritative signup timestamp.

export type DailyPoint = { date: string; users: number; cumulative: number };

export type UserGrowthSeries = {
  data: DailyPoint[];
  totalUsers: number;
  generatedAt: number;
};

export type UserGrowthResponse = {
  data: DailyPoint[];
  totalUsers: number;
  windowUsers: number;
  days: number;
  generatedAt: number;
};

const REDIS_KEY = "admin:stats:daily-new-users:v1";
// Keep the cache durable for 7 days. Anything older still gets served while a
// background rebuild runs — the goal is to never block a request behind a
// full Auth listUsers walk.
const REDIS_TTL_SECONDS = 7 * 24 * 60 * 60;
// A cached value newer than this is considered fresh; older values are still
// returned but trigger a background refresh.
const FRESH_TTL_MS = 30 * 60 * 1000;

let cachedSeries: UserGrowthSeries | null = null;
let pendingBuild: Promise<UserGrowthSeries> | null = null;

async function buildDailySeries(): Promise<UserGrowthSeries> {
  const auth = getAdminAuth();
  const countsByDate: Record<string, number> = {};
  let pageToken: string | undefined = undefined;
  let total = 0;
  let earliest: Date | null = null;
  let latest: Date | null = null;

  do {
    const page = await auth.listUsers(1000, pageToken);
    for (const user of page.users) {
      const rawCt = user.metadata?.creationTime;
      if (!rawCt) continue;
      const ct = new Date(rawCt);
      if (Number.isNaN(ct.getTime())) continue;
      const key = ct.toISOString().slice(0, 10);
      countsByDate[key] = (countsByDate[key] || 0) + 1;
      if (!earliest || ct < earliest) earliest = ct;
      if (!latest || ct > latest) latest = ct;
      total++;
    }
    pageToken = page.pageToken || undefined;
    // Yield to the event loop between pages so V8 can collect the
    // previous page's UserRecord objects before we request the next.
    await new Promise((r) => setImmediate(r));
  } while (pageToken);

  if (!earliest || !latest) {
    return { data: [], totalUsers: 0, generatedAt: Date.now() };
  }

  const endDate = new Date();
  endDate.setUTCHours(0, 0, 0, 0);
  const startDate = new Date(
    Date.UTC(
      earliest.getUTCFullYear(),
      earliest.getUTCMonth(),
      earliest.getUTCDate(),
    ),
  );

  const data: DailyPoint[] = [];
  let running = 0;
  for (
    const d = new Date(startDate);
    d <= endDate;
    d.setUTCDate(d.getUTCDate() + 1)
  ) {
    const key = d.toISOString().slice(0, 10);
    const users = countsByDate[key] || 0;
    running += users;
    data.push({ date: key, users, cumulative: running });
  }

  return { data, totalUsers: total, generatedAt: Date.now() };
}

function startBuild(): Promise<UserGrowthSeries> {
  if (pendingBuild) return pendingBuild;
  pendingBuild = buildDailySeries()
    .then(async (series) => {
      cachedSeries = series;
      await setJsonCache(REDIS_KEY, series, REDIS_TTL_SECONDS);
      return series;
    })
    .finally(() => {
      pendingBuild = null;
    });
  return pendingBuild;
}

function refreshInBackground() {
  void startBuild().catch((err) =>
    console.error("user-growth background rebuild failed:", err),
  );
}

export async function getUserGrowthSeries(): Promise<UserGrowthSeries> {
  const now = Date.now();

  if (cachedSeries) {
    if (now - cachedSeries.generatedAt >= FRESH_TTL_MS) refreshInBackground();
    return cachedSeries;
  }

  const fromRedis = await getJsonCache<UserGrowthSeries>(REDIS_KEY);
  if (fromRedis) {
    cachedSeries = fromRedis;
    if (now - fromRedis.generatedAt >= FRESH_TTL_MS) refreshInBackground();
    return fromRedis;
  }

  // No cache anywhere — only the very first request after a Redis flush
  // pays the cost of a full listUsers walk.
  return startBuild();
}

export function sliceSeries(
  series: UserGrowthSeries,
  daysParam: string | null | undefined,
): UserGrowthResponse {
  const wantsAll = !daysParam || daysParam === "all" || daysParam === "0";
  const days = wantsAll ? null : Math.max(1, parseInt(daysParam, 10));

  let data = series.data;
  if (days != null) {
    const start = new Date();
    start.setUTCDate(start.getUTCDate() - days);
    const startKey = start.toISOString().slice(0, 10);
    data = series.data.filter((p) => p.date >= startKey);
  }

  const windowUsers = data.reduce((sum, p) => sum + p.users, 0);

  return {
    data,
    totalUsers: series.totalUsers,
    windowUsers,
    days: days ?? series.data.length,
    generatedAt: series.generatedAt,
  };
}
