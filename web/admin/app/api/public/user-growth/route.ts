import { NextRequest, NextResponse } from "next/server";
import { getUserGrowthSeries, sliceSeries } from "@/lib/services/user-growth";

export const dynamic = "force-dynamic";

// Public, unauthenticated endpoint. Returns only aggregate counts —
// no UIDs, emails, or any other user-level data.
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const series = await getUserGrowthSeries();
    const body = sliceSeries(series, searchParams.get("days"));
    return NextResponse.json(body, {
      headers: {
        "Cache-Control": "public, max-age=300, s-maxage=300",
      },
    });
  } catch (error: any) {
    console.error("Public user-growth error:", error);
    return NextResponse.json(
      { error: "Failed to fetch user growth" },
      { status: 500 },
    );
  }
}
