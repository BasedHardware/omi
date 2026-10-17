import { NextRequest, NextResponse } from "next/server";
import { verifyAdmin } from "@/lib/auth";
import { embedEnabled, mintEmbed } from "@/lib/grafana-embed";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  const admin = await verifyAdmin(request);
  if (admin instanceof NextResponse) return admin;
  const headers = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  };
  if (!embedEnabled())
    return NextResponse.json({ enabled: false }, { headers });
  try {
    return NextResponse.json(
      { enabled: true, ...(await mintEmbed(admin.uid)) },
      { headers }
    );
  } catch {
    console.error("Grafana embed enrollment unavailable");
    return NextResponse.json(
      { error: "Dashboard login unavailable" },
      { status: 503, headers }
    );
  }
}
