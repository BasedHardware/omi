import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { getUserGrowthSeries, sliceSeries } from "@/lib/services/user-growth";
import { getPayload, setPayload } from "@/lib/payload-cache";

export const dynamic = "force-dynamic";
export const maxDuration = 3600;

function cacheKey(daysParam: string): string {
  return `daily-new-users:v1:${daysParam}`;
}

export { cacheKey as dailyNewUsersCacheKey };

export async function computeDailyNewUsers(daysParam: string) {
  const series = await getUserGrowthSeries();
  return sliceSeries(series, daysParam);
}

export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const { searchParams } = new URL(request.url);
    const daysParam = searchParams.get("days") || "all";
    const key = cacheKey(daysParam);

    const cached = await getPayload<ReturnType<typeof sliceSeries>>(key);
    if (cached) {
      return NextResponse.json(cached.data);
    }

    const payload = await computeDailyNewUsers(daysParam);
    await setPayload(key, payload);
    return NextResponse.json(payload);
  } catch (error: any) {
    console.error("Daily new users error:", error);
    return NextResponse.json(
      { error: error.message || "Failed to fetch daily new users" },
      { status: 500 },
    );
  }
}
