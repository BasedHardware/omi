import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { fetchPlanEconomics } from "@/lib/services/plan-economics";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const auth = await verifyAdmin(request);
  if (auth instanceof NextResponse) return auth;
  // No request-level platform attribution exists for these cost pools.
  const platform = request.nextUrl.searchParams.get("platform");
  if (platform && platform !== "all") {
    return NextResponse.json(
      { error: "Plan economics is available for all platforms only" },
      { status: 400 }
    );
  }
  try {
    return NextResponse.json(await fetchPlanEconomics(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    console.error("Plan economics aggregate query failed");
    return NextResponse.json(
      { error: "Plan economics unavailable", rows: [], partial: true },
      { status: 502 }
    );
  }
}
