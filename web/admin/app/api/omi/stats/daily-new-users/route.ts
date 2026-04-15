import { NextRequest, NextResponse } from "next/server";
import { getAdminAuth } from "@/lib/firebase/admin";
import { verifyAdmin } from "@/lib/auth";

export const dynamic = "force-dynamic";

// The Firestore `users` collection has a `created_at` field that was
// backfilled for ~63K existing users on a single day in late 2024, so it
// can't be used to derive signup history. Firebase Auth's
// `metadata.creationTime` is set by the Auth service on account creation
// and is the authoritative signup timestamp.
//
// Scanning every user via `listUsers()` pages 1000 at a time (112K ≈ 25s),
// so the full series is cached in module scope for 10 minutes. A pending
// rebuild is shared across concurrent requests so we don't fan out.

type DailyPoint = { date: string; users: number; cumulative: number };
type CachedSeries = {
  data: DailyPoint[];
  totalUsers: number;
  generatedAt: number;
};

const CACHE_TTL_MS = 10 * 60 * 1000;

let cachedSeries: CachedSeries | null = null;
let pendingBuild: Promise<CachedSeries> | null = null;

async function buildDailySeries(): Promise<CachedSeries> {
  const auth = getAdminAuth();
  const countsByDate: Record<string, number> = {};
  let pageToken: string | undefined = undefined;
  let total = 0;
  let earliest: Date | null = null;
  let latest: Date | null = null;

  do {
    const page = await auth.listUsers(1000, pageToken);
    for (const user of page.users) {
      const ct = user.metadata?.creationTime
        ? new Date(user.metadata.creationTime)
        : null;
      if (!ct || Number.isNaN(ct.getTime())) continue;
      const key = ct.toISOString().slice(0, 10);
      countsByDate[key] = (countsByDate[key] || 0) + 1;
      if (!earliest || ct < earliest) earliest = ct;
      if (!latest || ct > latest) latest = ct;
      total++;
    }
    pageToken = page.pageToken || undefined;
  } while (pageToken);

  if (!earliest || !latest) {
    return { data: [], totalUsers: 0, generatedAt: Date.now() };
  }

  // Fill every day from the earliest signup to today so the curve is
  // continuous (no gaps) and ends on the current date.
  const endDate = new Date();
  endDate.setUTCHours(0, 0, 0, 0);
  const startDate = new Date(
    Date.UTC(earliest.getUTCFullYear(), earliest.getUTCMonth(), earliest.getUTCDate()),
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

async function getSeries(): Promise<CachedSeries> {
  const now = Date.now();
  if (cachedSeries && now - cachedSeries.generatedAt < CACHE_TTL_MS) {
    return cachedSeries;
  }
  if (pendingBuild) return pendingBuild;
  pendingBuild = buildDailySeries()
    .then((series) => {
      cachedSeries = series;
      return series;
    })
    .finally(() => {
      pendingBuild = null;
    });
  return pendingBuild;
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const daysParam = searchParams.get("days");
    const wantsAll =
      !daysParam || daysParam === "all" || daysParam === "0";
    const days = wantsAll ? null : Math.max(1, parseInt(daysParam!, 10));

    const series = await getSeries();

    let data = series.data;
    if (days != null) {
      const start = new Date();
      start.setUTCDate(start.getUTCDate() - days);
      const startKey = start.toISOString().slice(0, 10);
      data = series.data.filter((p) => p.date >= startKey);
    }

    return NextResponse.json({
      data,
      totalUsers: series.totalUsers,
      days: days ?? series.data.length,
      generatedAt: series.generatedAt,
    });
  } catch (error: any) {
    console.error("Daily new users error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch daily new users" },
      { status: 500 },
    );
  }
}
