import { NextResponse } from "next/server";
import { embedEnabled, embedJwks } from "@/lib/grafana-embed";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
  if (!embedEnabled()) return NextResponse.json({ keys: [] }, { status: 503 });
  try {
    return NextResponse.json(await embedJwks(), {
      headers: { "Cache-Control": "public, max-age=60" },
    });
  } catch {
    return NextResponse.json(
      { error: "Signing keys unavailable" },
      { status: 503 }
    );
  }
}
