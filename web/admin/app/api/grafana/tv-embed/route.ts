import { NextRequest, NextResponse } from "next/server";
import { embedEnabled, legacyBoardOpen, mintEmbed } from "@/lib/grafana-embed";
import { resolveActiveTvToken } from "@/lib/tv-links";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Capability-authenticated kiosk embed. The TV share token is validated
 * server-side before any embed is minted, so revocation and expiry keep
 * working after the private cutover closes anonymous legacy access.
 * Flag-off mirrors /api/grafana/embed's rollout honesty: the kiosk keeps
 * the legacy board only while that board actually serves anonymous readers.
 */
export async function POST(request: NextRequest) {
  const headers = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
  };
  let token: unknown;
  try {
    token = (await request.json()).token;
  } catch {
    token = undefined;
  }
  if (typeof token !== "string" || token.length === 0 || token.length > 128) {
    return NextResponse.json(
      { error: "Invalid TV link" },
      { status: 400, headers }
    );
  }
  const link = await resolveActiveTvToken(token);
  if (!link) {
    return NextResponse.json(
      { error: "Invalid TV link" },
      { status: 403, headers }
    );
  }
  if (!embedEnabled()) {
    return NextResponse.json(
      { enabled: false, legacy: await legacyBoardOpen() },
      { headers }
    );
  }
  try {
    return NextResponse.json(
      { enabled: true, ...(await mintEmbed(`tv:${link.id}`)) },
      { headers }
    );
  } catch {
    // The token already proved the capability; only enrollment failed.
    console.error("Grafana TV embed enrollment unavailable");
    return NextResponse.json(
      { error: "TV dashboard login unavailable" },
      { status: 503, headers }
    );
  }
}
