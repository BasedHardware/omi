import { NextRequest, NextResponse } from "next/server";
import { embedEnabled, mintEmbed } from "@/lib/grafana-embed";
import { resolveActiveTvToken } from "@/lib/tv-links";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

/**
 * Capability-authenticated kiosk embed. The TV share token is validated
 * server-side before the private Business embed is minted, so revocation,
 * expiry, and the issuer still holding finance:read keep working for
 * existing TV links.
 * Flag-off keeps the TV page unavailable until the private Business embed is
 * enabled; it never falls back to the retired same-origin Grafana instance.
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
    return NextResponse.json({ enabled: false }, { headers });
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
