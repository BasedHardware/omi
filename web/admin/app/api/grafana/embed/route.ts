import { NextRequest, NextResponse } from "next/server";
import { requireScope } from "@/lib/auth";
import { embedEnabled, mintEmbed } from "@/lib/grafana-embed";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  // The Business board (omi-tv-v2) carries revenue, MRR, Shopify and
  // cost-vs-revenue panels, so minting an embed is a finance read.
  const admin = await requireScope(request, "finance:read");
  if (admin instanceof NextResponse) return admin;
  const headers = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  };
  if (!embedEnabled()) return admin.json({ enabled: false }, { headers });
  try {
    return admin.json(
      { enabled: true, ...(await mintEmbed(admin.uid)) },
      { headers }
    );
  } catch {
    console.error("Grafana embed enrollment unavailable");
    return admin.json(
      { error: "Dashboard login unavailable" },
      { status: 503, headers }
    );
  }
}
