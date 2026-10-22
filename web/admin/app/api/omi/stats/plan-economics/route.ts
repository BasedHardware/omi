import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { fetchPlanEconomics } from "@/lib/services/plan-economics";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const auth = await requireScope(request, "finance:read");
  if (auth instanceof NextResponse) return auth;
  // No request-level platform attribution exists for these cost pools.
  const platform = request.nextUrl.searchParams.get("platform");
  if (platform && platform !== "all") {
    return auth.json(
      { error: "Plan economics is available for all platforms only" },
      { status: 400 }
    );
  }
  try {
    return auth.json(await fetchPlanEconomics(), {
      headers: { "Cache-Control": "no-store" },
    });
  } catch {
    console.error("Plan economics aggregate query failed");
    return auth.json(
      { error: "Plan economics unavailable", rows: [], partial: true },
      { status: 502 }
    );
  }
}
