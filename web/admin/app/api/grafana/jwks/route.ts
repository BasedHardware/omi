import { NextResponse } from "next/server";
import { embedJwks } from "@/lib/grafana-embed";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET() {
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
